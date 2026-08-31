# Sprint 023 — Project Operations (Discovery / Contract Lock)

Status: **DISCOVERY ONLY — no production code, no migrations, no tests
written.** Locked per `docs/ROADMAP.md`'s reconciled v1.0 sequence.

Branch: `sprint-023-project-operations`
Baseline: `main` @ `ddb3fc2` (Sprint 022 merge, confirmed via
`git rev-parse origin/main`)

## Objective

A `booked` Project (the state a Quote handoff already creates it in,
`app/quotes/service.py`) becomes operationally manageable: an Owner assigns
a responsible Staff member, and the Project advances through validated
operational stages, one step at a time, with every transition audited. No
task boards, no scheduling engine, no calendar sync — the smallest vertical
that makes a booked Project trackable end-to-end through fabrication and
installation.

## 1. Current-state findings (verified against `main` @ `ddb3fc2`)

### `Project.status` is a single shared 7-value pipeline, already in place

`app/projects/models.py`'s `ProjectStatus` enum (Sprint 006, unchanged
since): `enquiry → quoted → booked → templated → fabricated → installed →
complete`. Stored as a plain `String` column
(`app/database/models.py::Project.status`), no DB-level enum — same
convention as `ActivityType`/`UserRole`. **No new statuses are needed.**

### The status-update endpoint has zero transition validation and zero RBAC — a real, pre-existing gap

`app/projects/router.py::update_project_status` — dependencies are just
`Depends(get_current_user)` (no `require_role`). `ProjectService.update_status`
(`app/projects/service.py:70-73`) calls `crud.update_project_status`
directly with whatever `ProjectStatus` value the caller sent — **any
authenticated user of any role, including `role=None`, can currently set
any Project to any status, forward, backward, or skipping stages, with no
audit trail.** `crud.update_project_status` (line 336) *is* tenant-scoped
(filters by `tenant_id` in its `select`), so cross-tenant is already `404`
— that part doesn't need fixing. The RBAC and transition-validation gaps
do, and closing them is this sprint's core contract, not scope creep: every
other stateful transition in this codebase (`convert-to-customer`,
appointment create/status) already enforces both.

### No staff-assignment field exists anywhere on `Project`

`app/database/models.py::Project` has `tenant_id`, `customer_id`,
`quote_id`, `name`, `notes`, `status`, `created_at` — no
`assigned_user_id`, no equivalent. `app/users/` (Sprint 015) already
exposes `GET /api/v1/users` → `TeamMemberOut[]` (id, name, email, role,
is_active, created_at) for listing a tenant's team — this is directly
reusable as the frontend's staff picker; no new listing endpoint is
needed.

### User lookup is not tenant-scoped by default

`crud.get_user_by_id(db, user_id)` (line 175) takes no `tenant_id` and
returns any user in the database. Every existing caller either doesn't
need tenant-scoping (auth) or is Sprint 011/015's own team-management
code, which already tenant-scopes some other way. Sprint 023's assignment
service must verify `user.tenant_id == project.tenant_id` itself before
accepting an `assigned_user_id` — mirroring `ProjectService.create`'s
existing `CustomerNotFoundError` pattern for `customer_id`
(`app/projects/service.py:44-47`), not a new convention.

### No `updated_at` anywhere in this schema — established, unbroken convention

Every table's only timestamp is `created_at`; mutations are tracked via
`ActivityLog`, not a mutation-timestamp column (explicitly re-confirmed by
Sprint 022's `Appointment` docstring). **This sprint will not add
`started_at`/`completed_at` columns** — `ActivityLog`'s own timestamp on
each `PROJECT_STATUS_CHANGED` event already gives an exact, queryable
audit trail of when each stage began, with zero new columns and zero
deviation from precedent.

### Existing service/router/activity/atomicity shape (the template to reuse)

`app/appointments/service.py` (Sprint 022) is the closest precedent: a
tenant-scoped parent lookup, a caller-owned transaction
(`crud.*(..., commit=False)` → `activity_service.log(..., db=db)` →
`db.commit()`, `except: db.rollback(); raise`), and a service-level domain
error the router maps to an HTTP status. This sprint reuses that shape
exactly for both the status-transition and assignment routes.

### RBAC (`app/auth/dependencies.py::require_role`)

Every stateful mutation added since Sprint 021 uses
`require_role(UserRole.OWNER, UserRole.STAFF)`. No route in this codebase
is Owner-only today. Sprint 023 introduces the first Owner-only route
(assignment — see §6/Decision 2) as a deliberate, narrow exception, not a
new general pattern.

### Tenant isolation

Every relationship lookup in this codebase 404s on cross-tenant access
(ADR-029, "hide existence"), never 403. `get_project_by_id` and
`update_project_status` already do this for `Project`; the new assignment
path must do the same for the `assigned_user_id → users.id` relationship.

### Activity logging

`ActivityType` (`app/activity/models.py`) has no `project_assigned` or
`project_status_changed` member yet — both are new.

### Frontend

`apps/web/app/projects/[id]/page.tsx` (current, post-Sprint-022) already
has an unconditional "Advance to {next status}" button
(`handleAdvance`/`nextStatus`, lines 96-113, 242-252) with **no role
gating at all** — the frontend mirror of the backend RBAC gap above. No
assignment UI exists. `apps/web/lib/api.ts` already has `updateProjectStatus`
and `getUsers`; no `assignProject`/equivalent exists.

### E2E

`apps/web/e2e/enquiry-conversion.spec.ts`, `quote-handoff.spec.ts`,
`site-visit-scheduling.spec.ts` exist; none touch status-transition RBAC,
validation, or assignment.

## 2. Smallest useful Sprint 023 vertical (locked scope)

Project (already `booked` via quote handoff) → Owner assigns a Staff
member → Owner/Staff advances the Project one status forward at a time
through the existing 7-value pipeline → current stage and assignee are
visible on the Project detail page → every assignment and every status
change is activity-logged → both persist across reload → verified by a
real Playwright E2E.

**Explicitly not built this sprint** (§13): task boards/checklists,
multiple assignees or teams, workload/availability logic, calendar sync,
started_at/completed_at columns, notifications, materials/procurement,
timesheets, cost tracking, anything from Sprints 024-030.

## 3. Locked data model change

One additive column, one additive migration:

- `Project.assigned_user_id: uuid.UUID | None` — nullable FK →
  `users.id`, indexed (matches every other FK-to-parent column in this
  schema, e.g. `Appointment.project_id`). No cascade rule needed
  (`ON DELETE` behavior matches existing FK columns — Postgres default
  `NO ACTION`, consistent with every other FK in this schema having no
  explicit `ondelete=`).
- No new table. No `started_at`/`completed_at`/`assigned_at` columns (§1).

## 4. Locked status-transition contract

- **Graph**: strictly linear, one step forward only —
  `enquiry → quoted → booked → templated → fabricated → installed →
  complete`. `PATCH /projects/{id}/status` accepts only the *exact next*
  value in this sequence for the Project's current status. Anything else
  — a repeat of the current status, a skip, or any backward move —
  is rejected with `409`. `complete` is terminal: no further transition is
  valid from it (matches the frontend's existing "This project has
  completed the pipeline" terminal state).
- **Reason**: directly matches the explicit instruction ("prefer strict
  forward transitions, no arbitrary status jumping") and closes the exact
  gap found in §1 without inventing new states or branching logic the
  product doesn't need yet.
- **RBAC**: `require_role(OWNER, STAFF)` — closes the zero-RBAC gap found
  in §1, matching every other stateful mutation in this codebase.
- **Activity**: one new type, `PROJECT_STATUS_CHANGED`, logged once per
  successful transition with a safe (`Project {id} moved from {old} to
  {new}`) description — no customer PII. A single generic type, not one
  member per status pair (7 statuses would mean up to 6 transition-pair
  members), because this is a uniform linear progression, unlike
  Appointment's branching completed/cancelled outcome (Sprint 022,
  Decision 4) which genuinely needed two distinct terminal types.
- **Atomicity**: `crud.update_project_status(..., commit=False)` →
  `activity_service.log(..., db=db)` → one `db.commit()`, `rollback()` +
  re-raise on exception — Sprint 021/022's proven pattern, additive
  `commit` parameter on the existing crud function.

## 5. Locked staff-assignment contract

- **Endpoint**: `PATCH /api/v1/projects/{project_id}/assign`, body
  `{assigned_user_id: UUID | null}` (nullable to support unassigning —
  the minimal useful shape; no separate unassign endpoint).
- **RBAC**: `require_role(OWNER)` only. **Decision 2** (§9) — assignment is
  a management decision distinct from doing the operational work, and
  restricting it to Owner is the smallest deliberate deviation from the
  otherwise-universal OWNER+STAFF pattern, not a new general convention.
- **Tenant invariant**: the target user must belong to the same tenant as
  the Project (§1's `get_user_by_id`/tenant-scoping finding) — cross-tenant
  or nonexistent `assigned_user_id` → `404` "User not found" (mirrors
  `ProjectService.create`'s existing `CustomerNotFoundError` → `404`
  pattern for `customer_id`, not a new error shape). `assigned_user_id:
  null` always succeeds (no lookup needed).
- **No role restriction on the assignee** — any tenant user (Owner or
  Staff) can be the assignee. No `is_active` check either. Both are
  deliberately out of scope: the brief explicitly warns against
  introducing team/availability logic this codebase doesn't already have,
  and nothing in the target vertical requires it.
- **Activity**: one new type, `PROJECT_ASSIGNED`, logged on every
  successful assignment change (including to `null`), safe description
  only (`Project {id} assigned to {user_id}` / `Project {id} unassigned`).
- **Atomicity**: same `commit=False`/`db=`/`rollback` shape as §4.
- **Idempotency**: assigning the same `assigned_user_id` again is not a
  special case — it re-runs the same write and logs another
  `PROJECT_ASSIGNED` event. Unlike Appointment's terminal-status
  idempotency (which existed to make an accidental double-click on a
  disappearing button safe), a re-assignment is always an explicit,
  deliberate action through a persistent form, so there is no
  double-submission risk to guard against, and suppressing a genuine
  re-assignment's audit event would be the wrong default.

## 6. Tenant isolation (both routes)

- Both routes 404 via the existing tenant-scoped `get_project_by_id`
  lookup before any write. Tenant B can never assign staff to, or advance
  the status of, Tenant A's Project — proven by dedicated cross-tenant
  tests, same convention as every prior sprint.
- Tenant B's own user id can never be assigned to Tenant A's Project
  (§5's tenant invariant) — proven by a dedicated test.

## 7. RBAC summary

| Route | Owner | Staff | role=None |
|---|---|---|---|
| `PATCH /projects/{id}/status` | allow | allow | `403` |
| `PATCH /projects/{id}/assign` | allow | `403` | `403` |

## 8. Frontend contract

`apps/web/app/projects/[id]/page.tsx` gains a "Project Operations"
sub-section (not a page redesign):

- Current stage (already shown via the existing status `Badge`) plus the
  assigned Staff member's name (or "Unassigned").
- "Advance to {next status}" button — **now gated** to
  `role === "Owner" || role === "Staff"` (closing the frontend mirror of
  the backend RBAC gap), hidden entirely once `status === "complete"`
  (already the existing behavior for `nextStatus === null`).
- An Owner-only "Assign" control — a `<select>` populated from
  `api.getUsers()` (already exists, no new listing endpoint), "Unassigned"
  as a selectable option mapping to `assigned_user_id: null`.
- Both actions: server-response-authoritative (never optimistic), failure
  leaves state/selection unchanged and surfaces the existing error-card
  pattern, action re-enabled for retry — same convention as every prior
  sprint's frontend hardening cycle.

`apps/web/lib/api.ts` gains `assignProject(id, assignedUserId)`. No
renaming of `updateProjectStatus` — it already has the right shape and
name.

## 9. Open decisions (resolved now, smallest coherent choice each)

### Decision 1 — validate transitions in the service or the router

- **Selected**: service (`ProjectService.update_status` raises a new
  `InvalidProjectTransitionError`; router maps it to `409`).
- **Reason**: matches every existing domain-error convention in this
  codebase (`CustomerNotFoundError`, `ProjectNotInEnquiryStateError`,
  `AppointmentTransitionError`) — the router never contains business
  rules.

### Decision 2 — assignment RBAC: Owner-only vs. Owner+Staff

- **Options**: Owner-only (management decision) vs. Owner+Staff (anyone
  operational can reassign).
- **Selected**: Owner-only.
- **Reason**: the brief's own suggested split ("OWNER: assign staff... ;
  STAFF: advance status?") is also the more conservative, harder-to-abuse
  default, and nothing in current product usage (no self-assignment
  workflow exists anywhere in this codebase) argues for Staff self-service
  reassignment yet. Easiest decision to loosen later; hardest to tighten
  after the fact once relied upon.

### Decision 3 — one generic `PROJECT_STATUS_CHANGED` vs. per-stage activity types

- **Selected**: one generic type (§4).
- **Reason**: 7 linear statuses would need up to 6 transition-specific
  members for no behavioral gain — `ActivityLog.description` already
  carries the specific from/to values a reader needs, matching
  `PROJECT_CREATED`/`ENQUIRY_CONVERTED`'s existing single-type-with-a-
  descriptive-string precedent over Appointment's genuinely-branching
  two-terminal-outcome case.

### Decision 4 — reject vs. no-op a same-status "transition"

- **Selected**: reject with `409` (§4).
- **Reason**: there is no UI path that would ever submit the current
  status as a "next" value (the frontend only ever sends the single
  computed `nextStatus`), so this only matters for direct API misuse or a
  stale client — treating it as a real conflict (not a silent no-op) is
  more honest and consistent with rejecting any other non-adjacent value.

## 10. True E2E contract

Real Chromium + real Next.js + real FastAPI + real Postgres, no mocks:

1. Sign up a fresh synthetic tenant/Owner (real API).
2. Create a Project directly at `booked` via the real quote-handoff path
   (or, if that proves awkward to drive end-to-end in one spec, via a
   direct authenticated `POST /projects` + one real `PATCH .../status`
   call through enquiry→quoted→booked — decided at RED-writing time,
   whichever keeps the spec's setup honestly "real API, not fabricated
   state" without re-deriving quote-handoff's own multi-step flow).
3. Log in through the real UI.
4. Open the Project detail page — see "Unassigned" and the current stage.
5. Assign a Staff member through the UI — verify it renders and persists
   across reload.
6. Advance the Project one stage through the UI — verify the badge/label
   updates and persists across reload.
7. Verify via the live API: `assigned_user_id`, `status`, and exactly one
   `project_assigned` + one `project_status_changed` activity record.

## 11. Staging contract

Identical discipline to Sprint 022 (`docs/STAGING_RUNBOOK.md`): clean-commit
`git archive` + `railway up`, `/health`/`/ready`, **`alembic current` must
equal `alembic heads` before any browser verification** (Sprints 020 and
022 both hit CLI migration drift — treat recurrence as expected, not
surprising, and remediate via the documented `railway ssh` path before
proceeding, never inferring migration success from health/ready alone),
real browser flow, live security checks (cross-tenant, RBAC, invalid
transition), live activity verification, smoke suite. Production
untouched throughout (already zero deployed services).

## 12. Migration plan

One migration: add `assigned_user_id` (nullable `UUID`, indexed,
explicitly named FK `fk_projects_assigned_user_id_users` — never left
autogenerate-unnamed, per every prior new-column/table migration's
established fix in this repo) to `projects`. Generated via
`alembic revision --autogenerate`, hand-verified for the explicit
constraint name before use, verified with `alembic heads`/`alembic check`
and a full downgrade→upgrade round-trip.

## 13. Explicit out of scope

Task boards/checklists/stages-within-a-stage, multiple assignees or teams,
staff workload/availability/capacity logic, calendar sync, `started_at`/
`completed_at`/`assigned_at` columns, self-assignment by Staff,
reassignment notifications, materials/procurement/purchase orders,
timesheets, subcontractors, cost tracking, stock control, any Sprint
024-030 work (notifications/follow-up, command centre, hardening II,
UAT, release candidate, production launch), Google/Outlook calendar,
payments, AI workforce.

## 14. Locked TDD sequence

1. First RED: Owner assigns Staff to their own tenant's `booked` Project → `200`, `assigned_user_id` round-trips.
2. GREEN: migration + model + minimal assign endpoint (Owner-only, no validation yet beyond existence).
3. RED/GREEN: cross-tenant `assigned_user_id` → `404`.
4. RED/GREEN: Staff (non-Owner) caller on assign → `403`.
5. RED/GREEN: cross-tenant Project on assign → `404`.
6. RED/GREEN: `PROJECT_ASSIGNED` activity, exactly once per call.
7. RED/GREEN: assignment atomicity (failure-injection on activity log → assignment rolls back).
8. RED/GREEN: valid forward status transition (`booked → templated`) now requires Owner/Staff (locks in existing tenant-scoping, adds the missing RBAC).
9. RED/GREEN: invalid transition (skip, repeat, backward) → `409`.
10. RED/GREEN: `role=None` on status transition → `403` (closes the zero-RBAC gap).
11. RED/GREEN: cross-tenant status transition still `404` (regression lock, already true).
12. RED/GREEN: `PROJECT_STATUS_CHANGED` activity, exactly once per real transition.
13. RED/GREEN: status-transition atomicity (failure-injection).
14. Full backend regression.
15. Frontend RED/GREEN: assignment control + gated advance button.
16. Frontend hardening: failure safety, permission visibility.
17. True Playwright E2E.
18. Full local regression (backend, frontend, e2e, typecheck, lint, runtime-config, docker-contract, build, alembic heads/check).
19. Exact-head CI.
20. Staging deploy + migration verification + browser/security/activity verification + smoke.
21. Docs closeout.
22. Final feature CI.
23. PR, explicit merge commit, origin/main verification, post-merge CI.

## LOCKED CONTRACT

- **Data model**: `Project.assigned_user_id` (nullable UUID FK →
  `users.id`, indexed, named constraint `fk_projects_assigned_user_id_users`).
  No other schema change.
- **Status endpoint** (existing route, tightened): `PATCH
  /api/v1/projects/{project_id}/status` — `require_role(OWNER, STAFF)`;
  accepts only the exact next value in `enquiry → quoted → booked →
  templated → fabricated → installed → complete`; any other value → `409`;
  `complete` is terminal; logs `PROJECT_STATUS_CHANGED` once per success;
  atomic with its activity write.
- **New assignment endpoint**: `PATCH /api/v1/projects/{project_id}/assign`
  — `require_role(OWNER)`; body `{assigned_user_id: UUID | null}`; target
  user must share the Project's tenant or `404`; logs `PROJECT_ASSIGNED`
  once per call (including unassignment); atomic with its activity write.
- **Tenant isolation**: both routes 404 on a cross-tenant Project
  (existing `get_project_by_id` scoping); assign additionally 404s on a
  cross-tenant `assigned_user_id`.
- **Frontend**: "Assign" control (Owner-only, `<select>` from
  `api.getUsers()` + "Unassigned") and the existing "Advance" button
  (now Owner/Staff-gated) on the Project detail page; both
  server-authoritative and failure-safe.
- **E2E**: real browser — assign, advance, both persist across reload,
  both verified live via the API and activity log.
- **Out of scope**: everything in §13, unconditionally.

### Verdict

- **All open decisions resolved: YES** — binding for implementation.
- **Sprint 023 contract locked: YES.**
- **Ready for the first backend RED: YES.**
