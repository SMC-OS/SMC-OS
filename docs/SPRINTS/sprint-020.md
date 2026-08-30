# Sprint 020 — End-to-End Quote Approval & Project Handoff

## Objective

A permitted tenant staff user can create a quote for an existing customer, approve it through a deliberate backend-enforced lifecycle, and hand it off to the existing Project pipeline through the real UI and API. The resulting project remains tenant-scoped, traceable to its quote and customer, and usable after a refetch.

## Implemented contract

This document is the Sprint 020 delivery contract. It describes the intended implementation until the verification sections are populated with fresh evidence.

### Existing foundations reused

- `Customer`, `Quote`, and `Project` remain the existing tenant-owned records.
- Quotes continue to be created by `POST /api/v1/quote`; an authenticated caller's tenant is attached by the established optional-auth behaviour.
- Projects retain the existing pipeline and its `booked` operational state.
- `get_current_user` / `require_role` remain the sole authorization framework. Both existing operational roles (`Owner`, `Staff`) may manage approval and handoff; portal routes have no staff JWT and cannot use either operation.
- Existing tenant-filtered CRUD lookups, ActivityLog, API client, and quote/project detail pages are extended rather than replaced.

### Quote lifecycle

New persisted quotes start as `draft`, the single editable/pre-approval state presently supported by the existing create-only quote surface. `approved` is the terminal approval state for this sprint. Approval is a command operation, not a generic status patch. It records `approved_at` and the approving staff user where the schema supports it.

An anonymous or unlinked quote may remain a historical calculated quote, but cannot enter the customer-to-project handoff: approval and handoff require a quote linked to an accessible tenant customer.

### Approval operation

`POST /api/v1/quotes/{quote_id}/approve`:

- is staff-authenticated and tenant-scoped;
- accepts only a linked `draft` quote;
- persists approval state and audit attribution;
- writes one meaningful `quote_approved` activity event with safe identifiers only;
- returns the refreshed quote;
- returns a stable conflict for an already-approved quote and a not-found response for inaccessible tenant data.

### Project handoff operation

`POST /api/v1/quotes/{quote_id}/handoff`:

- is staff-authenticated and tenant-scoped;
- requires an approved quote linked to the caller's customer;
- creates one existing `Project` in `booked` state, retaining its customer and a traceable `quote_id` relationship;
- writes one `quote_handed_off` activity event;
- returns the resulting project;
- is idempotent: a repeat handoff returns the already-linked project and never creates another.

The project-side unique quote relationship is the database-enforced duplicate prevention mechanism. Existing projects have a nullable `quote_id` so historical data remains valid.

### Database contract

One additive Alembic revision may add only the columns and constraints necessary for this contract:

- quote `status`, `approved_at`, and `approved_by_user_id`;
- project `quote_id`, foreign-keyed to `quotes.id` and uniquely constrained.

The migration preserves existing rows by assigning the safe pre-approval default to historical quotes, retains tenant FKs, and is verified by an upgrade/downgrade/upgrade round trip.

### UI contract

The real quote detail page renders state, approval and handoff actions only when valid. It provides pending/disabled and error feedback, refreshes its real API state after each transition, and links directly to the resulting Project after handoff. It does not introduce a parallel quote/customer creation flow or a mocked state transition.

## Mandatory invariants

- Tenant A cannot read, approve, or hand off Tenant B's quote, nor attach Tenant B's customer or project.
- A portal token cannot acquire staff approval/handoff authority.
- Invalid transitions are rejected server-side.
- Repeated approval has stable domain behaviour; repeated handoff cannot create duplicate Projects.
- Approval and handoff records activity using safe, useful identifiers without quote contents or secrets.
- The frontend calls the real API and persisted backend state survives refetch/reload.

## Verification requirements

TDD covers approval, invalid/repeated transitions, RBAC, tenant isolation, activity events, rollback where testable, project linkage, and duplicate protection. Frontend tests cover visible/hidden actions, success, errors, pending state, and project navigation using the existing repository conventions where available. A real browser E2E journey must exercise Customer → Quote → Approve → Handoff → Project through the frontend.

Before staging, run backend, migration, frontend lint/type/build/tests, E2E, existing auth/RBAC/quote/project tests, Sprint 019 non-destructive regression, `git diff --check`, and a secret scan. Stage only approved Sprint 020 files after review; never stage unrelated local evidence or environment files.

## Explicitly out of scope

- Appointment/calendar functionality.
- A new enquiry subsystem or unrelated CRM work.
- A general quote update/delete editor, sending/email delivery, customer self-service approval, billing, payment collection, or a new permissions framework.
- A new notification subsystem. Existing activity is mandatory; a notification is added only if an existing recipient/action convention makes it an obvious narrow extension.
- Sprint 019 recovery changes or any Sprint 021 work.

## Implementation evidence

Closed out at commit `3196fa3` on `sprint-020-e2e-quote-handoff`. Every item below is backed by a command, test, or staging check actually run during this sprint — nothing here is aspirational.

### Backend

- Quote approval: `POST /api/v1/quotes/{quote_id}/approve` — staff-authenticated, tenant-scoped, accepts only a linked `draft` quote, persists `approved_at`/`approved_by_user_id`. Covered by `tests/test_quote_handoff.py::test_staff_can_approve_a_draft_quote`.
- Approval RBAC: `require_role(OWNER, STAFF)` on both approve and handoff routes (`app/quotes/router.py`); a role-less same-tenant user is rejected with 403 — `tests/test_quote_handoff.py::test_non_owner_staff_user_cannot_hand_off_an_approved_quote`.
- Approval activity: exactly one `quote_approved` `ActivityLog` row per approval, tenant-scoped — `test_approving_quote_creates_exactly_one_tenant_scoped_activity_record`.
- Approved-only handoff: `POST /api/v1/quotes/{quote_id}/handoff` rejects a draft quote with 409 — `test_handoff_rejects_a_draft_quote`.
- `Project.quote_id` migration/linkage: Alembic revision `d3e7a9c1f204` adds `projects.quote_id` (FK to `quotes.id`, unique-constrained); the handoff response and `GET /api/v1/projects/{id}` both return it — `test_staff_can_hand_off_an_approved_quote_into_a_project`.
- Booked Project creation: handoff creates a `Project` in `booked` status, retaining the quote's customer — same test.
- Idempotent retry: a repeat handoff of the same quote returns the existing Project and never creates a second one (DB-unique-constraint-backed) — `test_repeat_handoff_of_the_same_quote_is_idempotent`.
- Tenant isolation: Tenant B handing off Tenant A's approved quote gets 404 — `test_handoff_of_another_tenants_quote_returns_404`.
- Handoff RBAC regression coverage: same 403 contract locked in permanently by `test_non_owner_staff_user_cannot_hand_off_an_approved_quote`.
- `quote_handed_off` activity: exactly one row per successful handoff, tenant-scoped — `test_successful_handoff_creates_exactly_one_tenant_scoped_activity_record`.

Full backend suite: **361 passed, 1 skipped** (`pytest`, from repo root, against local Postgres, migrated to `d3e7a9c1f204`).

### Frontend

- Quote status: `/quotes/[id]` renders `Draft`/`Approved` from the real `Quote.status` field.
- Approve UI: "Approve" button visible only when `status === "draft"` and role is Owner/Staff; calls `api.approveQuote` and re-renders on success.
- Role gating: both Approve and Hand-off actions are gated on `role === "Owner" || role === "Staff"` client-side (server enforces the real rule regardless).
- Handoff UI: "Hand off to Project" visible only when `status === "approved"`; calls `api.handoffQuote`.
- Returned Project navigation: `router.push('/projects/{server-returned id}')` — the id comes from the API response, never derived from `quote.id`.
- Handoff failure safety: on a failed handoff, the page does not navigate, restores the action button, and surfaces the existing error UI — `apps/web/app/quotes/[id]/page.test.tsx::keeps_the_user_on_the_quote_and_restores_handoff_after_api_failure`.

Frontend component suite: **3 passed** (`pnpm --filter web test`).

### E2E (true browser, Sprint 020's first)

- Runner: Playwright 1.62.1, Chromium only (`apps/web/playwright.config.ts`), hardcoded loopback URLs (`localhost:3000` web / `127.0.0.1:8000` API) with no env-var override, so the suite cannot be pointed at a non-local origin without editing the file.
- Real Next.js dev server + real FastAPI (`uvicorn app.main:app`) + real local Postgres — no mocked fetch, router, or API client anywhere in `apps/web/e2e/quote-handoff.spec.ts`.
- Exercises: real UI login → real Quote detail page → UI Approve → UI Hand-off → browser navigation to the real returned Project → "Booked" rendered → page reload → still "Booked".
- API-side linkage verification (not renderable in the UI): `GET /api/v1/projects/{id}` confirms `quote_id`/`customer_id`/`status`.
- Duplicate-count verification: `GET /api/v1/projects?limit=50` filtered by `quote_id` confirms exactly one Project.
- CI: dedicated `e2e` job in `.github/workflows/ci.yml` (Postgres service, backend deps + migrations, Chromium install, `pnpm --filter web test:e2e`); the existing frontend Vitest suite was also added to CI's `frontend` job (it was previously configured but never run in CI).

### Staging

- Deployed SHA: `3196fa3` (both `simo-api-staging` and `simo-web-staging`, environment `staging` — production has zero services and was never touched).
- `/health` / `/ready`: GREEN (`{"status":"healthy"}` / `{"status":"ready","database":"reachable"}`).
- Real browser flow (Chrome via claude-in-chrome, not Playwright — see the deployment-issue note below for why an extra revision check was needed first): login → Draft Quote → UI Approve → Approved rendered → UI Hand off → navigated to the real returned Project → Booked rendered → reload → still Booked. All GREEN.
- API-verified linkage: `project.quote_id == quote.id`, `project.customer_id == customer.id`, `project.status == "booked"`. GREEN.
- Idempotency: repeat handoff via the real API returns the same Project id; Project count for the quote stays at 1; `quote_handed_off` activity count stays at 1 (no duplicate). GREEN.
- Draft handoff → 409. GREEN.
- Cross-tenant handoff → 404. GREEN.
- `quote_approved` / `quote_handed_off` activity: both present, tenant-scoped. GREEN.
- Staging smoke (`scripts/staging/smoke.py`, using the pre-existing "Sprint 019 Smoke Material"/"20mm" catalog fixture): **16 passed, 0 failed, 6 blocked** (all 6 are pre-existing, documented, operator-authorization-gated items — see Technical debt below — not Sprint 020 regressions).
- **RBAC 403 on staging: BLOCKED, not verified.** No safe supported path existed to create the required same-tenant no-role user on staging within this session — the environment's own safety controls declined the SSH-based service-layer fixture creation (`auth_service.create_user`) needed to produce that user. This check is **not** claimed as passing on staging. The equivalent backend automated regression (`test_non_owner_staff_user_cannot_hand_off_an_approved_quote`) is GREEN and is the authoritative coverage for this behavior.

### Technical debt / open items

- **Concurrent handoff race**: idempotency is verified for *sequential* repeat calls (tenant-scoped pre-check + the DB-level unique constraint on `projects.quote_id`), both locally and on staging. Genuinely concurrent duplicate-insert recovery (two simultaneous handoff requests racing the unique-constraint check) was not separately implemented or tested this sprint; the unique constraint is the only backstop against a true race, and no explicit application-level retry/recovery path exists for the constraint-violation case.
- **E2E / staging synthetic data**: no safe generic delete API exists for customers, quotes, or projects. Local Playwright runs and every staging verification pass in this sprint leave synthetic tenant/customer/quote/project rows behind, identified by clear `Sprint020-Staging-<run-id>` / `pytest-e2e-sprint020-*` naming.
- **Staging RBAC 403 fixture gap**: see above — blocked by environment safety controls, not by application behavior. Needs a safe, approved way to provision a same-tenant no-role user on staging (e.g., a dedicated, reviewed diagnostic script) before this can be closed.
- **Railway CLI migration verification**: `railway up` deploying `3196fa3` did not apply the two pending Sprint 020 Alembic migrations, even though `preDeployCommand` was correctly configured and its first step (`python -m app.core.runtime_check`) provably executed. Staging silently remained at `f81683afc3f4` while the deployed code expected `d3e7a9c1f204`, causing `POST /api/v1/projects` to 500 with `UndefinedColumn: projects.quote_id`. `/health` and `/ready` both stayed green throughout and did not surface this. See `docs/STAGING_RUNBOOK.md`'s new verification rule. Remediated this sprint via `railway ssh` + `alembic upgrade head` (staging only, no raw SQL); root cause of *why* the CLI-triggered pre-deploy step didn't apply the migration is not fully understood and is called out as an open question, not a proven universal behavior of `railway up`.
- **Pre-existing staging smoke blocked gates** (not Sprint 020 failures — present before this sprint and unrelated to quote handoff): `migration` (requires separately recorded remote Alembic evidence — now available for this sprint, see above), `no_seeding` (requires operator comparison against a known seed inventory), `restart_persistence` (requires `--allow-restart` plus a configured bounded API-only Railway restart command), `logs_request_ids` (no approved safe test-only unhandled-failure mechanism), `repository_secret_scan` (must be run locally against tracked files, not from a staging HTTP check), `backup_restore` (requires a separately approved destructive-risk restore drill).
