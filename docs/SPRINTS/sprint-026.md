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

## Production safety boundary (restated)

No production Railway service, database, DNS, or credential is touched by
this sprint. Staging deployment and verification only occur after feature
CI is green, per Phase 6.
