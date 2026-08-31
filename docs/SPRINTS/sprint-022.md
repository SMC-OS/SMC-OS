# Sprint 022 — Appointment / Site Visit Scheduling

Status: **END-TO-END DELIVERED — staging-verified, pending final merge
gate.** Locked per `docs/ROADMAP.md`'s reconciled v1.0 sequence
(`docs/ROADMAP.md`, reconciliation merged `843439d`). Full end-to-end
evidence in §17 below.

Branch: `sprint-022-appointment-site-visit`
Baseline: `main` @ `843439d` (roadmap reconciliation merge, confirmed via
`git rev-parse origin/main`)

## Objective

Close the first genuinely missing vertical in the product's intended
sequence (Enquiry → Customer → **Appointment/Site Visit** → Quote → ...).
A staff member schedules a site visit against an existing enquiry Project,
can mark it completed or cancelled, and sees the visit history on the
Project detail page — no calendar sync, no customer self-booking, no
availability engine. Same one-vertical-slice-per-sprint cadence every prior
sprint in this codebase has followed since Sprint 008.

## 1. Current-state findings (verified against `main` @ `843439d`, not assumed)

### No existing Appointment/Site Visit capability, anywhere
A repo-wide, case-insensitive search for `appointment|appointments|site.visit|
site_visit|scheduled_at|assigned_user|assigned_to|assignee|calendar` across
`app/`, `apps/web/`, `tests/`, `alembic/`, and `docs/` returns exactly one
code hit outside documentation: `app/brain/router.py`'s keyword-intent
dictionary maps the string `"calendar"` → the label `"scheduling"` — a stub
entry in the still-unbuilt AI router (deferred, `docs/ROADMAP.md`'s
"Deferred — AI Workforce & Commerce" section), not a real feature. No
`Appointment`/`SiteVisit` model, table, migration, service, router, frontend
page, or test exists anywhere. This confirms the Sprint 021 audit's finding
and rules out any risk of duplicating existing work.

### Alembic
Current head: `d3e7a9c1f204` (`alembic/versions/d3e7a9c1f204_add_project_quote_id.py`,
Sprint 020's `Project.quote_id` addition — the same head Sprint 021 left
untouched). 15 revisions total. No migration in-flight.

### Project model (`app/database/models.py`)
`Project`: `id, tenant_id (nullable FK, indexed), customer_id (nullable FK),
quote_id (nullable, unique FK), name, notes, status (default "enquiry"),
created_at`. **No `updated_at` column** — worth noting explicitly, see
below. `Project.customer_id` already identifies the customer indirectly;
per the task's own steer, an `Appointment` does **not** need its own
`customer_id` — it reaches the customer through `project_id →
Project.customer_id`, exactly the same indirection `Quote`/`Document`
already avoid duplicating (none of them carry a redundant path to data
already reachable through one FK hop).

### Customer model
Unchanged since Sprint 004/012: `id, tenant_id, name, email, phone,
created_at`. No relevance beyond confirming the existing
`Project.customer_id` path.

### No `updated_at` convention anywhere in this schema
Checked every table in `app/database/models.py` (`Tenant, Customer, Quote,
Project, Material, User, Invitation, PortalLink, Document, Message,
ActivityLog, NotificationRecord`) — **none** have an `updated_at` column.
The established convention is `created_at` only, with any mutation
(`Project.status`, `Quote.status`, `Invitation.status`, `User.is_active`)
tracked via the existing `ActivityLog`, not a row-level timestamp. Sprint
022 should follow this convention rather than introduce a new one
unilaterally — see the proposed data model below.

### Existing service/router shape (the template to reuse)
Every business module (`customers`, `projects`, `quotes`, `documents`,
`portal`, `messages`) follows the identical `models.py` /`service.py`/
`router.py` shape, mounted once in `app/api/v1/__init__.py`. The most
directly analogous precedent is Sprint 021's
`ProjectService.convert_to_customer` (`app/projects/service.py`):
1. tenant-scoped lookup of the parent record (`crud.get_project_by_id(db,
   project_id, tenant_id)`), `None` → `404` at the router;
2. a relationship-bypass guard is unnecessary here in the *reverse*
   direction Sprint 021 needed one for (Appointment doesn't reference a
   second tenant-owned entity the way conversion referenced a Customer) —
   the single tenant-scoped Project lookup is sufficient, matching
   `Document.upload_document`'s and `PortalService.create_link`'s exact
   precedent (both attach to one already-tenant-verified parent and need no
   second check);
3. the service creates the child row and returns it;
4. the service logs its own `ActivityEvent` (every mutating service in this
   codebase does this itself, never the router).

### RBAC (`app/auth/dependencies.py::require_role`)
`require_role(UserRole.OWNER, UserRole.STAFF)` is the established gate for
"routine business-data work" (Sprint 020's quote approve/handoff, Sprint
021's conversion) — as opposed to `require_role(UserRole.OWNER)` alone,
reserved for tenant-control actions (invitations, team deactivation).
Scheduling a site visit and marking it complete/cancelled is squarely
"routine operational scheduling," the same class of action as creating a
customer or converting an enquiry — not a tenant-control decision. **Both
OWNER and STAFF should be able to create/list/complete/cancel.** No new
role is needed or justified by anything in the current permission matrix
(`docs/USER_ROLES.md`).

### Tenant isolation
Universal convention since Sprint 012 (ADR-029): every tenant-owned table
has `tenant_id`, every `crud.get_*_by_id` filters by it, a cross-tenant
lookup returns `404` (never `403` — "hide existence"). An `Appointment`
table needs its own `tenant_id` column (not solely inherited via
`project_id` — matching every other child table's own explicit column,
e.g. `Document.tenant_id` alongside `Document.customer_id`) so
`get_appointment_by_id` can filter directly without an extra join, and so a
future direct-by-id lookup can't leak across tenants even if the caller
supplies a project id from a different tenant by mistake.

### Activity logging
13 `ActivityType` members exist today (`app/activity/models.py`), most
recently `ENQUIRY_CONVERTED` (Sprint 021). The established pattern: one new
enum member per meaningful domain transition, safe identifiers only in
`description` (no PII), logged by the service immediately after the
persisted mutation, tenant-scoped.

### Frontend
`apps/web/app/projects/[id]/page.tsx` currently renders: name/status
badge, Customer (link or `—`), Notes, an "Advance to {status}" button, and
— as of Sprint 021 — a conditional "Convert to Customer" action/form. No
appointment/scheduling UI of any kind exists. `apps/web/lib/api.ts` has no
appointment-related client method. No existing frontend page anywhere in
this repo has a user-editable date/time input — every date field today is
either server-generated (`created_at`, `approved_at`) or display-only
(`formatRelativeTime`, `toLocaleDateString`/`toLocaleString` in
`apps/web/lib/utils.ts` and four page files). **Sprint 022 is the first
sprint that needs one.**

### E2E
`apps/web/e2e/` has exactly two specs (`quote-handoff.spec.ts`, Sprint 020;
`enquiry-conversion.spec.ts`, Sprint 021), both following the identical
real-browser/real-API/real-Postgres shape against `playwright.config.ts`'s
hardcoded loopback URLs. `docs/STAGING_RUNBOOK.md` (updated Sprint 021)
already documents the clean-`git archive`-deploy and
verify-Alembic-via-SSH lessons a Sprint 022 staging pass would need to
follow again if a migration ships.

## 2. Proposed data model

```python
class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="scheduled")
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- **`tenant_id` non-nullable**: unlike `Customer`/`Project`/`Quote` (whose
  `tenant_id` stays nullable for anonymous-quote/legacy-row reasons that
  don't apply here), every `Appointment` is created by an already
  authenticated tenant user against an already tenant-verified Project —
  there is no anonymous-creation path to accommodate, so this table can
  start `NOT NULL` the way `User.tenant_id` and `Invitation.tenant_id` do,
  with no historical-row backfill concern (it's a brand new table).
- **`project_id` non-nullable, FK to `projects.id`, indexed** — the sole
  relationship; no `customer_id` duplicated (see above).
- **`created_by_user_id` non-nullable, FK to `users.id`** — audit-only,
  matching `Invitation.invited_by_user_id`/`PortalLink.created_by_user_id`/
  `Document.uploaded_by_user_id`'s exact convention. **No
  `assigned_user_id`** this sprint — no precedent for staff task-assignment
  exists anywhere in this codebase yet, and inventing one here would be
  scope creep into Sprint 023's actual territory (Project Operations). Can
  be added additively later without disruption.
- **`scheduled_at`, timezone-aware, non-nullable** — the one field this
  entire feature exists to carry. See §Date/time below.
- **`status`, plain `String`, `server_default="scheduled"`** — same
  no-DB-enum convention as `Project.status`/`Quote.status`/
  `Invitation.status`, validated at the Pydantic/API boundary only.
  Three values: `scheduled | completed | cancelled`. No `no_show`,
  `confirmed`, `in_progress`, or `rescheduled` — nothing in the current
  domain model or any adjacent sprint's scope calls for them, and adding
  them speculatively contradicts every prior sprint's "smallest useful
  slice" discipline.
- **`notes`, nullable `String`** — free-text, matching `Project.notes`'s
  exact shape.
- **`created_at` only, no `updated_at`** — per the repo-wide convention
  found above. A status change is itself the kind of "consequential
  action" this codebase always represents via `ActivityLog`, not a
  timestamp column race with it.
- **Indexes**: `tenant_id` and `project_id` both indexed (matching every
  other tenant-owned child table). No composite index proposed — no read
  pattern this sprint needs one (list-by-project is a single-column filter
  on an already-indexed column).
- **No unique constraint** — a Project can have many appointments over its
  lifetime (unlike `Project.quote_id`'s deliberate one-to-one), and nothing
  in scope requires "at most one scheduled visit at a time" as a DB-level
  rule; if that becomes a real product rule later it can be a partial
  unique index added non-disruptively.

## 3. Proposed endpoint contract

```
POST   /api/v1/projects/{project_id}/appointments        create
GET    /api/v1/projects/{project_id}/appointments         list (for that project)
PATCH  /api/v1/appointments/{appointment_id}/status       transition status
```

This mirrors two established precedents at once: `POST
/quotes/{id}/handoff`/`POST /projects/{id}/convert-to-customer`'s
"action-suffixed sub-resource of the parent" shape for creation nested
under the owning Project, and `PATCH /projects/{id}/status`'s existing
top-level status-transition shape for the second call (an appointment's own
id is already globally addressable once created, same as a project's own
id is for its own status PATCH — no need to nest the status update under
`/projects/{project_id}/appointments/{id}/status` when the appointment id
alone is sufficient and tenant-scoped).

- `POST .../appointments` body: `{scheduled_at: datetime, notes?: string}`
  — no `status` field (server always creates `scheduled`).
- `GET .../appointments` returns the project's own appointments,
  tenant-scoped, most-recent-first (matching `list_projects`/
  `list_customers`'s `order_by(created_at.desc())` convention — order by
  `scheduled_at` is arguably more useful for this specific list and is an
  open decision below).
- `PATCH /appointments/{id}/status` body: `{status: "completed" |
  "cancelled"}` — transitioning back to `scheduled` from either terminal
  state is out of scope (see below); the Pydantic enum can still technically
  accept `scheduled` for symmetry with `ProjectStatusUpdate`'s pattern, but
  whether to allow it is an open decision.

## 4. RBAC contract

`require_role(UserRole.OWNER, UserRole.STAFF)` on all three routes — create,
list, and status-transition. No route is Owner-only; this is routine
day-to-day scheduling, not a tenant-control action (see finding above).

## 5. Tenant-isolation contract

- `POST`/`GET .../projects/{project_id}/appointments`: tenant-scope the
  Project lookup first (`crud.get_project_by_id(db, project_id,
  tenant_id)`), `404` if absent/cross-tenant, before touching
  `Appointment` at all — Tenant B can never create or list an appointment
  against Tenant A's Project, because the Project itself is invisible to
  them.
- `PATCH /appointments/{id}/status`: tenant-scope the Appointment lookup
  directly (`crud.get_appointment_by_id(db, appointment_id, tenant_id)`),
  `404` if absent/cross-tenant — no need to re-derive tenant ownership
  through `project_id` since `Appointment.tenant_id` is set once at
  creation and is itself the source of truth, same as every other child
  table's own `tenant_id` column.

## 6. Activity contract

New `ActivityType.SITE_VISIT_SCHEDULED = "site_visit_scheduled"` this
sprint, emitted once per successful creation — safe content only (e.g.
`description=f"Project {project.id} — visit scheduled for
{appointment.scheduled_at.isoformat()}"`, no customer PII).

**Recommend deferring `site_visit_completed`/`site_visit_cancelled` to a
later cycle within this same sprint, not skipping them outright** — the
locked TDD sequence below treats them as their own RED/GREEN step after the
creation path is proven, consistent with how Sprint 020 shipped
`quote_approved` before `quote_handed_off` as two separate activity events
in two separate cycles rather than all at once. This is a recommendation
for cycle *ordering* within Sprint 022, not a scope cut — all three events
belong in this sprint.

## 7. Atomicity

Creation is a two-write operation (`Appointment` row + `ActivityLog` row) —
structurally identical in shape to Sprint 021's original two-write
`Customer`+`ActivityLog` problem before atomicity was added, and Sprint 021
already generalized the fix: `crud.create_activity_log` and
`activity_service.log`/`PostgresActivityRepository.add` all accept an
additive `commit: bool = True` / `db: Session | None = None` parameter
(default preserves every existing caller). **This sprint's creation flow
should reuse that exact mechanism from the start** — `crud.create_appointment(...,
commit=False)` then `activity_service.log(..., db=db)` then one
`db.commit()`, wrapped in the same try/`db.rollback()`/re-raise shape
`ProjectService.convert_to_customer` already established — rather than
re-litigating the atomicity question as a separate later RED/GREEN cycle
the way Sprint 021 had to. The status-transition endpoint is a single write
(no paired activity event proposed for `completed`/`cancelled` beyond what
§6 already flags as an open sub-decision), so it doesn't need the same
treatment unless that decision changes.

## 8. Frontend contract

On `apps/web/app/projects/[id]/page.tsx`:
- A "Schedule Site Visit" trigger button, visible when `role === "Owner" ||
  role === "Staff"` (no status/link gating the way Sprint 021's conversion
  action needed — an appointment can be scheduled against a Project in any
  status, there's no lifecycle restriction analogous to
  "`customer_id == null`").
- Clicking it reveals an inline form (same pattern as Sprint 021's
  "Convert to Customer"): a date/time input for `scheduled_at`, an optional
  Notes field, a "Save"/"Schedule" submit button.
- A "Site Visits" list below it: each appointment's `scheduled_at`
  (formatted via a new date+time variant of the existing
  `formatRelativeTime`/`toLocaleString` helpers), a status `Badge` (reusing
  the existing `Badge` component, same tone-mapping convention as
  `PROJECT_STATUS_TONE`), and "Mark Completed"/"Cancel" actions shown only
  on `scheduled` rows.
- New `apps/web/lib/api.ts` methods: `createAppointment(projectId, data)`,
  `getProjectAppointments(projectId)`, `updateAppointmentStatus(id,
  status)|completeAppointment(id)|cancelAppointment(id)` (exact naming an
  open decision below).
- New `apps/web/types/appointment.ts` mirroring the backend Pydantic shapes.

## 9. Date/time contract — the one genuinely new convention this sprint needs

**Storage**: `DateTime(timezone=True)` (already this repo's universal
column type for every existing timestamp) — Postgres stores it internally
as UTC regardless of what offset was submitted; SQLAlchemy/psycopg return a
timezone-aware Python `datetime`.

**API representation**: Pydantic serializes a timezone-aware `datetime`
field as an ISO 8601 string with explicit UTC offset (e.g.
`2026-09-15T14:00:00+00:00`) — no new serialization code needed, this is
FastAPI/Pydantic's existing default behavior, already implicitly exercised
by every `created_at`/`approved_at` field today. The one **new** discipline
this sprint must add: the incoming `scheduled_at` on `POST
.../appointments`'s request body **must be rejected if it lacks timezone
info** (a naive datetime is ambiguous — whose midnight?). FastAPI/Pydantic
v2 by default accepts a naive ISO string and treats it as-is without
attaching a timezone, which would silently create ambiguity; the request
model should either require an offset (Pydantic's `datetime` type already
distinguishes aware vs. naive at validation time — this needs one explicit
`field_validator` rejecting a naive value, the first of its kind in this
codebase, since nothing has taken a client-supplied datetime before) or
document why naive-is-acceptable if that turns out to be the frontend's
only realistic path (see open decision below on `datetime-local`).

**Frontend input**: no existing convention (first sprint to need one). The
plain-HTML `<input type="datetime-local">` is the natural fit for the
existing `Field`/`Input` component pair (already proven to pass through
arbitrary `type` values, e.g. `type="email"` in Sprint 021's conversion
form) — but it produces a **naive local-time string**
(`YYYY-MM-DDTHH:mm`, no offset), which must be explicitly converted to a
real timezone-aware value before `JSON.stringify`-ing it into the request
body: `new Date(localValue).toISOString()` converts the browser's
interpretation of that local string into a proper UTC ISO string with a
`Z` suffix — this conversion is the one piece of genuinely new frontend
code this sprint needs, and it directly resolves the naive-vs-aware
question above in the backend's favor (the frontend always sends an aware
value; the backend's validator exists to guard the API contract for any
other caller, not to accommodate the frontend's own naive intermediate
state).

**Display**: reuse the existing `toLocaleString(undefined, {...})` pattern
(four existing page files already do this for `created_at`) — renders in
the viewer's own local timezone, matching how this repo already displays
every other timestamp; no new display convention needed.

## 10. E2E contract

One new spec, `apps/web/e2e/site-visit-scheduling.spec.ts`, structural twin
of `enquiry-conversion.spec.ts`: create a synthetic Project via the real
API, log in through the real UI, open the real Project detail page,
schedule a visit through the real browser form, observe the real `POST
.../appointments` response via `page.waitForResponse` (never
intercepted/fulfilled), verify it renders, reload and verify persistence,
mark it completed through the UI, verify the status badge updates and
persists after another reload, then verify via the real API (`GET
.../appointments`, `GET /activity?type=site_visit_scheduled`) that exactly
the expected rows/events exist. No mocks anywhere, matching both existing
specs' explicit house rule.

## 11. Staging contract

Same discipline Sprint 021 established and `docs/STAGING_RUNBOOK.md` now
documents: deploy the exact reviewed commit via a clean `git archive`
export (not the working tree) to `simo-api-staging`/`simo-web-staging`;
verify `/health`/`/ready`; **explicitly verify `alembic current` ==
`alembic heads` via `railway ssh`** since this sprint, unlike Sprint 021,
*does* ship a real migration — health/ready must not be treated as proof it
applied; real-browser schedule/complete/cancel flow against the deployed
staging URLs; API-verified persistence and tenant isolation; RBAC-negative
check attempted but likely `BLOCKED BY STAGING FIXTURE SAFETY` again (same
reason as Sprint 021 — no approved path creates a role=None staging user);
run the existing staging smoke suite and record it honestly, including any
legitimately-blocked gates.

## 12. Migration plan

- **Current head**: `d3e7a9c1f204`.
- **Proposed new revision**: one additive migration, `create appointments
  table` — new table only, no changes to any existing table/column.
  Generate via `alembic revision --autogenerate` against the already-added
  `Appointment` model (same process every prior new-table migration in this
  repo used — Sprint 011's `invitations`, Sprint 013's `portal_links`,
  Sprint 016's `documents`), then hand-verify the generated constraint names
  are explicit (not autogenerate's anonymous defaults — Sprint 008's own
  documented lesson about why unnamed FK constraints make `downgrade()`
  unreliable).
- **Columns**: exactly the seven listed in §2 (`id, tenant_id, project_id,
  created_by_user_id, scheduled_at, status, notes, created_at`).
- **FKs**: `tenant_id → tenants.id`, `project_id → projects.id`,
  `created_by_user_id → users.id` — three explicitly-named constraints,
  matching `portal_links`' three-FK migration as the closest precedent.
- **Indexes**: `ix_appointments_tenant_id`, `ix_appointments_project_id`.
- **Nullability**: `tenant_id`, `project_id`, `created_by_user_id`,
  `scheduled_at`, `status` (has a server default so effectively always
  populated), `created_at` (server default) — all `NOT NULL`. Only `notes`
  nullable.
- **Downgrade**: drop the table (and its two indexes implicitly) — no data
  migration needed either direction, it's a brand-new table with no
  existing rows to preserve or backfill.
- **Verification**: `alembic upgrade head` → `downgrade -1` → `upgrade
  head` round-trip against the live local Postgres, plus `alembic check`
  confirming no model/migration drift, exactly Sprint 011/013/016's own
  audit pattern.

## 13. Explicit out of scope

- Google Calendar / Outlook Calendar sync, ICS generation, or any external
  calendar webhook.
- Customer self-service booking or rescheduling (no customer account/portal
  access to appointments at all this sprint — the read-only client portal,
  Sprint 013/016/017, is not extended here).
- Recurring appointments.
- A staff availability/conflict-detection engine.
- SMS/email reminders or any automated follow-up (that's Sprint 024's
  named territory).
- Route planning / multi-visit scheduling optimization.
- `assigned_user_id` / staff task-assignment (no precedent exists yet in
  this codebase — candidate for Sprint 023, Project Operations, not this
  sprint).
- Rescheduling a `scheduled_at` value once created (no `PATCH
  .../appointments/{id}` for editing the date/time — only the status
  transition endpoint exists this sprint; changing your mind about the
  time means cancelling and creating a new one).
- Reopening a `completed`/`cancelled` appointment back to `scheduled`.
- Any change to `Project.status` — scheduling or completing a visit never
  advances the Project's own pipeline stage, matching Sprint 021's identical
  "conversion never changes Project.status" precedent for the same reason
  (these are orthogonal concerns; a staff member still uses the existing
  `PATCH /projects/{id}/status` separately, by choice, when they decide the
  project has actually moved stage).

## 14. Open decisions (to resolve before the first RED)

1. **List ordering**: `GET .../appointments` ordered by `created_at DESC`
   (matching every other list endpoint's convention) or by `scheduled_at`
   (arguably more useful for an appointments list specifically — "what's
   coming up" vs. "what was added most recently")? Recommend `scheduled_at
   ASC` for upcoming-first usefulness, breaking from the literal
   `created_at DESC` convention deliberately, but this is a judgment call
   worth confirming rather than assuming.
2. **Status-transition symmetry**: should `PATCH .../status` technically
   accept transitioning back to `scheduled` (for API/schema symmetry with
   `ProjectStatusUpdate`), even though the frontend never offers it and
   it's listed as out of scope above? Recommend: the Pydantic enum lists
   all three values (schema honesty), but the *service* only permits
   `scheduled → completed` and `scheduled → cancelled`, rejecting any other
   transition (including a no-op re-set or reversing a terminal state) with
   `409` — mirroring `QuoteApprovalStateError`'s exact shape.
3. **Idempotency of the status transition**: if `PATCH .../status` is
   called twice with the same target status (e.g. double-clicking "Mark
   Completed"), should the second call be a `200` no-op (return the
   already-completed row) or a `409`? Sprint 021's precedent split on
   exactly this kind of question by contract type (idempotent for
   conversion, rejecting for the lifecycle guard) — recommend idempotent
   `200` here (a double-click retry safety net, matching the *reason*
   Sprint 021's conversion itself was made idempotent) rather than `409`,
   but this needs an explicit decision, not an assumed default.
4. **`site_visit_completed`/`site_visit_cancelled` activity events**: both
   in scope (per §6) — confirm before locking the TDD sequence whether
   `cancelled` truly deserves its own activity type or could reuse a single
   `SITE_VISIT_STATUS_CHANGED` event parameterized by the new status in its
   description. Recommend two distinct types (matches the existing
   one-type-per-domain-transition convention exactly, e.g. `QUOTE_APPROVED`
   vs. `QUOTE_HANDED_OFF` are two types for two transitions of the same
   underlying entity, not one generic `QUOTE_STATUS_CHANGED`).
5. **Naive-datetime rejection**: confirm the backend should hard-reject a
   naive `scheduled_at` (422) rather than silently assume UTC — recommended
   above, but worth locking explicitly since it's a new validation rule
   with no precedent to point to.
6. **Frontend API client method naming**: `updateAppointmentStatus(id,
   status)` (generic, mirrors `updateProjectStatus`) vs. two dedicated
   `completeAppointment(id)`/`cancelAppointment(id)` methods (more explicit
   call sites). No strong precedent either way — `updateProjectStatus` is
   generic; `handoffQuote`/`approveQuote` are dedicated. Recommend
   dedicated methods, matching the more recent (Sprint 020/021) precedent
   over the older (Sprint 006) one.

## 15. Proposed TDD sequence

1. **Model/migration RED** — a test asserting the `appointments` table
   exists with the expected columns (or simply: the first service-level RED
   below will fail at import/schema time until the model + migration land
   together, same as every prior new-table sprint did — Sprint 011/013/016
   never wrote a standalone "table exists" test, they went straight to
   endpoint-level REDs. Recommend following that same precedent rather than
   inventing a new intermediate step.)
2. **Create appointment RED → GREEN** — `POST
   .../projects/{id}/appointments` with a valid future `scheduled_at`
   returns `201`/`200`, persists, `status == "scheduled"`.
3. **Tenant isolation** — Tenant B creating/listing against Tenant A's
   Project → `404`, nothing persisted (likely GREEN-on-arrival regression
   coverage, same as Sprint 021's cross-tenant cycle, given the identical
   `get_project_by_id` precedent).
4. **RBAC** — same-tenant role=None user → `403` (likely GREEN-on-arrival
   regression coverage once `require_role` is wired in step 2, same as
   Sprint 021's RBAC cycle).
5. **List appointments** — `GET .../projects/{id}/appointments` returns
   only that project's own appointments, tenant-scoped.
6. **Status transition: complete** — `PATCH /appointments/{id}/status`
   `{status: "completed"}` → `200`, persists; invalid transition (e.g.
   already-cancelled → completed) → `409`.
7. **Status transition: cancel** — same shape as step 6, `{status:
   "cancelled"}`.
8. **Idempotent status-transition retry** — per open decision 3, a repeat
   call with the same target status is a `200` no-op, not a duplicate
   mutation or activity event.
9. **Activity: scheduled** — creation logs exactly one
   `site_visit_scheduled` event, tenant-scoped, safe content only.
10. **Activity: completed/cancelled** — each status transition logs its own
    event (per open decision 4), no duplicate on an idempotent retry.
11. **Atomicity** — creation's Appointment+ActivityLog write reuses Sprint
    021's `commit=False`/shared-session/rollback mechanism from the start
    (per §7) — likely proven via the same injected-failure `monkeypatch`
    technique Sprint 021 used, as its own explicit RED/GREEN cycle even
    though the mechanism is reused rather than invented, so the specific
    reuse is verified, not assumed.
12. **Frontend: schedule RED → GREEN** — "Schedule Site Visit" form,
    submits through the real API client, renders the created appointment.
13. **Frontend: status actions** — "Mark Completed"/"Cancel" buttons, same
    pattern.
14. **Frontend: failure/visibility hardening** — API-failure safety (no
    fake appointment attached, form stays retryable) and role-visibility
    regression coverage, mirroring Sprint 021's two hardening cycles.
15. **True Playwright E2E** — `site-visit-scheduling.spec.ts`, real
    browser/API/DB, no mocks.
16. **Staging** — deploy, verify Alembic revision via SSH (this sprint
    genuinely ships a migration, unlike Sprint 021), real browser flow,
    API-verified persistence, smoke suite.
17. **Docs** — `docs/SPRINTS/sprint-022.md` closeout evidence section,
    `docs/ROADMAP.md` status flip once actually done.
18. **Merge** — feature branch → `main`, same PR-based, explicit-merge-commit
    discipline Sprint 021 established (including checking CI on the exact
    merge commit, not just the feature branch's own last run).

## 16. Locked contract

The six open decisions from §14 above are resolved below and are binding —
later RED/GREEN cycles implement them, they do not renegotiate them.

### Decision 1 — list ordering

- **Decision**: how should `GET .../appointments` order its results?
- **Options identified**: `created_at DESC` (matches every other list
  endpoint's literal convention) vs. `scheduled_at ASC` (upcoming-first,
  more useful for what this specific list is *for*).
- **Selected**: `scheduled_at ASC`.
- **Reason**: the whole point of an appointments list is "what's coming up"
  — ordering by insertion time instead would be actively less useful for
  identical implementation cost (one `order_by` clause either way).
- **LOCKED.**

### Decision 2 — status-transition schema vs. service symmetry

- **Decision**: should the status-update request schema accept all three
  status values (`scheduled|completed|cancelled`) for symmetry with
  `ProjectStatusUpdate`, even though reverting to `scheduled` is out of
  scope?
- **Options identified**: (a) schema allows all three, service enforces the
  real rule; (b) schema itself only allows the two valid targets
  (`completed|cancelled`).
- **Selected**: (b) — the request schema only accepts `completed` or
  `cancelled` as the target status.
- **Reason**: smallest coherent contract — there is no path in this sprint
  that ever needs to submit `scheduled` as a target, so a schema that can't
  even express the invalid request is simpler than a schema that expresses
  it and then a service that rejects it. (`ProjectStatusUpdate`'s broader
  schema exists because *every* project status is a valid PATCH target in
  that domain; this domain has exactly two valid targets, so the narrower
  schema is the more honest one, not a divergence from convention.)
- **LOCKED.**

### Decision 3 — idempotency of a repeated status transition

- **Decision**: if `PATCH .../status` is called twice with the *same*
  target status once already terminal, is the second call a `200` no-op or
  a `409`? (Distinct from attempting to cross *between* the two terminal
  states, or revert to `scheduled` — those are always `409`, per the
  "completed and cancelled are terminal" constraint.)
- **Options identified**: idempotent `200` (double-click/retry safety net,
  same reasoning Sprint 021's conversion retry used) vs. `409` on every
  repeat call regardless of target.
- **Selected**: idempotent `200` — a repeat call with the *same* status as
  the appointment's current (terminal) status returns that unchanged row,
  `200`, no new activity event. A call with the *other* terminal status, or
  a revert to `scheduled`, is `409` in every case (this is what "terminal"
  means here — you cannot leave a terminal state for a *different* state).
- **Reason**: a UI double-click or network retry on "Mark Completed" is a
  fully expected client-side event, not an error condition — matching why
  Sprint 021 made its own repeat-call case idempotent rather than a hard
  reject.
- **LOCKED.**

### Decision 4 — one vs. two activity types for completed/cancelled

- **Decision**: should completing and cancelling a visit share one generic
  `SITE_VISIT_STATUS_CHANGED` event, or get their own distinct types?
- **Options identified**: one generic type parameterized by the new status
  in its description, vs. two distinct `ActivityType` members.
- **Selected**: two distinct types — `SITE_VISIT_COMPLETED` and
  `SITE_VISIT_CANCELLED`.
- **Reason**: matches the established one-type-per-domain-transition
  convention exactly (`QUOTE_APPROVED` vs. `QUOTE_HANDED_OFF` are two types
  for two transitions of the same `Quote`, not one generic
  `QUOTE_STATUS_CHANGED`) — no precedent anywhere in this codebase for a
  parameterized generic activity type.
- **LOCKED.**

### Decision 5 — naive-datetime rejection

- **Decision**: should the API reject a `scheduled_at` submitted without
  timezone/offset information?
- **Options identified**: reject (422) vs. silently assume a timezone
  (e.g. UTC) for a naive value.
- **Selected**: reject — a naive `scheduled_at` on `POST
  .../appointments` fails Pydantic validation with `422`.
- **Reason**: directly required by the locked constraint that `scheduled_at`
  "must be timezone-aware at the API boundary" — silently assuming a
  timezone would be exactly the ambiguous-naive-storage outcome that
  constraint exists to prevent, and there is no existing precedent in this
  codebase for accepting a client-supplied datetime at all, so there is no
  competing convention to preserve.
- **LOCKED.**

### Decision 6 — frontend API client method naming

- **Decision**: one generic `updateAppointmentStatus(id, status)` vs. two
  dedicated `completeAppointment(id)`/`cancelAppointment(id)` methods.
- **Options identified**: generic (mirrors the older `updateProjectStatus`
  precedent) vs. dedicated (mirrors the more recent `approveQuote`/
  `handoffQuote` precedent).
- **Selected**: dedicated methods — `completeAppointment(id)` and
  `cancelAppointment(id)`.
- **Reason**: matches the more recent convention (Sprint 020/021) over the
  older one (Sprint 006), and reads more clearly at each call site than a
  generic status string would for exactly two possible actions.
- **LOCKED.** (Frontend-only; not exercised by Sprint 022's first backend
  RED.)

## LOCKED CONTRACT

- **Entity / table**: `Appointment` / `appointments`.
- **Fields**: `id (UUID, PK), tenant_id (UUID, NOT NULL, FK → tenants.id),
  project_id (UUID, NOT NULL, FK → projects.id), created_by_user_id (UUID,
  NOT NULL, FK → users.id), scheduled_at (DateTime(timezone=True), NOT
  NULL), status (String, NOT NULL, server_default "scheduled"), notes
  (String, nullable), created_at (DateTime(timezone=True), server_default
  now())`. No `updated_at` (no table in this schema has one).
- **Project relationship**: `project_id` only — the sole FK relationship.
  No `customer_id` on `Appointment`; the customer is reached, when needed,
  via `project_id → Project.customer_id`, avoiding the exact duplication
  the discovery pass ruled out.
- **User relationship(s)**: `created_by_user_id` only (audit — who
  scheduled it), matching `Invitation.invited_by_user_id`/
  `PortalLink.created_by_user_id`/`Document.uploaded_by_user_id`'s
  identical shape. No `assigned_user_id` — no task-assignment precedent
  exists anywhere in this codebase yet; that's Sprint 023 territory
  (Project Operations), not pulled forward here.
- **tenant_id strategy**: `NOT NULL` from creation (no anonymous-creation
  path exists for this entity, unlike `Customer`/`Project`/`Quote`'s
  nullable columns, which exist for reasons — anonymous quotes, legacy
  rows — that don't apply to a brand-new, always-authenticated-caller
  table).
- **Statuses**: `scheduled` (initial/default) → `completed` | `cancelled`
  (both terminal). No `rescheduled`, `no_show`, `confirmed`, or
  `in_progress` — none required by anything in scope.
- **Date/time rule**: stored as `DateTime(timezone=True)` (this repo's
  universal timestamp column type); the API rejects a naive
  `scheduled_at` on input with `422` (Decision 5); responses serialize it
  as an ISO 8601 string with explicit UTC offset (Pydantic's existing
  default behavior, no new serialization code).
- **Create endpoint**: `POST /api/v1/projects/{project_id}/appointments` —
  body `{scheduled_at: datetime, notes?: string}`; response `AppointmentOut`
  `200`/`201` (exact status code decided at RED-writing time by matching
  the closest sibling convention — `POST /projects` returns `201`, `POST
  /quotes/{id}/handoff` returns `200`/`201`, both accepted by their own
  tests; the RED below locks whichever this endpoint actually returns).
- **List/read endpoint**: `GET /api/v1/projects/{project_id}/appointments`
  — tenant-scoped, `scheduled_at ASC` (Decision 1), returns
  `list[AppointmentOut]`.
- **Status-update endpoint**: `PATCH /api/v1/appointments/{appointment_id}/status`
  — body `{status: "completed" | "cancelled"}` (Decision 2's narrowed
  schema), `200`, idempotent on a same-status repeat, `409` on any other
  transition (Decision 3).
- **`AppointmentOut` fields**: `id, tenant_id, project_id,
  created_by_user_id, scheduled_at, status, notes, created_at` — matches
  `DocumentOut`/`PortalLinkOut`'s shape (both expose `tenant_id` and their
  creator id directly), the closer structural precedent for a
  child-of-parent audit entity than `CustomerOut`/`ProjectOut` (which
  expose neither).
- **RBAC**: `require_role(UserRole.OWNER, UserRole.STAFF)` on all three
  routes — create, list, and status-update. No route is Owner-only.
- **Tenant isolation**: create/list tenant-scope the parent Project first
  (`crud.get_project_by_id(db, project_id, tenant_id)`, `404` if
  absent/cross-tenant) before touching `Appointment` at all; the
  status-update route tenant-scopes the `Appointment` lookup directly via
  its own `tenant_id` column. Tenant B can never create, list, or update an
  appointment through Tenant A's Project or Appointment id — both paths
  404 before any Appointment row is read or written.
- **Activity events**: `SITE_VISIT_SCHEDULED` (on creation),
  `SITE_VISIT_COMPLETED` (on `→ completed`), `SITE_VISIT_CANCELLED` (on
  `→ cancelled`) — one per real transition, none on an idempotent repeat
  (Decision 4).
- **Transaction boundary**: creation's `Appointment` row + its
  `SITE_VISIT_SCHEDULED` `ActivityLog` row are one logical transaction from
  the first GREEN — `crud.create_appointment(..., commit=False)` then
  `activity_service.log(..., db=db)` then one `db.commit()`, wrapped in the
  same try/`db.rollback()`/re-raise shape `ProjectService.convert_to_customer`
  established in Sprint 021. Each status-transition is a single write (no
  paired write beyond its own activity event, which uses the same
  established pattern).
- **Frontend scope**: `apps/web/app/projects/[id]/page.tsx` gains "Schedule
  Site Visit" (Owner/Staff, no status/link gating) → inline date/time +
  notes form → "Site Visits" list (`scheduled_at ASC`) with status badges
  and "Mark Completed"/"Cancel" on `scheduled` rows only.
  `apps/web/lib/api.ts` gains `createAppointment`, `getProjectAppointments`,
  `completeAppointment`, `cancelAppointment` (Decision 6). Not touched in
  this cycle — later cycles per §15's TDD sequence.
- **E2E scope**: `apps/web/e2e/site-visit-scheduling.spec.ts` — real
  browser/API/DB, no mocks, schedule → observe real response → renders →
  reload persists → complete → persists after reload → API-verified via
  `GET .../appointments` and `GET /activity?type=site_visit_scheduled`.
  Not implemented in this cycle.
- **Explicit out-of-scope** (unchanged from §13, restated as binding):
  Google/Outlook calendar sync, ICS generation, customer self-booking or
  rescheduling, recurring appointments, staff availability/conflict
  engine, SMS/email reminders or automated follow-up, route planning,
  `assigned_user_id`, editing `scheduled_at` after creation, reopening a
  terminal status, any change to `Project.status`, and any Sprint 023
  (Project Operations) work of any kind.

### Verdict

- **Six decisions resolved: YES** — all binding for implementation.
- **Sprint 022 contract locked: YES.**
- **Ready for the first backend RED: YES** — proceeding to
  `test_appointments.py`'s creation contract.

## 17. End-to-end delivery closeout

Full vertical delivered per the locked contract above: designed →
implemented → tested → browser-E2E verified → staging verified →
documented. Commits below are all on `sprint-022-appointment-site-visit`.

### Git history

| Stage | Commit | Summary |
|---|---|---|
| Discovery | `15b71c8` | Discovery doc (§1–15) |
| Contract lock | `b4edae5` | Six decisions locked (§16, LOCKED CONTRACT) |
| First RED | `34f9786` | `test_appointments.py` creation contract — confirmed `404` (route missing) |
| Backend GREEN | `80e44ae` | `Appointment` model, CRUD, service, router, activity types, migration `3a56d7ee9bba` |
| Backend hardening | `7db7482` | Tenant isolation, RBAC, list ordering, status transitions (idempotent/409), activity, atomicity — plus a latent `app/core/errors.py` fix (see below) |
| Frontend GREEN | `9b8330d` | "Site Visits" section on the project detail page — schedule form, list, Complete/Cancel |
| True E2E | `a85cced` | `e2e/site-visit-scheduling.spec.ts` — real browser/API/DB |
| Contract-conformance fix | `4052609` | Renamed frontend API client methods to match locked Decision 6 (`completeAppointment`/`cancelAppointment`/`getProjectAppointments`, not the generic shape the first pass had drifted to) — no behavior change |

### Domain details

Exactly as locked in §16 (LOCKED CONTRACT), implemented without further
deviation except the Decision 6 naming catch above: `Appointment` /
`appointments` table, `scheduled` → `completed`/`cancelled` lifecycle, no
`updated_at`, no `customer_id`, no `assigned_user_id`.

### API details

- `POST /api/v1/projects/{project_id}/appointments` → `201`
- `GET /api/v1/projects/{project_id}/appointments` → `200`, `scheduled_at ASC`
- `PATCH /api/v1/appointments/{appointment_id}/status` → `200` (including
  idempotent same-status retry), `409` on a genuine conflicting transition
- Naive `scheduled_at` → `422` (see error-handler fix below)
- Cross-tenant access on any of the three routes → `404`
- Caller without `OWNER`/`STAFF` → `403`

### Security details

- Tenant isolation: create/list tenant-scope the parent Project first;
  status-update tenant-scopes the Appointment row directly. Verified both
  in `tests/test_appointments.py` and live against staging (§ below).
- RBAC: `require_role(OWNER, STAFF)` on all three routes, verified with a
  real `role=None` user (not a fabricated role) in both the backend suite
  and the frontend visibility tests.
- No new secrets, no new PII fields, no change to existing auth/JWT flow.

### A latent bug found and fixed (not scope creep)

Sprint 022 is the first sprint whose Pydantic model raises a plain
`ValueError` from a `field_validator` (the `scheduled_at` timezone check).
`app/core/errors.py`'s `validation_exception_handler` passed pydantic's raw
`exc.errors()` straight to `JSONResponse`, but such an error's `ctx.error`
is a live exception object, which plain `json.dumps` can't serialize —
every naive-datetime `422` was actually crashing into an unhandled `500`.
Fixed by passing the errors through `jsonable_encoder` first (`7db7482`).
This was required for Sprint 022's own locked contract (Decision 5) to
actually work, not an unrelated cleanup.

### Activity details

`SITE_VISIT_SCHEDULED` on creation, `SITE_VISIT_COMPLETED` /
`SITE_VISIT_CANCELLED` on their respective real transitions, none on an
idempotent repeat — verified by dedicated tests and independently
confirmed live on staging via `GET /activity?type=...`.

### Atomicity details

Reused Sprint 021's caller-owned-transaction pattern
(`commit=False`/`db=`/`rollback`+re-raise). Both create+activity and
transition+activity are covered by failure-injection tests
(`monkeypatch.setattr(activity_service, "log", ...)`) proving the
Appointment row/status change does not survive a failed activity write.

### Frontend details

`apps/web/app/projects/[id]/page.tsx` — "Site Visits" section, Owner/Staff
gated identically to Convert to Customer: list (empty state, status
badges), "Schedule Site Visit" form (`datetime-local` → tz-aware ISO string
via `toISOString()`), "Complete"/"Cancel" on `scheduled` rows only, all
mutations server-response-authoritative (never optimistic), failure-safe
(error surfaced, form/state preserved, action re-enabled for retry).

### Test totals

- Backend: `tests/test_appointments.py` — 14 passed. Full suite — 382
  passed, 1 skipped, 0 failed (regression-clean).
- Frontend: `apps/web/app/projects/[id]/page.test.tsx` +
  `app/quotes/[id]/page.test.tsx` — 15 passed (2 test files). Typecheck,
  lint, `test:runtime-config`, `test:docker-contract` all clean.
- True E2E (local, real browser/API/DB): 3 passed —
  `enquiry-conversion.spec.ts`, `quote-handoff.spec.ts` (regression),
  `site-visit-scheduling.spec.ts` (new).

### CI

Green on every pushed commit's exact HEAD, including the final
Decision-6-fix commit `4052609` (frontend/backend/e2e jobs all `success`).

### A local-environment-only build artifact (not a code defect)

`next build`/`next dev` failed with a Turbopack workspace-root-inference
error when run from this sprint's git worktree
(`.../AppData/Local/Temp/.../scratchpad/sprint022`), but succeeded cleanly
from both the original repo checkout and a shallow `git archive` export of
the identical commit — and GitHub Actions CI's `frontend`/`e2e` jobs (a
clean, shallow checkout) both passed. This is a path-depth/sibling-lockfile
artifact of the specific Windows Temp worktree location, not a defect in
the shipped code; local verification (build, E2E) was completed from clean
shallow exports instead, per `docs/STAGING_RUNBOOK.md`'s existing
clean-commit-export precedent.

### Staging evidence

- Deployed via the documented clean-commit `git archive` + `railway up`
  procedure (`docs/STAGING_RUNBOOK.md`) at commit `4052609` (frontend-only
  change from `a85cced`'s already-deployed backend; the API deploy shipped
  `4052609`'s tree too since both services deploy from the same export).
- `simo-api-staging` deployment `38ef4853…`, `simo-web-staging` deployment
  `c5e88232…`, both `SUCCESS`, both `online`, 0 issues, 0 recent failures.
- Public `/health` → `200`, `/ready` → `200`.
- **Migration-drift gap recurred a third time** (same class of issue
  `docs/STAGING_RUNBOOK.md` already documents from Sprint 020): the CLI
  deploy's pre-deploy command did not apply migration `3a56d7ee9bba`;
  `alembic current` read `d3e7a9c1f204` post-deploy. Remediated exactly per
  the runbook's prescribed procedure — `railway ssh ... -- alembic upgrade
  head`, then re-verified `alembic current` == `alembic heads` ==
  `3a56d7ee9bba`. No runbook change needed; the already-mandatory
  post-deploy verification step is precisely what caught this.
- Real browser flow verified against staging (fresh synthetic tenant, no
  mocks): signup → new Project → Schedule Site Visit → visible in list →
  **persists across reload** → Complete → status flips, actions removed →
  **persists across a second reload**.
- Security checks against the live staging API: a second synthetic tenant
  got `404` on create/list/status-update against tenant A's
  Project/Appointment (3 checks); an invalid `completed → cancelled`
  transition returned `409`; a repeated `completed → completed` returned
  `200` unchanged (idempotent).
- Activity verified live: exactly one `site_visit_scheduled` and one
  `site_visit_completed` record for the test appointment.
- Staging smoke suite (`scripts/staging/smoke.py`): 14 passed, 0 failed, 8
  blocked (all 8 are the pre-existing `--quote-material`/`--quote-thickness`
  optional gate, not run — same as Sprint 021's recorded smoke run, not a
  new gap).
- Per `docs/STAGING_RUNBOOK.md`'s browser-session-isolation lesson: the
  verification browser tab's `localStorage` was checked for a stray token
  before starting (none found — the topbar's apparent "Simo / Owner" text
  is static placeholder UI in `UserProfileMenu.tsx`, unrelated to auth
  state) and cleared again after finishing.

### Safety confirmations

- Production was not touched — `simo-os/production` has zero deployed
  services throughout this sprint.
- No destructive git operations — every commit is additive, pushed with a
  plain `git push` (no force), no rebases, no squashes.
- No secrets, tokens, or customer data committed or logged.

### Final status

**Sprint 022 is functionally CLOSED** pending only the mechanical final
merge gate (CI check on this exact HEAD, PR open/update, explicit merge
commit, post-merge `main` CI verification) — Phase 21/22 of the delivery
plan, executed immediately after this doc commit. Sprint 023 does not
start until that merge lands and this status line is updated to "CLOSED —
merged to main."
