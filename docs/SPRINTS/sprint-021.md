# Sprint 021 — Enquiry → Customer Conversion (Discovery / Contract Lock)

Status: **CONTRACT LOCKED — the three open questions below are resolved. No
production code, no migrations written yet; first TDD RED is next.**

Branch: `sprint-021-enquiry-customer-conversion`
Baseline: `main` @ `77a5a25` (Sprint 020 merge, confirmed via `git rev-parse HEAD`)

## 1. Domain reality check

There is **no `Enquiry` entity, table, or `app/enquiries/` module anywhere in the
codebase.** A repo-wide search for `enquiry|enquiries|Enquiry|lead|Lead` turned up
exactly one real usage: `ProjectStatus.ENQUIRY = "enquiry"`
(`app/projects/models.py`), the default status every new `Project` row is created
with (`app/projects/service.py::ProjectService.create`, unconditionally passes
`ProjectStatus.ENQUIRY.value`).

So in this codebase, **"an Enquiry" already means "a `Project` row in status
`enquiry`."** `Project.customer_id` is nullable, and `ProjectCreate` lets a caller
omit `customer_id` entirely — the existing "New Project" form
(`apps/web/app/projects/new/page.tsx`) already supports creating a project with
`customer_id` left blank ("— No customer linked —"). That unlinked, freshly
created, status=`enquiry` Project **is** the enquiry/lead this sprint targets —
not a new table.

This reframes the sprint from "build an Enquiry subsystem" to "add a
Customer-conversion action to the existing Project record, for the case where it
has no `customer_id` yet." This mirrors Sprint 020's Quote→Project `handoff()`
almost exactly, just one relationship over (Project→Customer instead of
Quote→Project), and that sprint's code/tests are the direct template for this
one's contract, RBAC, idempotency, and activity shape.

## 2. Current implemented behavior (verified by reading, not assumed)

### Backend — Customer (`app/customers/`)
- `Customer` (`app/database/models.py`): `id, tenant_id (nullable FK, indexed),
  name, email (nullable, no unique constraint), phone (nullable, no unique
  constraint), created_at`.
- `CustomerService.create()` (`app/customers/service.py`) does a bare
  `crud.create_customer(...)` — **no email/phone lookup exists anywhere in
  `app/database/crud.py`**, so there is zero duplicate-customer detection today,
  at the DB level (no unique index/constraint — confirmed via
  `alembic/versions/a8d91098a01e_add_tenant_id_indexes_for_isolation.py`, which
  only adds `ix_customers_tenant_id`) or the application level.
- `app/customers/router.py`: `GET /customers`, `GET /customers/{id}`,
  `POST /customers` — all behind bare `Depends(get_current_user)` only. **No
  `require_role(...)` anywhere on this router** — any authenticated user
  (Owner or Staff) can create a customer today.
- Activity: `create()` logs `ActivityType.CUSTOMER_ADDED` once per creation
  (`app/customers/service.py`), same "service logs its own ActivityEvent"
  convention as every other mutating service.
- Tenant isolation: `get_customer_by_id`/`list_customers` both filter by
  `tenant_id` (Sprint 012, ADR-029) — cross-tenant reads 404, matching the
  established convention exercised in `tests/test_customers.py`.

### Backend — Project (`app/projects/`)
- `Project` (`app/database/models.py`): `id, tenant_id, customer_id (nullable
  FK), quote_id (nullable, unique FK — Sprint 020 traceability convention),
  name, notes, status (default "enquiry"), created_at`. **No
  `converted_from_project_id`/similar traceability column exists** — Sprint 020's
  precedent for this is `Quote.id` living on `Project.quote_id`, not a reverse
  pointer.
- `ProjectService.create()` accepts an optional `customer_id`; if given, it must
  belong to the caller's tenant (`CustomerNotFoundError` → 404) — same
  cross-tenant-linking guard convention used by `QuoteService`.
- **No function exists to attach/change a Project's `customer_id` after
  creation.** `crud.py` has `update_project_status` only; there is no
  `update_project_customer` or equivalent. This is the core gap this sprint
  fills.
- `app/projects/router.py`: `GET /projects`, `GET /projects/{id}`,
  `POST /projects`, `PATCH /projects/{id}/status` — all behind bare
  `Depends(get_current_user)` only. **No `require_role(...)` on this router
  either** — unlike `app/quotes/router.py`'s `approve`/`handoff`, which Sprint 020
  gated with `require_role(UserRole.OWNER, UserRole.STAFF)`.
- Activity: `create()` logs `PROJECT_CREATED`. No `PROJECT_...CUSTOMER...` /
  `ENQUIRY_CONVERTED` activity type exists yet
  (`app/activity/models.py::ActivityType` currently has 11 members, most
  recently `QUOTE_HANDED_OFF` from Sprint 020).

### Relationship / conversion behavior today
**None.** A Project with `customer_id = NULL` stays that way forever unless
someone edits the DB directly — there is no API, service method, or UI action
that turns an unlinked enquiry-Project into one with a real linked Customer.
`ProjectDetailPage` (`apps/web/app/projects/[id]/page.tsx`) already renders
`Customer: —` for this exact case (line 122-124) but offers no action from
there.

### Tenant isolation
Established, consistent pattern across Customer/Project/Quote: every table has
`tenant_id`, every `crud.get_*_by_id` filters by it, cross-tenant lookups 404
(never 403 — "hide existence," per `test_get_project_cross_tenant_returns_404`
and its Customer/Quote equivalents). Sprint 021's new conversion endpoint must
follow the same convention: tenant-scoped lookup of the Project, 404 if it
belongs to another tenant.

### RBAC
`require_role()` (`app/auth/dependencies.py`, Sprint 010) exists and is proven
in production use on `app/quotes/router.py`'s `approve`/`handoff` routes
(`require_role(UserRole.OWNER, UserRole.STAFF)`, Sprint 020,
`tests/test_quote_handoff.py::test_non_owner_staff_user_cannot_hand_off_an_approved_quote`
is the exact test-shape template). It is **not** applied to `app/customers/` or
`app/projects/` routers today. Sprint 021's conversion endpoint should use the
same `require_role(UserRole.OWNER, UserRole.STAFF)` gate as the Sprint 020
handoff, since it is the same class of action (an enquiry becoming a committed
CRM record).

### Activity logging
Fully consistent "service logs its own ActivityEvent" convention, one record
per mutating action, tenant-scoped. A conversion needs its own new
`ActivityType` member (naming choice below), not reuse of `CUSTOMER_ADDED` or
`PROJECT_CREATED` — same reasoning Sprint 020 gave for introducing
`QUOTE_HANDED_OFF` instead of reusing `PROJECT_CREATED`.

### Frontend
- `apps/web/app/projects/[id]/page.tsx`: renders customer link/`"—"`, has a
  status-advance button (`PATCH .../status`) but nothing customer-related.
- `apps/web/app/customers/new/page.tsx`: standalone customer-creation form, not
  reachable from a project context.
- `apps/web/lib/api.ts`: has `createCustomer`, `createProject`,
  `updateProjectStatus`, `handoffQuote` (Sprint 020's exact precedent —
  `POST /quotes/{id}/handoff` → `Project`). **No conversion-equivalent client
  method exists** (e.g. no `convertProjectToCustomer`/`linkProjectCustomer`).
- `apps/web/e2e/`: exactly one spec, `quote-handoff.spec.ts` — the direct
  structural template for this sprint's own e2e spec.

### Existing tests
`tests/test_customers.py` and `tests/test_projects.py` cover creation,
listing, get-by-id, tenant isolation, and (`test_projects.py`) status
advancement/cross-tenant status guard. **Neither file, nor any other test file,
covers linking an existing Project to a newly created Customer.**
`tests/test_quote_handoff.py` is the closest analog and the direct pattern
source for RED tests in this sprint (idempotency, status guard, cross-tenant
404, RBAC 403, activity-record assertions).

### Existing migrations
15 revisions, current head `d3e7a9c1f204` (matches Sprint 020 handoff's
`git log --oneline` note and today's `alembic heads` output). No migration
currently touches `customers.email`/`customers.phone` uniqueness or adds any
`Project` traceability column beyond Sprint 020's `quote_id`.

## 3. Gaps (what's missing for the target slice)

- No backend action (service method + route) to attach a `customer_id` to an
  existing Project.
- No `crud.update_project_customer(...)`-equivalent function.
- No duplicate-customer detection at all (no email/phone lookup, no unique
  constraint) — converting an enquiry today could silently create N duplicate
  Customer rows for the same real person if run twice, or if two enquiries
  share contact details. This did not matter before because nothing chained a
  second write off of customer creation; a conversion action makes it matter.
- No RBAC on the Project/Customer routers to gate this kind of write.
- No new `ActivityType` for this transition.
- No re-conversion / duplicate-conversion guard (the Sprint 020 idempotency
  pattern — "second call returns the existing result, doesn't create a second
  row" — has no equivalent here yet).
- No frontend affordance anywhere to trigger conversion.
- No API client method.
- No e2e coverage.

## 4. Locked Sprint 021 contract (smallest vertical slice)

The three points flagged as open questions in the discovery pass are now
resolved as follows. These are binding — later RED/GREEN cycles implement
them, they do not renegotiate them.

- **Endpoint:** `POST /api/v1/projects/{project_id}/convert-to-customer`.
  Request body supplies the Customer fields already accepted by the existing
  Customer model/API (`CustomerCreate`: `name`, optional `email`, optional
  `phone`). Mirrors `POST /quotes/{id}/handoff`'s shape (an action-suffixed
  sub-resource on the source record, not a new top-level endpoint).
- **Source status (Decision 1):** conversion is allowed **only** when
  `Project.status == "enquiry"`. If the tenant-scoped Project exists but its
  status is anything else, the endpoint returns **`409 Conflict`** — no
  Customer is created, no field on the Project changes. Conversion links the
  contact identity; it does **not** advance the Project lifecycle —
  `Project.status` stays `"enquiry"` after a successful conversion too (a
  separate `PATCH /projects/{id}/status` call remains the only way to move a
  project's status, unchanged from today).
- **Repeat conversion (Decision 2):** conversion is **project-level
  idempotent**. If the tenant-scoped Project already has a non-null
  `customer_id`, the endpoint does not create another Customer — it loads the
  existing Customer (tenant-scoped) and returns it with **`200`**. A normal
  retry or UI double-click therefore always returns the same Customer, never
  a second one. This sprint does **not** implement global customer
  deduplication by email or phone, and does **not** add a unique constraint
  on `Customer.email`/`Customer.phone` — those stay exactly as they are today
  unless a later, explicit contract requires otherwise.
- **Response shape (Decision 3):** the endpoint returns the existing
  `CustomerOut` shape (`app/customers/models.py`) — not a `ProjectOut`, and
  not a wrapper embedding both. Status is **`200`** for both the first
  successful conversion and every idempotent retry (not `201` on first
  success) — the Customer returned by the server is authoritative regardless
  of which of the two paths produced it.
- **Traceability:** unchanged from the discovery pass — the link *is*
  `Project.customer_id -> Customer.id`. No reverse `Customer -> Project`
  pointer and no new `Enquiry` table are required.
- **Permissions:** `require_role(UserRole.OWNER, UserRole.STAFF)`, same gate
  as `approve`/`handoff` in `app/quotes/router.py`.
- **Activity (later cycle, not first GREEN):** a new
  `ActivityType.ENQUIRY_CONVERTED` (or equivalent), logged exactly once per
  successful *first* conversion, tenant-scoped — same convention as
  `QUOTE_HANDED_OFF`. Not implemented in the first GREEN unless a test
  requires it there.
- **Frontend (explicitly deferred):** no frontend work happens in the first
  backend TDD cycle. Once the backend contract is GREEN, `ProjectDetailPage`
  gets a "Convert to Customer" affordance for the `customer_id == null`
  case, `apps/web/lib/api.ts` gets a client method, and
  `apps/web/e2e/enquiry-conversion.spec.ts` becomes the structural twin of
  `quote-handoff.spec.ts` — all as later cycles, not this one.

### Locked step-by-step behavior for the first successful conversion

1. Tenant-scope and load the Project.
2. Return `404` if the Project is absent or belongs to another tenant.
3. Require `Project.status == "enquiry"` — otherwise `409`.
4. Require the caller to be `OWNER` or `STAFF` — otherwise `403`.
5. If `Project.customer_id` already exists: load and return that existing
   tenant-scoped Customer, `200` — skip steps 6-7.
6. Otherwise, create one Customer from the supplied conversion payload
   (tenant-scoped).
7. Set `Project.customer_id` to that Customer's id.
8. Leave `Project.status == "enquiry"` (untouched).
9. Persist both the new/linked Customer and the updated Project.
10. Return the resulting Customer, `200`.
11. (Later cycle) emit exactly one `enquiry_converted` activity event on the
    first real conversion — not on idempotent retries.

## 5. First TDD RED

- **Exact test:** `tests/test_enquiry_conversion.py::test_staff_can_convert_an_unlinked_enquiry_project_into_a_customer`
  — arrange a tenant, an authenticated OWNER/STAFF user, and a `Project` in
  that tenant with `status == "enquiry"` and `customer_id is None`; act by
  calling `POST /api/v1/projects/{project_id}/convert-to-customer` with a
  valid Customer payload; assert `200`, that the response body is the
  resulting `CustomerOut` (submitted name/email/phone round-trip, tenant_id
  correct if exposed), that the persisted `Project.customer_id` now equals
  the returned Customer's id, that `Project.status` is still `"enquiry"`, and
  that exactly one new Customer row was created.
- **Expected missing behavior:** the route `POST
  /api/v1/projects/{id}/convert-to-customer` does not exist at all yet, so
  the test fails with `404` where `200` is expected — the smallest possible
  RED, same shape as Sprint 020's first handoff RED. A fixture, syntax, or
  schema-level failure is not a valid RED for this cycle.
- **Deliberately not tested yet** (later RED/GREEN cycles): repeat/idempotent
  conversion, the non-enquiry `409`, cross-tenant `404`, RBAC `403`,
  activity-record assertions, frontend, e2e, global email/phone duplicates.

## 6. Out of scope (this sprint)

- A separate `Enquiry` table/model.
- Global customer deduplication by email.
- Global customer deduplication by phone.
- A `Customer` merge/dedupe workflow.
- Anonymous/public lead intake (today's `POST /projects` stays auth-only;
  making enquiry creation itself public is a separate, much larger decision,
  parallel to ADR-023's public `/quote`/`/estimate`, and is not implied by
  "conversion").
- CRM pipeline redesign.
- Appointment scheduling.
- RBAC changes to the existing `app/customers/` or `app/projects/` routers'
  other routes (list/get/create/status-update stay exactly as they are).
- Any status transition beyond `"enquiry"` — conversion never changes
  `Project.status`.
- Frontend work in the first backend TDD cycle.

## Verdict

- **Contract locked: YES** — all three previously-open questions (source
  status restriction, repeat-conversion behavior, response shape) are
  resolved above and are binding for implementation.
- **Ready to begin Sprint 021 TDD: YES** — proceeding to the first RED test
  named in §5.
