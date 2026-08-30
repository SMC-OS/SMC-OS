# Sprint 021 — Enquiry → Customer Conversion

Status: **ENGINEERING COMPLETE — STAGING VERIFIED — READY TO MERGE.** Not yet
merged to `main` and not deployed to production — see
[Implementation evidence](#implementation-evidence) below for what was
actually run, and the discovery/contract-lock sections that follow (§1-6,
originally written before implementation started) for the reasoning behind
the design.

Branch: `sprint-021-enquiry-customer-conversion`
Baseline: `main` @ `77a5a25` (Sprint 020 merge, confirmed via `git rev-parse HEAD`)
Feature HEAD: `96f7448`

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

## Verdict (discovery/contract-lock pass)

- **Contract locked: YES** — all three previously-open questions (source
  status restriction, repeat-conversion behavior, response shape) are
  resolved above and are binding for implementation.
- **Ready to begin Sprint 021 TDD: YES** — proceeding to the first RED test
  named in §5.

## Implementation evidence

Engineering-complete at commit `96f7448` on `sprint-021-enquiry-customer-conversion`.
Every item below is backed by a command, test, or staging check actually run
during this sprint — nothing here is aspirational. TDD proceeded as one
RED/GREEN cycle per contract, each committed and pushed separately; commit
SHAs are cited so any claim here can be traced back to the exact diff that
produced it.

### Backend

- Endpoint: `POST /api/v1/projects/{project_id}/convert-to-customer`
  (`app/projects/router.py`), gated by `require_role(UserRole.OWNER,
  UserRole.STAFF)` — same convention as Sprint 020's `approve`/`handoff`.
  Request body is the existing `CustomerCreate` shape; response is the
  existing `CustomerOut` shape — no new schema introduced.
- First conversion: an unlinked, `status == "enquiry"` Project gets a new
  `Customer` created and linked, `200` — RED `865f2ed`, GREEN `cff5db2`.
  Covered by `tests/test_enquiry_conversion.py::test_staff_can_convert_an_unlinked_enquiry_project_into_a_customer`.
- Idempotency: a repeat conversion on an already-linked Project returns the
  existing Customer (tenant-scoped lookup via `Project.customer_id`), `200`,
  never creates a second Customer or changes the link — RED `ddaacc5`, GREEN
  `4fac247`. `test_repeat_conversion_returns_the_same_customer_without_creating_another`.
- Lifecycle guard: conversion is only allowed while `Project.status ==
  "enquiry"`; any other status returns `409` via a new
  `ProjectNotInEnquiryStateError` (service-raises / router-maps convention,
  same as `QuoteApprovalStateError`), and never mutates the Project — RED
  `5ca8069`, GREEN `a97dff3`. `test_conversion_rejects_a_non_enquiry_project`.
  The status check runs *before* the idempotency short-circuit, so an
  already-linked Project that has since advanced past `"enquiry"` is still
  rejected, not idempotently returned.
- Tenant isolation: Tenant B converting Tenant A's Project returns `404`
  (existing `crud.get_project_by_id(db, project_id, tenant_id)` already hides
  cross-tenant Projects — no production change was needed here, verified as
  regression coverage) — `de95eff`.
  `test_conversion_of_another_tenants_project_returns_404`.
- RBAC: a same-tenant, role-less (`role=None`) user gets `403` (existing
  `require_role` already covered this from the very first GREEN — no
  production change needed, verified as regression coverage) — `a6426da`.
  `test_same_tenant_user_without_owner_staff_role_cannot_convert_enquiry`.
- Activity: new `ActivityType.ENQUIRY_CONVERTED = "enquiry_converted"`
  (`app/activity/models.py`). Exactly one event on the first real conversion
  only — the idempotent-retry early return happens before logging, so a
  retry never emits a duplicate. Safe content only: `title="Enquiry
  converted"`, `description=f"Project {project.id} converted to customer
  {customer.id}"` — no email/phone/name/PII — RED `b492eff`, GREEN `ee9eee2`.
  `test_successful_enquiry_conversion_creates_exactly_one_tenant_scoped_activity`.
- **Atomicity**: the first conversion's three writes (Customer creation,
  `Project.customer_id` link, `enquiry_converted` activity) are one logical
  transaction on the request-scoped `db` session — `crud.create_customer`,
  `crud.update_project_customer`, and `PostgresActivityRepository.add` each
  gained an additive `commit: bool = True` / `db: Session | None = None`
  parameter (default preserves every other existing caller's behavior
  unchanged); `ProjectService.convert_to_customer` calls all three with
  `commit=False`, then commits exactly once, rolling back and re-raising on
  any failure. Proven by injecting a `RuntimeError` into
  `activity_service.log` via `monkeypatch` and asserting the Customer and
  Project link do not survive — RED `f960892`, GREEN `57f153d`.
  `test_conversion_rolls_back_customer_and_project_link_if_activity_logging_fails`.
- No global email/phone dedupe, no `Customer` merge/dedupe workflow, no
  unique constraint added to `customers.email`/`customers.phone` — all
  explicitly out of scope per the locked contract (§4/§6 above) and
  unchanged this sprint.
- No migration: the entire vertical slice reuses existing nullable
  `Project.customer_id`; `ActivityType` is a plain Python enum backed by an
  unconstrained `String` column, so adding `ENQUIRY_CONVERTED` needed no
  schema change.

Full backend suite: **368 passed, 1 skipped, 0 failed** (`pytest`, from repo
root, against local Postgres, migrated to `d3e7a9c1f204` — unchanged from
Sprint 020's head, confirmed no drift throughout).

### Frontend

- `apps/web/lib/api.ts`: `convertProjectToCustomer(id, customer)` — `POST
  /projects/{id}/convert-to-customer`, existing `request<T>()` abstraction,
  no separate client.
- `apps/web/app/projects/[id]/page.tsx`: "Convert to Customer" visible only
  when `role === "Owner" || role === "Staff"` **and** `project.status ===
  "enquiry"` **and** `project.customer_id == null` — same
  local-`const canX`-gate pattern as `QuoteDetailPage`. Clicking it reveals
  an inline form (Full name/Email/Phone, same `Field`/`Input` components and
  labels as `customers/new/page.tsx`) with a "Save customer" submit button.
  On success: the server's returned Customer is applied to local state only
  *after* the awaited response (never optimistically) — `setCustomer`,
  `setProject({...project, customer_id: returnedCustomer.id})` — the
  Customer renders in the existing linked-customer area and the conversion
  action disappears. On failure: no Customer is attached, `Project` state is
  untouched, the form stays visible with the user's typed input intact, "Save
  customer" re-enables, and the existing error `Card` renders the failure —
  no new toast/modal/notification system. RED `30654a7`, GREEN `617bb0f`
  (happy path); failure-safety and visibility gating verified as regression
  coverage without any further production change — `c2d7010` (API-failure
  safety) and `9016e68` (Staff-positive, role=None-hidden,
  non-enquiry-hidden, already-linked-hidden).
- One incidental fix landed alongside the happy-path GREEN: the page's
  mount `useEffect` listed `router` in its dependency array, which — because
  a mocked/real `useRouter()` can return a new object identity — caused the
  effect (and its `load()` call) to re-fire on every re-render, silently
  overwriting freshly-applied conversion state with a stale re-fetch. Fixed
  by dropping `router` from the dependency array (it's only used for
  `router.replace("/login")`, not read reactively) — required for the locked
  RED test to pass without weakening the test itself.
- Frontend component suite: **9 passed** across `app/quotes/[id]/page.test.tsx`
  (3, unaffected) and `app/projects/[id]/page.test.tsx` (6: happy path,
  failure safety, Staff-positive, role=None-hidden, non-enquiry-hidden,
  already-linked-hidden).
- type-check: GREEN. lint: GREEN. runtime-config: 7 passed. Docker contract:
  5 passed. build: GREEN — all re-run after every backend and frontend
  change in this sprint, not just once at the end.

### E2E (true browser)

- `apps/web/e2e/enquiry-conversion.spec.ts` —
  `unlinked_enquiry_can_be_converted_to_customer_and_persists` — `96f7448`.
  Structural twin of Sprint 020's `quote-handoff.spec.ts`: real Chromium,
  real Next.js dev server, real FastAPI (`uvicorn app.main:app`), real local
  Postgres — no mocked fetch, router, or API client anywhere in the spec.
- Flow: unlinked enquiry Project created via the real API → real UI login →
  real Project detail page → click "Convert to Customer" → fill synthetic
  Full name/Email/Phone → click "Save customer" → `page.waitForResponse`
  *observes* (never intercepts/fulfills) the real `POST
  .../convert-to-customer` → `200` → returned Customer renders → action
  hidden → page reload → both still true.
- API-side verification (not renderable in the UI): `GET
  /api/v1/projects/{id}` confirms `customer_id`/`status`; `GET
  /api/v1/customers/{id}` confirms the three submitted fields; `GET
  /api/v1/activity?type=enquiry_converted` confirms exactly one event with
  the exact safe description.
- Playwright suite: **2 passed** (Sprint 020 `quote-handoff.spec.ts` + Sprint
  021 `enquiry-conversion.spec.ts`), run together every time this sprint's
  E2E was exercised.
- Synthetic E2E rows remain (no safe generic delete API exists for
  tenants/customers/projects) — identified by `Pytest E2E Sprint 021
  <run-id>` naming, same policy as Sprint 020's `pytest-e2e-sprint020-*` rows.

### Staging

- Deployed SHA: `96f7448`, both `simo-api-staging` and `simo-web-staging`
  (environment `staging` — the `production` environment has zero deployed
  services and was never touched, config or otherwise).
- **Deployment method**: a clean `git archive 96f7448` export, not the
  working tree — the working tree contains a pre-existing, ACL-locked
  directory (`.tmp-pytest-task10/`, present since before this sprint,
  unrelated to Sprint 021) that Railway's local uploader could not traverse
  (`Access is denied`, OS error 5, reproducible even via `icacls` on the
  directory itself). The clean archive sidesteps this entirely and is a
  stricter guarantee of "exactly this commit" than uploading the working
  tree would have been. See `docs/STAGING_RUNBOOK.md`'s new "Clean-commit
  staging deployment" note.
- `/health` / `/ready`: GREEN (`{"status":"healthy"}` /
  `{"status":"ready","database":"reachable"}`) — **not treated as migration
  proof**. Actual schema revision was independently verified via `railway
  ssh -i ~/.ssh/id_ed25519 --service simo-api-staging --environment staging
  -- alembic current` → `d3e7a9c1f204 (head)`, matching `alembic heads` →
  `d3e7a9c1f204 (head)`. Sprint 021 required no migration, and staging's
  revision matches exactly — no drift.
- Real browser flow (claude-in-chrome, real staging URLs, no mocks): login
  as a fresh synthetic Owner → unlinked enquiry Project → "Convert to
  Customer" → filled synthetic Full name/Email/Phone → "Save customer" →
  observed real `POST .../convert-to-customer` → `200` → Customer rendered →
  action hidden → page reload → both still true. GREEN.
- API-verified persistence: `Project.customer_id` == returned Customer id,
  `Project.status` still `"enquiry"`, Customer's three fields match exactly
  what was submitted, exactly one `enquiry_converted` activity with the safe
  identifier-only description. GREEN.
- Idempotency: a second `POST .../convert-to-customer` on the live staging
  API returns `200`, the same Customer id (same `created_at`, confirming the
  same row), no duplicate Customer, `Project.customer_id` unchanged,
  activity count still exactly 1. GREEN.
- Non-enquiry guard: a second synthetic Project advanced to `"booked"` then
  converted returns `409`, no Customer created, no mutation, no activity.
  GREEN.
- Cross-tenant isolation: a freshly signed-up Tenant B converting Tenant A's
  unlinked enquiry Project returns `404`; Tenant A's Project, Customer count,
  and activity count all unchanged. GREEN.
- **RBAC 403 on staging: BLOCKED BY STAGING FIXTURE SAFETY, not verified
  live** — same category of gap as Sprint 020's staging RBAC finding. No
  approved API path creates a same-tenant `role=None` user (public signup
  only creates Owner; invitations only create Staff); the automated test's
  `auth_service.create_user` is direct Python, not an HTTP endpoint, and
  running it via SSH against staging's live database would be a manual data
  mutation outside the approved fixture path — deliberately not done. The
  equivalent backend automated regression
  (`test_same_tenant_user_without_owner_staff_role_cannot_convert_enquiry`)
  is GREEN and is the authoritative coverage for this behavior.
- Staging smoke (`scripts/staging/smoke.py`, no `--quote-material`/
  `--quote-thickness` supplied — no public materials-catalog endpoint exists
  to source real values and `SEED_DATA_ENABLED=false`): **14 passed, 0
  failed, 8 blocked**. Blocked gates, all pre-existing/documented, none a
  Sprint 021 regression: `migration` (separate remote Alembic evidence
  required — satisfied independently above), `no_seeding` (requires operator
  seed-inventory comparison), `quote_invoice` (requires the two optional
  flags this run omitted), `tenant_isolation` (the smoke runner's own
  documented partial-coverage limit — Sprint 021's actual cross-tenant
  conversion was separately verified live as `404` above),
  `restart_persistence` (requires `--allow-restart` plus a configured
  bounded restart command), `logs_request_ids` (no approved safe
  failure-injection mechanism), `repository_secret_scan` (local/repository
  evidence, not a staging runtime check), `backup_restore` (requires a
  separately approved destructive-risk restore drill).

### Test-hygiene note (not a product defect)

The browser used for staging verification already held an authenticated
real-user session ("Simo / Owner") before the synthetic staging login even
began — visible on a fresh, untouched navigation to `/login`, before any
form interaction. This is a shared-profile browser-automation hazard, not a
Sprint 021 application bug: the synthetic staging Owner was logged in as
instructed (this necessarily replaces the browser's cached JWT), and the
session was cleared (`localStorage.clear()`) immediately after verification,
leaving the browser logged out rather than mid-impersonation. No credentials
or tokens were exposed in any report. See `docs/STAGING_RUNBOOK.md`'s new
"Browser-session isolation" note for the recommended fix going forward
(a fresh isolated browser context/profile for staging auth checks, not a
persistent one that may already hold an unrelated session).

### Technical debt / open items

- **Concurrent conversion race**: idempotency is verified for *sequential*
  repeat calls only (tenant-scoped pre-check under one transaction, both
  locally and on staging). Unlike Sprint 020's `Project.quote_id` (unique
  FK, so a genuine race is caught by the database), `Project.customer_id`
  has **no unique/exclusion constraint** backing the idempotency check — two
  truly concurrent first-conversion requests on the same Project could each
  pass the "customer_id is null" check before either commits, producing two
  Customers and a last-write-wins link. No explicit application-level
  locking or retry/recovery path exists for this case; it was not
  implemented or tested this sprint and is a real gap, not a theoretical one.
- **E2E / staging synthetic data**: no safe generic delete API exists for
  customers or projects (same finding as Sprint 020). Rows from this
  sprint's local Playwright runs and every staging verification pass remain,
  identified by `Pytest E2E Sprint 021 <run-id>` / `Sprint 021 Staging
  <run-id>` naming.
- **Staging RBAC 403 fixture gap**: identical in shape to Sprint 020's
  finding — blocked by environment safety controls, not application
  behavior. Still needs a safe, approved way to provision a same-tenant
  no-role user on staging (e.g., a dedicated, reviewed diagnostic script)
  before this can be closed for either sprint.
- **Railway CLI upload vs. working-tree debris**: `railway up`'s local
  indexer hard-failed on a pre-existing, ACL-locked, non-gitignored
  directory (`.tmp-pytest-task10/`) unrelated to this sprint's code.
  Worked around via a clean `git archive` deploy (see Staging section above
  and the runbook update). The directory itself was left untouched — it
  could not be inspected or modified even with `icacls`, and deleting an
  unfamiliar, inaccessible directory without understanding its origin was
  judged too risky to do unilaterally.
- **`.railwayignore` local edit**: during diagnosis of the upload failure
  above, `.railwayignore` was edited locally to exclude
  `.tmp-pytest-task10/`, `.venv-broken-sprint019/`,
  `.venv-broken-sprint019-current/`, and `graphify-out/`. This edit was
  **not** part of the successful deployment (the clean `git archive` route
  was used instead) and was **deliberately left uncommitted** — it's
  unrelated to the shipped Sprint 021 feature. It remains a modified,
  unstaged file in the working tree as of this doc closeout; a maintainer
  should decide separately whether to commit, discard, or revise it.
- **Pre-existing staging smoke blocked gates**: same categories as Sprint
  020 (`no_seeding`, `restart_persistence`, `logs_request_ids`,
  `repository_secret_scan`, `backup_restore`), plus `quote_invoice` and
  `tenant_isolation` for the reasons given above — none are Sprint 021
  regressions.
