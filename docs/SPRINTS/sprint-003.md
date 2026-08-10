# Sprint 003 — API Restructuring, JWT Auth Machinery, Error Handling, Tests + CI

**Status:** ✅ Done, pending commit approval. Implemented and verified against the live local PostgreSQL 16 instance; not yet committed to git (see `docs/CHANGELOG.md`'s Sprint 003 entry for the placeholder commit reference).

## Objective

Restructure the API under `/api/v1`, add real error responses in place of raw 500s, add JWT login/`/me` machinery, and add the project's first test suite and CI pipeline — the last P0 item in the "Foundation & Stabilise" milestone before any business-domain module (CRM, Materials, Projects) can be built.

Two scope decisions were made explicitly, before implementation started:
- **Auth ships as machinery only.** `POST /api/v1/auth/login` and `GET /api/v1/auth/me` work end-to-end, but no other route requires a token — see ADR-020.
- **`/api/v1` cutover is clean, not dual-mounted.** Old unprefixed paths (`/quote`, `/activity`, etc.) return `404`. Only the frontend consumes this API, so there was no external client to preserve compatibility for.

## Scope delivered

**Backend — `/api/v1` restructuring (ADR-012)**
- New `app/api/v1/` package: `__init__.py` assembles `api_router` (core + auth sub-routers) under the `/api/v1` prefix; `core.py` holds the routes formerly declared directly in `main.py` (`/process`, `/quote`, `/estimate`, `/quote/pdf`, `/dashboard`) — bodies unchanged, only their location moved.
- `app/main.py` — stripped down to app instantiation, CORS, exception handler registration, and three `include_router()` calls (`api_router`, `activity_router` and `notifications_router` both mounted with `prefix="/api/v1"`). `GET /` and `GET /health` stay unprefixed — infra/health-check endpoints, not versioned business API.
- `app/activity/router.py` and `app/notifications/router.py` — **unchanged**, per ADR-002's spirit; only how they're mounted changed.

**Backend — configuration (`app/core/config.py`)**
- `Settings` (pydantic-settings): `database_url`, `jwt_secret_key`, `jwt_algorithm`, `jwt_expire_minutes`, `seed_admin_email`, `seed_admin_password`. Reads the same root `.env` the previous direct `python-dotenv` calls did.
- `app/database/database.py` and `alembic/env.py` both now read `settings.database_url` instead of a module-level constant — one source of truth, same as before, just centralised.

**Backend — error handling (`app/core/errors.py`)**
- `KeyError` (an unrecognised `/api/v1/quote`/`/api/v1/estimate` material) → `400` with a real message, fixing the raw-500 bug documented in `docs/API_SPEC.md` since Sprint 001.
- `RequestValidationError` → `422` with a cleaner body.
- Catch-all `Exception` → logged server-side, `500` returned to the client with no stack trace leaked.

**Backend — JWT auth machinery (`app/auth/`, ADR-011)**
- `models.py` (`LoginRequest`, `TokenResponse`, `UserOut`), `security.py` (`bcrypt` hashing, `pyjwt` encode/decode), `service.py` (`AuthService.authenticate()`/`create_user()`), `router.py` (`POST /login`, `GET /me`), `dependencies.py` (`get_current_user` — a working, reusable dependency, **not attached to any other route this sprint**, ADR-020), `seed.py` (seeds one owner account from `.env` if `users` is empty, guarded like `activity/seed.py`).
- `app/database/models.py` — `User` gets a new `password_hash` column (`NOT NULL` — safe, the table had 0 rows).
- `app/database/crud.py` — `create_user`, `get_user_by_email`, `get_user_by_id`, `count_users` added alongside the existing activity/notification helpers.
- Migration `07dceec1beaf` (`alembic revision --autogenerate`), applied against the live database.

**Frontend**
- `apps/web/lib/api.ts` — `request()`'s fetch call now targets `/api/v1${path}` instead of the bare path — one change in the shared helper covers every `api.*` call site. No other frontend file touched; wiring `UserProfileMenu`/`/settings` to real login is explicitly deferred, not part of this sprint.

**Tests + CI**
- `tests/` (new): `conftest.py` (`TestClient` fixture), `test_health.py` (route-mount smoke tests + confirms old paths are gone), `test_quotes.py` (calculator math + the `400` fix, unit and over-HTTP), `test_auth.py` (login success/wrong-password/unknown-email, `/me` with valid/missing/garbage token) — all run against the real local Postgres, fixtures clean up rows they create.
- `.github/workflows/ci.yml` (new): backend job (Python 3.12, a `postgres:16-alpine` service container, `alembic upgrade head`, `pytest`), frontend job (`pnpm lint`, `check-types`, `build`).
- `pytest.ini` — test discovery config.

**Dependencies added:** `pydantic-settings`, `pyjwt`, `bcrypt`, `pytest` (plus their transitive deps — see `requirements.txt`).

## Explicitly out of scope for this sprint (by decision, not oversight)

- **No route is gated by auth.** `/api/v1/quote`, `/api/v1/activity`, `/api/v1/notifications`, etc. remain fully public (ADR-020). Enforcement is deferred to whichever future sprint first has real per-user data worth protecting.
- **No frontend login UI.** `UserProfileMenu`'s disabled items and `/settings`'s "coming soon" state are unchanged — only the mandatory `/api/v1` base-path fix touched the frontend.
- **CRUD endpoints for `customers`/`quotes`/`projects`/`materials`** — still deferred to Sprints 004–005, unchanged from the original roadmap.

## Audit results

| Check | Result |
|---|---|
| `alembic upgrade head` against the live local Postgres | ✅ Migration `07dceec1beaf` applies cleanly, `password_hash` confirmed via `\d users` |
| `pytest` (16 tests) | ✅ All passing |
| Login → `/me` round trip, wrong password, missing/garbage token | ✅ All correct status codes, verified manually via `TestClient` and directly against the running app |
| `/api/v1/quote` with an unrecognised material | ✅ `400` with a real message, not a raw `500` |
| Old unprefixed paths (`/quote`, `/dashboard`, `/activity`, `/notifications`) | ✅ All `404` — confirmed the cutover is real, not a dual-mount leftover |
| `GET /`, `GET /health` | ✅ Still respond, unprefixed |
| Seed guard (`app/auth/seed.py`) | ✅ Ran once on import, created exactly one `users` row (confirmed via `SELECT count(*)`); test fixtures that create their own users clean up after themselves, leaving the seeded row as the only one post-test-run |
| `tsc --noEmit` / `eslint .` / `next build` | Pending — run as part of the full verification pass (see §10 of the approved plan) |

## Follow-up items raised, not part of Sprint 003 scope

- Frontend login UI (form, token storage, `UserProfileMenu`/`/settings` wiring) — natural follow-up once a future sprint decides something needs auth enforcement.
- `app/core/logger.py` / lifecycle events — `app/core/` now has `config.py` and `errors.py`, but logging/lifecycle remain unbuilt placeholders.
- No refresh-token flow — access-token-only, matching the roadmap's "basic JWT auth" framing; revisit if session length becomes a real problem.
