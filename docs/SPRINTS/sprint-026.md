# Sprint 026 — Security & Production Hardening II

Status: Phase 1 (discovery) complete.

This sprint follows Sprint 018 ("Production Runtime Hardening"). Sprint 018
covered fail-closed production config, non-root Docker, `/health`/`/ready`,
structured logging with redaction, and frontend prod API-origin validation —
and explicitly deferred rate limiting, password reset, malware scanning,
quotas, billing, WebSockets/SSE, and full APM. This sprint re-audits the
repository end to end against the OWNER of that deferred list plus anything
new introduced by Sprints 019–025, and locks a narrow, verified scope.

## Phase 1 — Discovery

### Method

Read-only inspection of the actual source tree on `sprint-026-security-production-hardening-ii`
(HEAD `ea4160f`, clean). No files were modified. Every finding below was
verified directly by reading the cited file/line, not inferred. Areas with no
finding are stated explicitly as "no issue found" with what was checked.

### 1. Authentication / authorization

Files inspected: `app/auth/security.py`, `app/auth/router.py`,
`app/auth/dependencies.py`, `app/auth/models.py`, `app/auth/service.py`,
`app/database/models.py`, `app/api/v1/core.py`, `app/dashboard/router.py`,
`app/invitations/*`, `app/portal/service.py`, `tests/test_dashboard.py`,
`tests/test_command_centre.py`.

- Password hashing: bcrypt, correct salt/hash/verify (`app/auth/security.py`). No issue.
- JWT: HS256, payload `{sub, tenant_id, exp}`, 60-minute expiry, no refresh
  token (re-login only; a reasonable, undeferred design choice, not flagged
  as a gap). `get_current_user` (`app/auth/dependencies.py:55-75`) rejects
  missing/invalid/expired tokens and deactivated users (`is_active`) with a
  uniform 401 — no detail leak between failure reasons (ADR-031, Sprint 015).
- RBAC: `require_role()` (`app/auth/dependencies.py:98-116`) is consistently
  applied to `projects`, `quotes`, `appointments`, `invitations`, and
  `GET /api/v1/dashboard/command-centre` (`app/dashboard/router.py:16-21`,
  `require_role(UserRole.OWNER, UserRole.STAFF)`).
- **VERIFIED FINDING — Medium.** `GET /api/v1/dashboard` (the original,
  pre-Sprint-025 legacy endpoint, `app/api/v1/core.py:77-85`) depends only
  on `get_current_user`, with no `require_role` gate, unlike every other
  business-data route including its Sprint 025 replacement
  `GET /api/v1/dashboard/command-centre`. `User.role` is nullable
  (`app/database/models.py:172`), and `require_role` rejects a `role=None`
  caller with 403 (locked in as regression coverage by
  `tests/test_command_centre.py::test_role_none_is_forbidden`) — but the
  legacy `/dashboard` route has no equivalent test and no equivalent gate,
  so a `role=None` account would get 200 with tenant revenue/quote/customer/
  project counts from it. Traced every user-creation path
  (`auth_service.signup` → always `OWNER`; `invitations` → always `STAFF`,
  `app/invitations/router.py:3-4`) — **no live signup/invitation path
  creates a `role=None` user today**, so this is not exploitable by an
  existing account-creation flow, but `auth_service.create_user` (used
  directly by `tests/test_command_centre.py`) shows `role` can be `None` at
  the data layer, and the inconsistency with every sibling route is real,
  documented across Sprints 022–025 as a known, repeatedly-deferred
  outlier, and cheap to close. `tests/test_dashboard.py` has no role/RBAC
  test at all (only auth-required, real-data, and tenant-scoping tests).
- Tenant resolution: the JWT's `tenant_id` claim is validated for shape
  only; `crud.get_user_by_id`'s DB row is the authoritative source of
  `tenant_id` (`app/auth/dependencies.py:67-72`) — no trust-the-token bug.
- Object-level / tenant-boundary checks: every scoped query in
  `app/database/crud.py` filters by `tenant_id`. `invitations/service.py`
  revoke path checks `row.tenant_id != tenant_id` before acting
  (lines 103-109). `portal/service.py` quote/document lookups check both
  `tenant_id` and `customer_id`, returning a uniform 404 regardless of
  which check failed (no oracle leak, lines 136-180). No cross-tenant issue
  found.
- Portal/invitation tokens: `secrets.token_urlsafe(32)` (256-bit), SHA-256
  hashed at rest before storage. No issue.

### 2. API security

Files inspected: `app/main.py`, `app/core/middleware.py`, `app/core/errors.py`,
`app/core/health.py`, `app/core/config.py`, `requirements.txt`.

- CORS (`app/main.py:73-79`): origins from settings, `allow_credentials=True`,
  methods/headers `"*"`. Production is fail-closed — `_validate_production_cors`
  (`app/core/config.py:141-165`) rejects `*`, requires HTTPS-only,
  scheme+host-only origins, at process-startup time.
- **VERIFIED FINDING — Low/Medium (deferred, see rationale below).** No
  `TrustedHostMiddleware` / Host-header validation in `app/main.py`. Railway
  domains are dynamic (`${{service.RAILWAY_PUBLIC_DOMAIN}}` template
  variables, confirmed in `deploy/railway/staging.env.example:11,17`), so a
  correct allow-list would need new environment wiring per environment.
  Given the reverse-proxy edge (Railway) already terminates and routes by
  host, and a misconfigured app-level allow-list would fail closed and take
  the API down, this is deferred rather than locked into this sprint's
  narrow scope (see Phase 2 rationale).
- **VERIFIED FINDING — Medium, real production value.** No security-response-headers
  middleware anywhere: no `X-Content-Type-Options`, no `X-Frame-Options` /
  `frame-ancestors`, no `Referrer-Policy`, no `Strict-Transport-Security` in
  production. `RequestContextMiddleware` (`app/core/middleware.py:26-68`)
  only handles request-ID propagation and safe completion logging. This is
  a self-contained, low-risk, response-only addition.
- Exception handling (`app/core/errors.py`): validation errors → clean 422;
  `KeyError` → bounded 400; catch-all `Exception` → generic
  `{"detail": "Internal server error"}` 500, with only `exception_type`
  (not message/traceback) logged server-side. No internal error leakage
  found.
- `/health` and `/ready` (`app/core/health.py`): unauthenticated by design,
  return only `{"status", "database"}` booleans — no config/version/stack
  leakage. No issue.
- **VERIFIED FINDING — Medium, real production value.** No brute-force
  protection or rate limiting on `POST /auth/login` or `POST /auth/signup`
  (`app/auth/router.py:14-35`). Confirmed no throttling library anywhere in
  `requirements.txt` (no `slowapi`, no `limits`, no `redis`). Explicitly
  deferred by Sprint 018 and never subsequently addressed — an unthrottled
  credential-stuffing / brute-force script can hit `/auth/login` today with
  no backoff.
- Input validation: Pydantic models throughout every router. No issue.
- Body-size limits: enforced app-side only for document uploads
  (`app/documents/service.py:30,86-96`, 20MB cap against actual streamed
  bytes). No global request-body-size cap at the app/middleware level —
  acceptable given the reverse-proxy edge typically enforces one; not
  independently verified in this repo and out of proportion for this
  sprint's scope.

### 3. Config / secrets

Files inspected: `.env.example`, `apps/web/.env.local.example`,
`deploy/railway/staging.env.example`, `.gitignore`, `app/core/config.py`.

- `git ls-files` confirms only `*.example` files are tracked for env
  config — no real `.env` or credential file is git-tracked.
  `.gitignore:54-60` excludes `.env`, `.env.local`, `.env.*.local` while
  allow-listing `*.example`. **No exposed live credential found.**
- `.env.example` values are clearly-labeled dev-only placeholders
  (`JWT_SECRET_KEY=dev-only-insecure-secret-change-me`,
  `SEED_ADMIN_PASSWORD=change-me-on-first-login`). No issue.
- Production config is fail-closed (`app/core/config.py:103-178`, verified
  by reading `_validate_production_secrets`, `_validate_production_cors`,
  `_validate_production_storage_and_database`): at startup, in production,
  the app refuses to start unless the JWT secret is ≥32 chars and not the
  dev default, seed email/password are non-default (password ≥12 chars),
  `SEED_DATA_ENABLED=false`, every CORS origin is HTTPS-only/scheme+host
  only/no wildcard, `UPLOAD_DIR` is absolute, and `DATABASE_URL` isn't the
  dev default and parses validly. **No gap found — this area is already
  well-hardened by Sprint 018 and is not touched by this sprint.**
- No client-exposed server secret found in a pass of frontend env examples.

### 4. Database

Files inspected: `app/database/crud.py`, `alembic/versions/*.py` (17 files),
`alembic.ini`, `deploy/railway/api.railway.toml`.

- Tenant filtering verified systematically: every list/get/count/update
  function in `crud.py` touching a tenant-scoped table (Customer, Project,
  Quote, Appointment, Notification, Invitation, ActivityLog, PortalLink,
  Document, User) filters on `tenant_id`. The one non-tenant-scoped read,
  `get_invitation_by_id` (`crud.py:637`), has its only caller
  (`invitations/service.py:103-109`) check `row.tenant_id != tenant_id`
  immediately before use. No leak found.
- Alembic: reconstructed the revision chain by reading all 17 files (could
  not run `alembic heads`/`current` live — no reachable Postgres/venv in
  this discovery pass). Chain is linear and single-rooted (`a22b1189f8e7`
  → … → `2243d66f83da`, sole head, no branching). This must be
  re-verified live (with a real DB) in Phase 4/6 — recorded here as a
  to-do, not a finding.
- Destructive migration safeguards: spot-checked filenames — all are
  additive (`add_*_table`, `add_*_field`, `add_*_indexes`); no unguarded
  `DROP` found.
- `deploy/railway/api.railway.toml:5` runs `alembic upgrade head`
  automatically as the `preDeployCommand` on every deploy, with no manual
  gate — existing accepted design from Sprint 018/019, not a new finding.

### 5. Frontend

Files inspected: `apps/web/lib/auth-storage.ts`,
`apps/web/components/auth/AuthProvider.tsx`, `apps/web/app/layout.tsx`.

- Token storage: JWT in plain `localStorage` — the standard XSS-exposure
  tradeoff for a non-BFF SPA. Architectural change (httpOnly-cookie
  redesign) out of proportion for a narrow sprint; recorded as an accepted,
  deferred risk, not in scope.
- `AuthProvider.tsx:20-26`: client-side `role`/`tenantName`/`userId` are
  documented in-code as cosmetic UI-gating only, with the server as the
  real enforcement point. Correctly designed. No issue.
- `dangerouslySetInnerHTML`: one usage, `apps/web/app/layout.tsx:48`, a
  static theme-init script constant, not user-controlled. No issue.
- Logout clears the token (`AuthProvider.tsx:98-104`); an expired/invalid
  stored token is caught by the mount-time `/auth/me` call failing, which
  flips `isAuthenticated` false. No issue found.

### 6. Infrastructure

Files inspected: `Dockerfile`, `deploy/railway/api.railway.toml`,
`deploy/railway/web.railway.toml`, `.github/workflows/ci.yml`,
`.github/workflows/staging-monitor.yml`.

- `Dockerfile`: non-root user `simo` (UID 10001), no secrets baked into the
  image, `EXPOSE 8000`, healthcheck hits `/health`, production `CMD` runs
  Uvicorn only, no shell entrypoint. Matches Sprint 018's verified
  evidence. No issue found.
- CI (`ci.yml`): backend (pytest + migrations), frontend
  (lint/typecheck/tests/build), and a Playwright e2e job all present. No
  dependency/secret-scanning step (no `pip-audit`, no `npm audit`, no
  `gitleaks`/`trufflehog`). Real but lower-priority gap — closer to CI
  hygiene than an exploitable weakness; explicitly deferred (see Phase 2).
- Railway configs: `preDeployCommand` runs a runtime config check, then
  `alembic upgrade head`, then `alembic current` before the app starts —
  fail-fast-on-bad-config, consistent with `config.py`'s validators. No
  issue found.

### 7. Tests / documentation

- `tests/test_command_centre.py` already carries exactly the RBAC pattern
  this sprint needs to replicate for the legacy endpoint
  (`test_owner_and_staff_can_both_access_command_centre`,
  `test_role_none_is_forbidden`), including the `auth_service.create_user(...,
  role=...)` helper for constructing a Staff or role-less user directly.
  `tests/test_dashboard.py` has no equivalent.
- No dedicated `test_security.py`/`test_rbac.py` file exists — RBAC
  assertions live per-feature, an established, intentional repo pattern
  (not itself a gap).
- Reviewed `docs/SPRINTS/sprint-018.md` through `sprint-025.md` and
  `docs/DECISIONS.md` for prior contracts: rate limiting, password reset,
  malware scanning, quotas, billing, WebSockets/SSE, and full APM were
  explicitly and repeatedly deferred and are not duplicated here. The
  `/api/v1/dashboard` RBAC-gate outlier is referenced (without being
  fixed) across Sprints 022–025.

### No exposed live credential found

`git ls-files` plus a review of every tracked env-config file confirms only
`*.example` placeholder files are tracked, all containing clearly-labeled
dev-only defaults. Nothing to redact or report as an incident.

## Recommended Sprint 026 scope (narrow, see Phase 2 for the locked contract)

Ranked by the sprint's own priority order:

1. **Close the `/api/v1/dashboard` RBAC-gate outlier** (auth/RBAC weakness,
   priority tier 1) — add `require_role(OWNER, STAFF)`, matching every
   sibling route and its own Sprint-025 replacement.
2. **Login/signup brute-force throttling** (missing HTTP hardening with
   real production value, priority tier 5) — no rate limiting exists
   anywhere in the stack; explicitly deferred since Sprint 018.
3. **Security response headers middleware** (priority tier 5) —
   `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and HSTS
   in production. Self-contained, response-only, low risk.

## Explicitly deferred (not in Sprint 026 scope)

- **Host-header / `TrustedHostMiddleware` validation** — real but lower
  value given the reverse-proxy edge already validates routing by host,
  and Railway's dynamic per-environment domains make a correct app-level
  allow-list require new environment wiring; a misconfigured allow-list
  fails closed and can take the API down. Left for a dedicated sprint with
  Railway domain values confirmed in hand.
- **CI dependency/secret-scanning step** (`pip-audit`/`npm audit`/`gitleaks`) —
  real hygiene gap, but CI-hygiene not an exploitable weakness; good
  candidate for a future sprint, not this narrow one.
- **JWT storage move to httpOnly cookies** — architectural change,
  disproportionate for this sprint; the client-side role is already
  correctly treated as cosmetic-only.
- **Refresh-token support, password-reset flow, malware scanning, global
  request-body-size middleware, quotas, billing, WebSockets/SSE, full
  APM** — all previously and correctly deferred by Sprint 018 and not
  reopened here.

## Phase 2 — Contract lock

Status: locked.

Three narrow, verified behaviors, each independently testable, independently
revertible, and each addressing a real gap confirmed by reading the actual
code in Phase 1 (not assumed).

### Contract A — `/api/v1/dashboard` RBAC gate

- **Exact behavior changed.** `GET /api/v1/dashboard`
  (`app/api/v1/core.py:77-85`) currently depends on `get_current_user` only.
  It will depend on `require_role(UserRole.OWNER, UserRole.STAFF)` instead —
  the same gate already used by its sibling
  `GET /api/v1/dashboard/command-centre` (`app/dashboard/router.py:18`).
  Both roles that can be authenticated at all today (`OWNER`, `STAFF`) keep
  identical access; only a `role=None` account's access changes, from 200 to
  403.
- **Exact tests.** New tests in `tests/test_dashboard.py`, mirroring
  `tests/test_command_centre.py`'s existing pattern:
  - `test_dashboard_role_none_is_forbidden` — build a user with no role via
    `auth_service.create_user(db, tenant_id=..., name=..., email=..., password=...)`
    (role omitted → `None`), log in, `GET /api/v1/dashboard` → expect 403.
  - `test_dashboard_staff_can_access` — build a `role="Staff"` user via the
    same helper, log in, `GET /api/v1/dashboard` → expect 200 (locks in that
    the fix doesn't regress the one role besides Owner that must keep
    working).
- **Expected RED reason.** Before the change, `test_dashboard_role_none_is_forbidden`
  fails because the endpoint returns 200 (no role check exists yet) instead
  of the expected 403.
- **Implementation boundary.** One dependency swap in
  `app/api/v1/core.py`, plus the import of `require_role`/`UserRole`
  already used elsewhere in that pattern. No other route, service, or
  schema touched.
- **Migration impact.** None — no schema change.
- **Staging verification.** `GET /api/v1/dashboard` with an Owner token →
  200; with a Staff token → 200; with no token → 401 (already covered);
  with a deliberately role-less token (created the same way as the new
  unit test, via a direct DB session against staging) → 403.
- **Rollback.** Revert the single dependency line and the two new test
  functions; no data or migration rollback needed.

### Contract B — Login brute-force throttling

- **Exact behavior changed.** `POST /api/v1/auth/login`
  (`app/auth/router.py:26-35`) currently has no limit on failed attempts.
  A new in-process, per-email, fixed-window limiter
  (`app/auth/rate_limit.py`, `LoginRateLimiter`) is checked before
  credentials are verified and incremented only on a failed attempt (401);
  a successful login always clears that email's counter. Default:
  5 failed attempts per 60-second window (new `Settings` fields
  `login_rate_limit_max_attempts=5`, `login_rate_limit_window_seconds=60.0`
  in `app/core/config.py`, following the existing plain-field convention —
  not secrets, no new production-validation branch needed). Exceeding the
  limit returns `429` with a `Retry-After` header, before `authenticate()`
  runs (also avoids wasted bcrypt work under attack).
  **Scope note:** `POST /api/v1/auth/signup` is deliberately NOT
  throttled in this sprint — see Deferred work below.
- **Exact tests.**
  - New `tests/test_login_rate_limit.py`:
    - Unit tests against `LoginRateLimiter` directly with an injected fake
      clock (no real sleeps): allows up to `max_attempts` failures then
      blocks; a window reset (fake clock advanced past `window_seconds`)
      allows again; `reset()` clears a key; two different emails are
      tracked independently.
    - HTTP integration tests against a real running app (default
      settings): fail login 5 times for one freshly created test account →
      each 401; the 6th attempt (even with the correct password) → 429
      with a `Retry-After` header present; a second, different test
      account is unaffected in the same window (isolation); a passing
      login after 2 failures (below the limit) resets the counter, so a
      subsequent single failure afterward does not immediately 429
      (proves reset-on-success).
- **Expected RED reason.** Before the change, the "6th attempt" HTTP test
  fails because the endpoint returns 401 (wrong password checked normally)
  instead of the expected 429 — no limiter exists yet to short-circuit it.
- **Implementation boundary.** One new file (`app/auth/rate_limit.py`,
  ~50 lines, no external dependency — no Redis/`slowapi` exists in
  `requirements.txt` and none is added), two new `Settings` fields, and a
  ~6-line change to `app/auth/router.py`'s `login` handler. Signup is not
  touched. No other route touched.
- **Migration impact.** None — in-memory only, no schema change.
- **Known, accepted limitation (documented, not fixed this sprint).**
  Per-process only: does not share state across horizontally scaled
  instances (matches the existing accepted `UPLOAD_DIR` single-instance
  limitation, ADR-032) and resets on redeploy/restart. Meaningful against
  today's actual deployment (single Railway API instance) and against an
  unthrottled brute-force script, which is the verified real gap; not a
  distributed rate limiter.
- **Staging verification.** From a real HTTP client against staging: 5
  failed logins against a disposable staging test account → 401 each; 6th
  → 429 with `Retry-After`; a valid login for a different account in the
  same window → 200 (unaffected); confirm a normal single mistyped-password
  retry by a real user is never blocked (only the 6th+ consecutive failure
  is).
- **Rollback.** Revert `app/auth/router.py`'s three added lines, delete
  `app/auth/rate_limit.py`, and revert the two `Settings` fields
  (defaults only, no data implication). No migration rollback needed.

### Contract C — Security response headers

- **Exact behavior changed.** Every HTTP response (including error
  responses and `/health`/`/ready`) gains:
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin` always, plus
  `Strict-Transport-Security: max-age=63072000; includeSubDomains` added
  only when `app_env == production` (HSTS on `http://localhost` in
  development would be actively harmful — it caches in the browser).
  Implemented as a new `SecurityHeadersMiddleware` in
  `app/core/middleware.py`, registered in `app/main.py` alongside
  `RequestContextMiddleware`.
- **Exact tests.** New `tests/test_security_headers.py`, using the
  existing `make_development_settings`/`make_production_settings` helpers
  from `tests/test_runtime_http.py` (imported, not duplicated) plus
  `create_app`:
  - `test_security_headers_present_on_a_normal_response` (dev settings,
    `GET /health`) — asserts the three always-on headers and their exact
    values.
  - `test_security_headers_present_on_an_error_response` — asserts the
    same headers survive a 404/500, not just 200s.
  - `test_hsts_present_in_production` (production settings) — asserts
    `Strict-Transport-Security` is present with the exact value.
  - `test_hsts_absent_outside_production` (development settings) —
    asserts the header is absent.
- **Expected RED reason.** Before the change, every new assertion fails
  because the header is simply missing from the response (`KeyError`/
  membership assertion failure) — no such middleware exists yet.
- **Implementation boundary.** One new middleware class (~15 lines) plus
  one `add_middleware` call in `app/main.py`. Response-header-only; does
  not touch routing, auth, or any business logic. Verified low blast
  radius: cannot change CORS behavior (registered independently of
  `CORSMiddleware`) and cannot alter status codes or bodies.
- **Migration impact.** None.
- **Staging verification.** `curl -i` (or the staging smoke suite) against
  a real staging response confirms all three always-on headers and,
  because staging runs with `APP_ENV=production`
  (`deploy/railway/staging.env.example:2`), the HSTS header too. Confirm
  the frontend (staging web) still loads and authenticates normally (HSTS/
  frame-ancestors headers on the API don't affect a separate-origin
  frontend's own headers).
- **Rollback.** Revert the `app/main.py` `add_middleware` call and delete
  the middleware class; no data or migration rollback needed.

### Deferred work (restated from Phase 1, unchanged by contract lock)

Host-header/`TrustedHostMiddleware` validation, CI dependency/secret
scanning, JWT httpOnly-cookie storage, signup throttling, refresh tokens,
password reset, malware scanning, global request-body-size middleware,
quotas, billing, WebSockets/SSE, full APM. None of these are started or
partially started by this contract.

### Production untouched requirement

No contract above touches `deploy/railway/api.railway.toml`,
`deploy/railway/web.railway.toml`, any production Railway service/variable,
any production database, or DNS. All three are pure application-code
changes verified first on the local test suite, then on staging only,
per Phase 6.

## Phase 3 — TDD implementation evidence

For each contract: RED confirmed first for the expected reason, then a
minimal GREEN implementation.

- **Contract A.** `test_dashboard_role_none_is_forbidden` RED: 200 instead
  of 403 (no gate existed). Implementation: swapped `get_current_user` for
  `require_role(UserRole.OWNER, UserRole.STAFF)` in
  `app/api/v1/core.py`. GREEN: `tests/test_dashboard.py` 5/5 passed
  (including the pre-existing `test_dashboard_staff_can_access`-equivalent
  regression coverage added alongside it).
- **Contract B.** RED: `tests/test_login_rate_limit.py` failed to even
  collect (`ModuleNotFoundError: app.auth.rate_limit`) — the clearest
  possible "feature missing" signal. Implementation: new
  `app/auth/rate_limit.py` (`LoginRateLimiter`), two new `Settings`
  fields, and a ~6-line change to `app/auth/router.py`'s `login` handler.
  GREEN: 8/8 new tests passed (4 unit tests against the limiter with an
  injected fake clock, 4 HTTP integration tests against the real
  endpoint). `tests/test_auth.py`'s existing single-failure login tests
  re-verified unaffected (10/10 passed).
- **Contract C.** RED: `tests/test_security_headers.py` — 3/4 new
  assertions failed with `KeyError` on the missing header (the 4th,
  "HSTS absent outside production," passed trivially both before and
  after, since no HSTS header exists anywhere yet). Implementation: new
  `SecurityHeadersMiddleware` in `app/core/middleware.py`, registered as
  the outermost middleware in `app/main.py`. GREEN: 4/4 passed.
  `tests/test_runtime_http.py`/`test_runtime_startup.py`/
  `test_runtime_config.py` (71 tests covering CORS/request-ID/logging/
  production-config behavior this middleware sits alongside) re-verified
  unaffected.

## Phase 4 — Full local verification

- **Backend.** Full suite: 428 passed, 1 skipped, 0 failed
  (`pytest`, local Postgres via `docker-compose.yml`, `.venv` from
  `requirements.txt`). One test,
  `test_follow_up_automation.py::test_run_creates_exactly_one_notification_for_a_stale_enquiry_with_assigned_staff`,
  failed once on an earlier full-suite run and passed both standalone and
  on a subsequent full-suite re-run — an existing order-dependent flake
  (the same class of shared-seeded-tenant pollution
  `tests/test_command_centre.py` already documents from Sprint 024),
  unrelated to any Sprint 026 file; not introduced by this sprint.
- **Alembic.** `alembic heads` → single head `2243d66f83da`; `alembic
  current` → matches; `alembic check` → "No new upgrade operations
  detected." Confirms Phase 1's reconstructed-from-files chain live
  against a real database, and confirms zero migration impact from all
  three contracts, as specified.
- **Frontend.** `pnpm lint` clean; `pnpm --filter web test` (Vitest) 49
  passed; `pnpm --filter web test:runtime-config` 7 passed;
  `pnpm --filter web test:docker-contract` 5 passed; `pnpm build`
  (Next.js production build) succeeded. No frontend file was changed by
  this sprint, so these are confirmation that an unrelated backend change
  didn't regress anything, not new coverage. (The workspace's
  `check-types` step only has a script defined for the shared `@repo/ui`
  package, not the `web` app itself — pre-existing repo structure, not a
  Sprint 026 gap; `pnpm build`'s own `tsc` pass, which did run against
  `web`, is what actually type-checks the app and passed.)
- **Playwright E2E.** `pnpm --filter web test:e2e` — 6/6 passed against a
  real local FastAPI server and a real local Next.js dev server
  (`http://127.0.0.1:8000` / `http://localhost:3000`, per
  `playwright.config.ts`'s hardcoded loopback-only URLs), covering
  enquiry conversion, project operations, quote handoff, site-visit
  scheduling, follow-up automation, and the business command centre — the
  last of which exercises real login + an authenticated dashboard-style
  fetch, directly adjacent to Contracts A and B. First two local attempts
  hit environment-only failures unrelated to this sprint's code: (1) a
  transient Windows Turbopack dev-server worker crash (exit code
  `0xc0000142`) resolved by clearing `apps/web/.next` and retrying, and
  (2) a missing `apps/web/.env.local` (this worktree had never been run
  locally before) resolved by copying `.env.local.example`. Neither is a
  Sprint 026 regression; both are local-environment setup gaps specific
  to this fresh worktree, not present in CI.
- **Repository.** `git diff --check` clean (no whitespace errors);
  `git status --short` after each commit showed only the files each
  contract's boundary specified — no debris, no accidentally-added
  secret/config file; `git diff -- deploy/railway/ .github/workflows/`
  empty — no production/CI-config file touched by Phase 3.

## Phase 5 — Feature CI

Pushed `sprint-026-security-production-hardening-ii` to `origin` (5
commits ahead of `origin/main`'s baseline `ea4160f`). GitHub Actions run
[`33392972458`](https://github.com/SMC-OS/SMC-OS/actions/runs/33392972458)
on commit `3378677` (docs-closeout-so-far HEAD at push time): all three
jobs completed `success` — `backend` (12:40:58Z→12:43:48Z), `frontend`
(12:40:58Z→12:42:00Z), `e2e` (12:40:59Z→12:43:14Z). Feature CI green
before any staging action, per the phase ordering requirement.

## Phase 6 — Staging verification

Linked to the existing `simo-os` Railway project (workspace SMC-OS).
Confirmed the project's `production` environment has **zero service
instances** — nothing to accidentally touch there regardless of command
scope. All actions below explicitly targeted the `staging` environment
(`58f1f618-f823-4c02-80b6-b1d6b630bb76`) and, since this sprint changed no
frontend file, only the `simo-api-staging` service was redeployed
(`simo-web-staging` was left at its existing Sprint-025 deployment and
verified compatible, not redeployed).

- **Clean-commit deploy.** Per `docs/STAGING_RUNBOOK.md`'s "Clean-commit
  staging deployment" finding: `git archive 3378677 | tar -x -C
  <clean-dir>`, then `railway up -c` from that clean export against
  `simo-api-staging` in `staging` — guarantees the uploaded artifact is
  byte-for-byte the reviewed commit. Build and deploy both reported
  `SUCCESS` (deployment `389cb7c9-3c75-45fd-ab07-cb0e774acda4`).
- **`/health` = 200, `/ready` = 200** against the public staging origin
  (`simo-api-staging-staging.up.railway.app`), both with request IDs.
- **Alembic — explicit remote verification (not inferred from health),
  per the runbook's Sprint 020 rule.** `railway ssh --service
  simo-api-staging --environment staging -- alembic current` →
  `2243d66f83da (head)`, exactly matching local `alembic heads`/`current`
  from Phase 4. Zero migration drift, as the contract specified.
- **Contract C (security headers) on real staging HTTP.** `curl -sD -
  https://simo-api-staging-staging.up.railway.app/health` returned all
  four headers, including `strict-transport-security: max-age=63072000;
  includeSubDomains` (confirms the production-only HSTS branch is live,
  since staging runs `APP_ENV=production` per the runbook's release
  invariants).
- **Contract A (RBAC) on real staging HTTP, with genuinely separate
  synthetic tenants.** Signed up two fresh synthetic tenants (A, B) via
  `POST /auth/signup`. `GET /api/v1/dashboard`: Owner A → 200, Owner B →
  200, no token → 401. Created a customer in tenant A only; A's dashboard
  count incremented by exactly 1, B's stayed unchanged — tenant isolation
  confirmed live, not just in the local suite. Invited and accepted a
  real Staff user in tenant A via the actual `POST /invitations` +
  `POST /invitations/token/{token}/accept` HTTP flow (not a direct DB
  construction, since staging offers no such access) — Staff `GET
  /api/v1/dashboard` → 200, confirming the require_role gate change
  didn't regress the one non-Owner role that must keep working. The
  `role=None` → 403 case has no live HTTP path to construct on staging
  (confirmed unreachable in Phase 1) and stays covered by the local
  service-layer test only — expected, not a gap.
- **Contract B (login throttle) on real staging HTTP.** Fresh synthetic
  account: 5 wrong-password attempts → 401 each; 6th attempt, this time
  with the *correct* password → `429` with `retry-after: 54`. A separate,
  uninvolved account logged in normally (`200`) in the same window,
  confirming the limiter is scoped per-email and a real user's valid
  login is never blocked by someone else's failed attempts.
- **Staging smoke suite.** Ran `scripts/staging/smoke.py` (Sprint 019's
  22-gate harness) against the live staging origins: **14 passed, 0
  failed, 8 blocked**. Every blocked gate self-reports a specific,
  legitimate reason — five require an operator opt-in flag or
  out-of-band evidence this run didn't need (`restart_persistence`
  needs `--allow-restart`; `repository_secret_scan` must run locally,
  not against a live origin; `backup_restore` is deliberately gated
  behind the runbook's separate owner-approval drill; `migration` and
  `no_seeding` ask for evidence already independently gathered above via
  `railway ssh`). The other two (`quote_invoice`, `tenant_isolation`)
  were investigated directly: staging runs with `SEED_DATA_ENABLED=false`,
  which (per `app/core/startup.py`'s uniform seeder gate) means the
  material catalogue was never seeded on staging at all — a pre-existing
  staging-environment condition unrelated to Sprint 026, not a
  regression from this sprint's changes. Tenant isolation itself was
  already independently confirmed above via the dashboard-endpoint check
  with two real synthetic tenants.
- **Performance sanity.** `/health` and login latency sampled 5x/3x
  directly against staging: `/health` 0.17s-0.46s, `/auth/login`
  0.44s-0.70s (bcrypt-dominated, as expected — the new middleware header
  writes and the rate-limiter's in-memory dict lookup add no measurable
  overhead).
- **Browser verification (auth behavior changed).** Per the runbook's
  Sprint 021 browser-isolation finding, used a fresh MCP tab group (not a
  persistent profile) — confirmed `localStorage` held no pre-existing
  session before starting. Logged in through the real staging web UI
  (`simo-web-staging-staging.up.railway.app/login`) with a fresh
  synthetic account: sign-in succeeded, redirected into the app, the
  dashboard/command-centre page rendered real (empty-state) data with no
  console/network errors. `localStorage.clear()`'d and the tab closed
  immediately after, per the same finding.

**PRODUCTION UNTOUCHED.** Every command above named `staging` explicitly
(environment ID `58f1f618-…`); the `production` environment (`c5f88dea-…`)
was never referenced by any deploy, SSH, or link command and independently
confirmed to have zero services throughout.

## Production safety boundary (restated)

No production Railway service, database, DNS, or credential is touched by
this sprint. Staging deployment and verification only occur after feature
CI is green, per Phase 6.
