# Sprint 027 — Full-System E2E / UAT Preparation

Status: **Phase 1/2 — discovery complete, contract not yet locked.** No
implementation has started. See `docs/ROADMAP.md`'s locked v1.0 table —
this is the next scheduled sprint after Sprint 026, and it is a
verification sprint, not a new business capability.

Branch: `sprint-027-full-system-e2e-uat`
Baseline: `main` @ `efbdcc4` (Sprint 026 merge, PR #8, clean)

## Objective

Sprints 020–026 each shipped and individually verified one vertical
slice of the v1.0 journey (Enquiry→Customer conversion, Appointment/
Site Visit, Project Operations, Notifications/Follow-up, Business
Command Centre, Security Hardening II). Each slice has its own
self-contained Playwright spec and pytest suite, proven only against
its own fresh seed data. **No test anywhere proves the slices work
connected together**, through the browser, as one customer/staff
journey. Sprint 027 does not add a feature. It closes that gap: one
deterministic full-system E2E suite, the role/tenant/token boundary
journeys that today are only tested piecemeal, a staging smoke tool
that still only covers Sprint 019-vintage routes, and CI failure
evidence that is currently captured locally by Playwright but never
retained.

Scope note: this sprint follows the discovery precedent set by
Sprint 026 (`docs/SPRINTS/sprint-026.md` §"Phase 1 — Discovery" —
read-only inspection, every finding verified by reading the cited
file/line, "no issue found" stated explicitly where checked and
clean) and the "Explicit out of scope" contract-lock precedent set by
Sprints 022–025 (`docs/SPRINTS/sprint-022.md` §13, `sprint-023.md`
§13, `sprint-024.md` §14, `sprint-025.md` §"Explicitly out of scope
this sprint").

---

## 1. Discovery method

Two read-only discovery passes were run against `main` before this
document existed:

1. A first pass proposed a new business capability ("Contracts &
   Customer Sign-off"), rejected by the product owner as unplanned —
   `docs/ROADMAP.md`'s locked v1.0 table names Sprint 027 explicitly
   as "Full-System E2E / UAT Preparation," not a new feature slot.
2. A second pass (this document's source) inventoried every v1.0
   journey delivered by Sprints 001–026 against the actual source
   tree — `app/`, `apps/web/`, `tests/`, `apps/web/e2e/`,
   `apps/web/playwright.config.ts`, `.github/workflows/ci.yml`,
   `scripts/staging/smoke.py`, `tests/conftest.py` — and against each
   delivered sprint's own Objective/Explicit-out-of-scope/Closeout
   sections (`docs/SPRINTS/sprint-020.md` through `sprint-026.md`).
   Every finding below was verified by reading the cited file, not
   inferred from `docs/ROADMAP.md`, `docs/DECISIONS.md`, or
   `docs/USER_ROLES.md` — those three, plus `docs/CHANGELOG.md`, are
   confirmed stale (last genuinely current somewhere between Sprint
   013 and Sprint 019; `docs/SPRINTS/sprint-NNN.md` files remain the
   authoritative historical record per `docs/ROADMAP.md`'s own
   maintenance rule).

## 2. Journey & coverage matrix

| Journey (sprint) | DB | Backend/API | RBAC | Tenant isolation | Frontend | Playwright E2E | Backend tests | Staging smoke |
|---|---|---|---|---|---|---|---|---|
| Signup/Login/JWT (003,009) | `users` | `auth/router.py` | n/a (pre-auth) | `tenant_id NOT NULL` (ADR-026) | `/signup`,`/login` | **None through the UI** — every spec signs up via raw API | `test_auth.py` | `signup_login_auth` gate |
| Login throttle + security headers (026) | — | `auth/rate_limit.py` | — | — | — | **None** | `test_login_rate_limit.py`, `test_security_headers.py` | **Missing** — not in `smoke.py` |
| Team invitations (011) | `invitations` | `invitations/router.py:58,80,95` — `require_role(OWNER)` | Yes | Yes | `/invite/[token]`, `/settings` | **None** | `test_invitations.py` | **Missing** |
| Team management/deactivate (015) | `users.is_active` | `users/router.py:28,37` — `require_role(OWNER)` | Yes | Yes | `/settings` | **None** | `test_users.py` | **Missing** |
| Customers CRUD (004) | `customers` | `customers/router.py` | none (routine work) | Yes | `/customers`,`/customers/[id]`,`/new` | **None** | `test_customers.py` | `customer` gate |
| Materials catalogue (005) | `materials` | internal only, no route | n/a | n/a (shared, deliberate) | none | — | `test_materials.py` | — |
| Quote create/approve/handoff (006,007,020) | `quotes`,`projects` | `quotes/router.py:73,100` — approve/handoff `require_role(OWNER,STAFF)` | Yes | Yes | `/quotes`,`/quotes/[id]`,`/new` | `quote-handoff.spec.ts` (approval+handoff only; not creation-through-UI or invoice download) | `test_quotes.py`,`test_quotes_api.py`,`test_quote_handoff.py` | `quote_invoice` gate — **creates + invoices only, never calls `/approve` or `/handoff`** |
| Enquiry→Customer conversion (021) | `customers`,`projects` (atomic) | project/customer conversion endpoint | — | Yes | project detail | `enquiry-conversion.spec.ts` | `test_enquiry_conversion.py` | **Missing** |
| Appointment/Site Visit (022) | `appointments` | `appointments/router.py:33,47,60` — `require_role(OWNER,STAFF)` | Yes | Yes | embedded in `/projects/[id]` | `site-visit-scheduling.spec.ts` | `test_appointments.py` | **Missing** |
| Project assignment + status transitions (023) | `projects.assigned_user_id` | `projects/router.py:86` assign `require_role(OWNER)`; `:65,104` status `require_role(OWNER,STAFF)` | Yes | Yes | `/projects/[id]` | `project-operations.spec.ts` | `test_project_operations.py`,`test_projects.py` | **Missing** |
| Client portal: tracking/docs/messaging (013,016,017) | `documents`,`messages`,`portal_links` | `portal/router.py`,`documents/router.py`,`messages/router.py` | n/a (token-scoped, public) | Yes (token+customer bound) | `/portal/[token]` | **None — zero Playwright coverage of `/portal/[token]`** | `test_portal.py` (23 tests), `test_documents.py`, `test_messages.py` | `staff_document`,`portal_token`,`portal_documents`,`portal_messaging`,`token_enforcement` gates |
| Per-user follow-up notifications (024) | `notifications.recipient_user_id`,source fields, dedupe key | `jobs/follow_up.py` (CLI only, no HTTP route) | n/a | Yes | `NotificationsPanel` | `follow-up-automation.spec.ts` | `test_follow_up_automation.py` | **Missing** (and can't use an HTTP gate — CLI-only) |
| Business Command Centre (025) | aggregates existing tables | `dashboard/router.py:16-21` — `require_role(OWNER,STAFF)` | Yes | Yes | embedded `CommandCentrePanel` on `/` | `business-command-centre.spec.ts` | `test_command_centre.py`,`test_dashboard.py` | **Missing** |
| Legacy `/dashboard` (pre-025) | — | `api/v1/core.py:78-89` — `require_role(OWNER,STAFF)` (fixed post-Sprint-026) | Yes | Yes | — | — | `test_dashboard.py` | — |
| Tenant isolation (012, cross-cutting) | `tenant_id` on 7/8 tables | every business route | — | ADR-029 pattern | — | Only implicit, inside each spec's own setup | `test_permissions.py` (4 unit tests on `require_role` only — **no per-route integration sweep**) | `tenant_isolation` gate (customers/projects/quotes only) |

## 3. Concrete findings

1. **No connected Playwright journey exists.** All 6 specs in
   `apps/web/e2e/` are single-sprint silos; each creates its own
   tenant/customer/quote via raw `request.newContext` API calls,
   never through the login UI, and never hands state to another
   spec. Nothing proves Enquiry→Appointment→Quote→Approval→Handoff→
   Project-Ops→Documents/Messaging→Notification→Command-Centre works
   connected, through the browser.
2. **Zero Playwright coverage of the customer portal**
   (`/portal/[token]`) despite `test_portal.py` being the most
   thoroughly-covered backend module (23 tests) — the one surface a
   real customer touches has no browser-level proof.
3. **Zero Playwright coverage of `/login`, `/signup`,
   `/invite/[token]`, `/settings`** — every spec bypasses the UI
   login form via API signup.
4. **`scripts/staging/smoke.py` is 7 sprints stale.** Its
   `SMOKE_GATES` tuple (22 gates) and code date from Sprint 019 —
   zero coverage of appointments, project assignment/status-transition
   RBAC, follow-up notifications, command centre, or Sprint 026's
   login-throttle/security-headers hardening. It also never calls
   quote `/approve` or `/handoff` (`smoke.py:128-132` only creates +
   invoices) — Sprint 020's entire objective has no staging smoke
   coverage today.
5. **`test_permissions.py` is a unit-test file, not an integration
   sweep.** It tests `require_role()` in isolation (4 tests). Each
   module's own file covers its own RBAC/cross-tenant cases
   individually (verified thorough in `test_portal.py`,
   `test_project_operations.py`), but no single test asserts the
   complete RBAC matrix across all ~13 routers at once — the same
   class of gap Sprint 026 found once on the legacy `/dashboard`
   route, with no regression guard against it recurring elsewhere.
6. **CI's `e2e` job produces no retained failure evidence.**
   `playwright.config.ts:32-33` sets `trace: "retain-on-failure"` and
   `screenshot: "only-on-failure"`, but `.github/workflows/ci.yml`'s
   `e2e` job has no `actions/upload-artifact` step — a CI E2E
   failure today gives a red check and nothing else to inspect.
7. **Only 5 frontend component test files exist**
   (`apps/web/app/projects/[id]/page.test.tsx`,
   `apps/web/app/quotes/[id]/page.test.tsx`,
   `CommandCentrePanel.test.tsx`, `NotificationsPanel.test.tsx`,
   `lib/activity.test.ts`). `/customers*`, `/settings`,
   `/portal/[token]`, `/login`, `/signup`, `/invite/[token]` have no
   component-level test.
8. **`tests/conftest.py:67-84`'s `other_tenant_auth_headers` fixture
   uses a fixed, non-randomized email/company**, cleaned up before
   and after use — unlike every Playwright spec's `RUN_ID`-randomized
   data. Safe under today's sequential `pytest` execution; a
   determinism risk only if backend tests are ever parallelized.
9. **Appointments have no customer-facing surface, by design**
   (`docs/SPRINTS/sprint-022.md` §13: "no customer account/portal
   access to appointments at all this sprint") — not a bug, stated
   here so it isn't mistaken for a missed link during full-system
   testing.
10. **Docs staleness** — `docs/ROADMAP.md`, `DECISIONS.md`,
    `CHANGELOG.md`, `USER_ROLES.md`, `DATABASE_SCHEMA.md` all stop
    reflecting reality somewhere between Sprint 013 and Sprint 019.
    `USER_ROLES.md` still says "seven modules require a token" where
    the real count today is 13 routers plus 2 public portal-token
    route groups.

## 4. Explicit out of scope

Any new database table, model, route, or UI screen not already
shipped by Sprints 001–026. Contracts, e-signatures, payments,
purchasing, supplier management, AI features, or any other new
business capability (rejected in the first discovery pass — this
sprint is verification-only, per the locked roadmap). Full historical
reconciliation of `DECISIONS.md`/`CHANGELOG.md` back to Sprint 013 —
only the reconciliation needed to close this sprint's own record
honestly. Parallelizing `pytest` or Playwright execution. A persistent
staging cron/scheduler for the follow-up job (already out of scope in
`docs/SPRINTS/sprint-024.md` §14 — "A persistent Railway
cron/scheduled-job service... is future infrastructure"). Any change
to an already-locked module contract from Sprints 001–026 except a
fix directly exposed by this sprint's own E2E/UAT suite. Production
or staging deployment during Phase 2 (discovery/contract-lock only —
deployment is a later phase of this same sprint, gated on its own
approval).

## 5. Open decisions to resolve before the first RED

1. **Follow-up job trigger in the connected E2E spec.** `jobs/follow_up.py`
   has no HTTP route — only a CLI entrypoint. The connected spec must
   either shell out to the CLI mid-test or a test-only invocation
   path must be added. Recommend: shell out to the same CLI command
   staging/production would run (`python -m app.jobs.follow_up` or
   equivalent), keeping the job itself unchanged — confirmed as the
   locked approach below.
2. **`smoke.py` gate additions are additive only.** New gates append
   to the existing `SMOKE_GATES` tuple and `SmokeRunner` class;
   no existing gate's behavior changes. Confirmed below.
3. **RBAC integration sweep scope.** A new backend test enumerates
   every route in `app/api/v1/__init__.py`'s `api_router` plus
   `app/activity/router.py`/`app/notifications/router.py` and asserts
   each one's actual dependency chain matches a hand-maintained
   expected table (role requirement, tenant-scoping expectation) —
   not a fully automatic route-introspection assertion, since FastAPI
   dependency graphs aren't trivially diffable against an "expected
   role" without hand-authored intent per route. Confirmed below.
