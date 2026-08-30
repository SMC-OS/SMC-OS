# Sprint 022 — Appointment / Site Visit Scheduling (Discovery / Contract Lock)

Status: **DISCOVERY ONLY — no production code, no migrations, no tests
written.** Locked per `docs/ROADMAP.md`'s reconciled v1.0 sequence
(`docs/ROADMAP.md`, reconciliation merged `843439d`).

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
