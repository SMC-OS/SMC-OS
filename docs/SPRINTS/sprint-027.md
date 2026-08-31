# Sprint 027 — Full-System E2E / UAT Preparation

Status: **Phase 2 — discovery and contract locked. Implementation not
yet started (Phase 3).** See `docs/ROADMAP.md`'s locked v1.0 table —
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

## 5. Open decisions — resolved

1. **Follow-up job trigger in the connected E2E spec.**
   `apps/web/e2e/follow-up-automation.spec.ts` already establishes the
   pattern: `execFileSync("python", ["-m", "app.jobs.follow_up", "--now", now], { cwd: REPO_ROOT })`
   as a real subprocess against the same database the running FastAPI
   server uses, using the job's own documented `--now` verification
   escape hatch (`app/jobs/follow_up.py`'s docstring: "verification
   only... production operation always uses the real current time").
   The connected journey and any new follow-up-adjacent test reuse
   this exact invocation — no product-code change, no new test seam.
2. **`smoke.py` gate additions are additive only.** New gates append
   to the existing `SMOKE_GATES` tuple and `SmokeRunner` class; no
   existing gate's behavior changes.
3. **RBAC integration sweep scope.** A new backend test enumerates
   every route in `app/api/v1/__init__.py`'s `api_router` plus
   `app/activity/router.py`/`app/notifications/router.py` and asserts
   each one's actual dependency chain matches a hand-maintained
   expected table (role requirement, tenant-scoping expectation) —
   not a fully automatic route-introspection assertion, since FastAPI
   dependency graphs aren't trivially diffable against an "expected
   role" without hand-authored intent per route.

---

## 6. Locked TDD sequence

Backend and frontend work proceed independently; both land before the
new E2E specs, which depend on real UI and real routes existing.
Every RED is a real failing test against real Postgres/FastAPI/
Next.js — no mocked layer, matching every prior sprint's convention
(`docs/SYSTEM_ARCHITECTURE.md` §8.3's verification bar).

1. RED/GREEN: `tests/test_rbac_matrix.py` — one parametrized test
   over a hand-authored `EXPECTED_ROUTE_AUTH` table (route, method,
   expected: `public` / `authenticated` / `require_role(OWNER)` /
   `require_role(OWNER, STAFF)` / `token-scoped-public`) asserting a
   `role=None` or wrong-role caller gets the expected `401`/`403`,
   and a valid caller of the *correct* role gets past the gate (not
   asserting full 200 business logic — that's each module's own
   suite's job). Covers all 13 routers plus the 2 activity/
   notifications routers plus the 2 public portal-token route groups.
2. RED/GREEN: extend `tests/conftest.py`'s `other_tenant_auth_headers`
   fixture to a `RUN_ID`-suffixed email/company (matching every
   Playwright spec's own convention), removing the fixed-email
   determinism risk (finding §3.8) without changing its cleanup
   contract.
3. Frontend RED/GREEN: `apps/web/app/login/page.test.tsx` — renders,
   submits, shows a field-level error on a 401.
4. Frontend RED/GREEN: `apps/web/app/signup/page.test.tsx` — renders,
   submits, redirects on success.
5. Frontend RED/GREEN: `apps/web/app/invite/[token]/page.test.tsx` —
   valid/expired/already-accepted token states.
6. Frontend RED/GREEN: `apps/web/app/settings/page.test.tsx` —
   invitation create/list, team list/deactivate, Owner-only controls
   hidden for a Staff-role session.
7. Frontend RED/GREEN: `apps/web/app/portal/[token]/page.test.tsx` —
   active/expired/revoked link states, document list, message thread.
8. CI RED/GREEN: `.github/workflows/ci.yml`'s `e2e` job — add an
   `actions/upload-artifact@v4` step (`if: failure()`) for
   `apps/web/playwright-report/` and `apps/web/test-results/`;
   verified by deliberately failing a spec locally/in a scratch run
   and confirming the artifact is produced, then reverting the
   deliberate failure.
9. `scripts/staging/smoke.py` RED/GREEN (against a local run, not
   staging, until Phase 4's real staging pass): add gates
   `quote_approve_handoff`, `appointment`, `project_assignment_status`,
   `follow_up_notification`, `command_centre` to `SMOKE_GATES` and
   corresponding `SmokeRunner` methods, reusing the existing
   `gate()`/`blocked()`/`sanitize_evidence()` machinery unchanged.
   `login_throttle`/security-headers verification is added as
   assertions inside the existing `https_reachability`/`liveness`
   gates' evidence (a new header-presence check), not a new gate, to
   avoid tripping the real rate limiter during an otherwise-clean
   smoke run.
10. Playwright RED/GREEN: `apps/web/e2e/unauthenticated-redirect.spec.ts`
    — one test, every staff-only frontend route (`/customers`,
    `/projects`, `/quotes`, `/settings`) redirects to `/login` with no
    token present.
11. Playwright RED/GREEN: `apps/web/e2e/cross-tenant-boundary.spec.ts`
    — one test, Tenant B's authenticated session cannot browse to
    Tenant A's customer/project/quote/appointment/document IDs
    through the real UI (not just the API), asserting the UI's
    not-found/error state, not just an HTTP status.
12. Playwright RED/GREEN: `apps/web/e2e/role-boundary-owner-vs-staff.spec.ts`
    — one test, a Staff-role browser session sees Owner-only controls
    (invite teammate, deactivate teammate, assign project) either
    absent or rejected with a correct UI-level message.
13. Playwright RED/GREEN: `apps/web/e2e/portal-token-lifecycle.spec.ts`
    — one test, an expired and a revoked portal link both render a
    clear "link no longer valid" UI state, not a raw error or blank
    page.
14. Playwright RED/GREEN: `apps/web/e2e/full-system-journey.spec.ts`
    — one test, the connected journey (§7 below), the sprint's
    centrepiece.
15. Full local regression: backend (`pytest`), frontend
    (`pnpm lint`, `pnpm check-types`, `pnpm --filter web test`,
    `pnpm --filter web test:runtime-config`,
    `pnpm --filter web test:docker-contract`, `pnpm build`), full
    Playwright suite (all 11 specs: 6 existing + 5 new), Alembic
    heads/check (no migration expected — confirm none was
    accidentally introduced).
16. Exact-head CI (push branch, confirm `backend`/`frontend`/`e2e`
    all green, confirm the new artifact-upload step is present in the
    job graph even on a green run).
17. Staging deploy + extended smoke run (`scripts/staging/smoke.py`
    against the real staging origin) + UAT checklist (§9) + browser
    verification.
18. Docs closeout: this file's closeout section, plus the minimum
    `docs/ROADMAP.md`/`USER_ROLES.md`/`DATABASE_SCHEMA.md` updates
    needed to close this sprint's own record honestly (§4 — not a
    full historical reconciliation).
19. Final feature CI.
20. PR, explicit merge commit, `origin/main` verification, post-merge
    CI.

## 7. LOCKED CONTRACT — the connected full-system E2E journey

`apps/web/e2e/full-system-journey.spec.ts`, one `RUN_ID`-seeded
tenant/company/owner/customer/project carried through every step
(deliberately *not* isolated per-step, unlike the other new specs —
the point here is proving hand-off, not isolation):

1. Signup through the real `/signup` UI form (not raw API — the one
   thing every existing spec skips). Confirm redirect + session.
2. Reload the page; confirm the session persists (token survives a
   refresh, per `components/auth/AuthProvider.tsx`'s documented
   mount-time `GET /api/v1/auth/me` resolution).
3. Create a Customer through the `/customers/new` UI.
4. Create a Project through the `/projects/new` UI, linked to that
   Customer (starts `enquiry`, per `ProjectStatus.ENQUIRY`).
5. On `/projects/[id]`, schedule an Appointment/Site Visit; mark it
   completed.
6. Create a Quote (`/quotes/new`) linked to the Customer; on
   `/quotes/[id]`, approve it (`POST /quotes/{id}/approve` through
   the UI action, not raw API).
7. Hand off the Quote to the Project through the UI
   (`POST /quotes/{id}/handoff`); confirm the Project's status is now
   `booked` and it is reachable from `/projects/[id]`.
8. On `/projects/[id]`: Owner assigns Staff (`assigned_user_id`);
   advance status `booked → templated → fabricated → installed →
   complete`, one UI action per transition, asserting each is
   reflected on reload. Attempt one invalid transition (e.g. skip a
   stage) and confirm the UI surfaces the backend's `409` cleanly.
9. Upload a Document to the Customer through the UI.
10. Create a Portal Link for the Customer through the UI. In a
    **second, unauthenticated Playwright browser context**, open
    `/portal/[token]`: confirm the Project, Quote, and Document are
    visible; post a customer message; back in the staff context,
    confirm the message appears and produced a notification.
11. Run `python -m app.jobs.follow_up --now <iso>` (per §5.1) against
    a **separately-seeded** stale `enquiry`-status Project in the
    same tenant (created earlier than the threshold, assigned to the
    Staff user) — not the Project from steps 4–8, which has already
    moved past `enquiry`. Confirm the resulting notification appears
    in the staff UI, is navigable, and reaches the correct recipient.
12. Load `/`; assert the Command Centre reflects the exact state
    built above (pipeline counts including the completed Project,
    quote funnel including the approved+handed-off Quote, one
    completed site visit, one follow-up notification) — exact
    assertions against known values, not a loose "is not empty"
    check, per Sprint 025's own established E2E precedent.
13. Revoke the Portal Link through the UI; in the second browser
    context, reload `/portal/[token]` and confirm it now renders the
    "link no longer valid" state.

Setup that has no UI path yet stays via direct API call, matching
every prior spec's own precedent (e.g. there is no UI form to create
a second, backdated stale-enquiry Project for step 11 — that stays
API-seeded, same as `follow-up-automation.spec.ts` already does).

## 8. LOCKED CONTRACT — role/isolation specs, RBAC sweep, CI, smoke

- **`test_rbac_matrix.py`**: `EXPECTED_ROUTE_AUTH` is a plain Python
  list of tuples (method, path template, expected-auth) hand-authored
  from this document's §2 matrix — kept as a literal table in the
  test file itself (not derived from route introspection), so a
  future route that forgets its gate fails this test the same way
  the legacy `/dashboard` gap was found in Sprint 026, rather than
  silently passing because the sweep only checks routes it already
  knew about. Adding a new route without updating this table is a
  known, accepted limitation — flagged in the test's own docstring.
- **CI artifact upload**: `if: failure()`, `actions/upload-artifact@v4`,
  `name: playwright-report`, `path: |\n  apps/web/playwright-report/\n  apps/web/test-results/`,
  `retention-days: 14` (matches this repo's existing preference for
  short, explicit retention over defaults — no other workflow step
  sets a custom retention, so 14 is a new, documented choice, not a
  silent default).
- **`smoke.py` new gates** append to `SMOKE_GATES` in this exact
  order, after `tenant_isolation` and before `cors_allowed`:
  `quote_approve_handoff`, `appointment`, `project_assignment_status`,
  `follow_up_notification` (`BLOCKED` by default — the CLI job isn't
  reachable from a public HTTPS smoke run without SSH/exec access;
  same treatment as the existing `migration`/`no_seeding` gates),
  `command_centre`. Each new `SmokeRunner` method follows the
  existing `gate()`/gate-name/evidence-dict shape exactly (see
  `smoke.py:94-105`'s `gate()` helper) — no new error-handling
  pattern introduced.
- **Login-throttle/security-headers evidence**: added as extra keys
  in the existing `liveness`/`https_reachability` gates' evidence
  dicts (e.g. presence of `X-Request-ID`, a hardened-headers
  presence check against a known Sprint 026 header set), not a
  request that actually trips the throttle — tripping a real rate
  limiter on every staging smoke run would itself be a production
  hazard, explicitly avoided.

---

## 9. UAT checklist & evidence requirements (Phase 4)

Mirrors the "End-to-end delivery closeout" format already established
in `docs/SPRINTS/sprint-025.md` §5 and `sprint-026.md`'s closeout:
git history (baseline/branch/every named commit), full local
regression output, exact-head CI run link, staging deploy commit +
Alembic-heads confirmation (no migration expected this sprint — an
explicit statement that none was introduced, not silence), extended
`smoke.py` JSON report (sanitized, per its existing redaction
contract), and the new Playwright trace/screenshot artifacts now
retained per §8's CI change.

## 10. Risks / blockers

- The 13-step connected spec risks flakiness under `workers: 1`/
  sequential timing — mitigated by existing `trace: retain-on-failure`
  plus the new CI artifact retention (§8).
- `smoke.py` gate additions touch real staging (Railway) once run
  for real in Phase 4 — must stay read/create-synthetic-only, per its
  existing contract; no schema or config change is implied by this
  sprint.
- The RBAC sweep (§8) is a hand-maintained table, not a self-updating
  one — accepted as a known limitation, not silently glossed over.

## 11. End-to-end delivery closeout

*Pending — recorded here once Phases 3-5 (implementation, local
regression, staging verification) are complete and approved. Not
populated by this Phase 2 contract-lock commit.*

