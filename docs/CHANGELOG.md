# SIMO OS — Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/). Derived from `git log` on the `SMC-OS` repository. Dates are commit dates, not necessarily when work started.

---

## 2026-08-11 — (uncommitted) — Sprint #005 — Full Material Library + Accurate Slab-Yield Calculator

Full detail in `docs/SPRINTS/sprint-005.md`. Not yet committed — pending approval.

**Backend**
- New `app/materials/` module (`service.py`, `seed.py`) — the `materials` table (unused since Sprint 002) is now real and seeded with ~30 rows: 15 named materials across 5 categories (quartz, granite, marble, porcelain, Dekton), each in 20mm and 30mm. **Internal only** — no `/api/v1/materials` route (confirmed scope decision); consumed by `/api/v1/quote`, `/api/v1/estimate`, `/api/v1/process`.
- **Honesty note, carried into the sprint doc:** this is a reference catalogue an operator edits to match real supplier costs, not sourced from a live supplier feed.
- `app/quotes/slab_calculator.py` — replaced the Sprint 001 placeholder (`if total_length > 3.2: slabs = 2 else 1`) with a real area-based formula: standard 650mm depth, a documented 15% wastage allowance, and named constants for island/waterfall/splashback/upstand extras. Still an estimate, not a fabrication-grade nesting optimizer.
- **Thickness-aware pricing** (a real bug fix that fell out of this work): `thickness` was collected on every quote request since Sprint 001 and silently ignored in pricing. `QuoteCalculator` now looks up `(material, thickness)`, so 30mm genuinely costs more than 20mm for the first time.
- `db: Session` threaded through `QuoteCalculator`, `QuoteGenerator`, `SalesAssistant`, `SearchAssistant`, `BrainManager`, and the `/process`/`/quote`/`/estimate`/`/quote/pdf` routes — the one genuinely invasive part of this sprint, five files changing signature to reach the now-database-backed catalogue.
- Error handling unchanged: a missing `(material, thickness)` combination still raises `KeyError`, still caught by Sprint 003's existing global handler, still `400`. No new exception type introduced.
- `app/data/materials.py`/`pricing.py` — superseded, left in place (ADR-008), no longer imported anywhere.

**Frontend**
- `apps/web/types/quote.ts` — `MATERIAL_OPTIONS` expanded from 3 to 15 entries, mirroring the new seeded catalogue (hand-kept in sync, same convention as before — no new API call, per the internal-only decision).

**Tests**
- `tests/test_materials.py` (new, 5 tests): catalogue covers all 5 roadmap categories, case-insensitive lookup, unknown combination returns `None`, thickness variants priced differently.
- `tests/test_quotes.py`: updated for the new `db` fixture; added cases for thickness-based pricing and slab count scaling with job size.
- New `db` fixture in `conftest.py`, reusable by future modules.
- Full suite: 30/30 passing against the real local Postgres.

**Verified**
- `pytest` (30/30), `tsc --noEmit`, `eslint .`, `next build` all clean.
- Manual smoke test: `/api/v1/quote` 20mm vs 30mm pricing on the same material, unrecognised material/thickness still `400`, `/api/v1/process` sales/search paths work against the new catalogue.
- Real headless-browser walkthrough (Playwright, transient dev tooling): `/quotes/new`'s material dropdown shows all 15 entries; a real quote (30mm Absolute Black, 4.2m run, island) calculated correctly end-to-end — verified the exact area/slab-count/price math by hand against the formula. Test data cleaned up afterward.

## 2026-08-11 — `2f23d21` — Sprint #004 — Customers (CRM), Auth Enforcement, Login UI

Full detail in `docs/SPRINTS/sprint-004.md`.

**Backend**
- New `app/customers/` module: `models.py` (`CustomerCreate`, `CustomerOut`), `service.py` (`CustomerService` — list/get/create; `create()` also logs a real `ActivityEvent` server-side, replacing the frontend's previous standalone call), `router.py` (`GET/POST /customers`, `GET /customers/{id}`).
- **First auth-enforced routes**: all three `/api/v1/customers/*` routes require `Depends(get_current_user)` — the trigger ADR-020 described (real business data now exists). Every other route (`/quote`, `/activity`, `/notifications`, etc.) remains public. New ADR-021 documents this.
- `app/database/crud.py` — `create_customer`, `get_customer_by_id`, `list_customers` added.
- No migration needed — the `customers` table has existed since Sprint 002 with no API surface until now.

**Frontend**
- Real login for the first time: new `/login` page, `lib/auth-storage.ts` (localStorage JWT), `components/auth/AuthProvider.tsx` (context mirroring `ThemeProvider`'s shape, with an `isReady` flag to avoid a redirect race against its own mount effect). `lib/api.ts` now attaches the stored token to every call and clears it on a `401`.
- `/customers` and `/customers/new` now use real persistence instead of activity-log-only behavior; new `/customers/[id]` read-only detail page. All three redirect to `/login` if not authenticated.
- `UserProfileMenu`'s Sign out is now real (clears the token, redirects to `/login`). Profile/Settings remain disabled — unrelated to this sprint.
- Stale "Sprint 003" references in `UserProfileMenu` and `/settings` updated to reflect current reality.

**Tests**
- `tests/test_customers.py` (new, 7 tests): create/list/get round trip, `401` without a token on all three routes, `404` on an unknown id, `?limit=` respected, customer creation logs a matching `ActivityEvent`. New `auth_headers` fixture in `conftest.py`, reusable by future modules.
- Full suite: 23/23 passing against the real local Postgres.

**Verified**
- `pytest` (23/23), `tsc --noEmit`, `eslint .`, `next build` all clean.
- Real headless-browser walkthrough (Playwright, transient dev tooling — not added as a project dependency): logged-out `/customers` → `/login` redirect, login, empty list, create a customer, redirect to its detail page with the entered data, customer appears in the list, sign out → `/login`, `/customers` redirects to `/login` again post-logout. All 7 steps confirmed working; test data cleaned up afterward.

## 2026-08-10 — `195cdab` — Sprint #003 — API Restructuring, JWT Auth Machinery, Tests + CI

Full detail in `docs/SPRINTS/sprint-003.md`.

**Backend**
- Every route except `GET /`/`GET /health` moved under `/api/v1` (ADR-012) — clean cutover, old unprefixed paths now `404`. New `app/api/v1/` package.
- `app/core/config.py` — pydantic-settings `Settings`, the single source for `DATABASE_URL`, JWT config, and seed-admin credentials. `app/database/database.py` and `alembic/env.py` now read from it instead of a direct `python-dotenv` read.
- `app/core/errors.py` — global exception handlers: unrecognised `/api/v1/quote` material now returns `400` instead of a raw `500` (the bug documented in `docs/API_SPEC.md` since Sprint 001), validation errors return a clean `422` body, anything else returns a logged, non-leaking `500`.
- `app/auth/` — JWT login/`/me` machinery (ADR-011): `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `bcrypt` password hashing, a reusable `get_current_user` dependency. **Not applied to any other route this sprint** — a deliberate scope decision (ADR-020), not an oversight. One owner account seeded on startup from `.env` if `users` is empty.
- `users.password_hash` column added (migration `07dceec1beaf`), safe as a `NOT NULL` add since the table had 0 rows.
- New dependencies: `pydantic-settings`, `pyjwt`, `bcrypt`, `pytest`.

**Frontend**
- `apps/web/lib/api.ts` — every call now goes to `/api/v1/...` (one-line change in the shared `request()` helper, not per call site). No other frontend file touched — the login UI itself (wiring `UserProfileMenu`/`/settings`) is explicitly deferred, not part of this sprint's scope.

**Tests + CI**
- `pytest` suite: quote calculator math + the `400` fix, full login/`/me` flow (success, wrong password, missing/garbage token), route-mount smoke tests confirming the `/api/v1` cutover and that old paths are gone. 16 tests, all passing against the real local Postgres.
- `.github/workflows/ci.yml` — new: backend job (Postgres service container, `alembic upgrade head`, `pytest`), frontend job (`pnpm lint`, `check-types`, `build`).

**Also fixed:** this changelog previously listed Sprint 002 as "(uncommitted) — pending approval" even though it had already been committed as `4929ff3` — a documentation lag caught during Sprint 003's investigation phase, corrected below.

## 2026-08-10 — `4929ff3` — Sprint #002 — Database Foundation

Full detail in `docs/SPRINTS/sprint-002.md`.

**Backend**
- PostgreSQL 16 + SQLAlchemy 2.0 + Alembic added. New `app/database/` module: `database.py` (engine/session/`get_db`), `models.py` (7 tables: `Customer`, `Quote`, `Project`, `Material`, `User`, `ActivityLog`, `NotificationRecord`, each with `tenant_id`), `crud.py` (helpers for `activity_log`/`notifications` only).
- `PostgresActivityRepository` / `PostgresNotificationRepository` added and made the default for `activity_service`/`notification_service` — `app/activity/router.py` and `app/notifications/router.py` unchanged, per ADR-001. `InMemory*Repository` still present, no longer used by default.
- `seed_activity()`/`seed_notifications()` guards (already present since Sprint 001) now do real work: they prevent duplicate seed rows across restarts against the real database.
- **No new API routes.** `customers`, `quotes`, `projects`, `materials`, `users` tables exist with zero endpoints reading/writing them — deliberately deferred to Sprints 003–006.
- `requirements.txt` re-encoded from UTF-16 to UTF-8 (long-standing bug, now fixed) and 3 packages added: `sqlalchemy==2.0.36`, `alembic==1.14.0`, `psycopg[binary]==3.2.3`.

**Infrastructure**
- `docker-compose.yml` (root): single `postgres:16-alpine` service for local dev, no other infrastructure.
- `.env.example` (root, tracked) and `.env` (root, gitignored): `POSTGRES_*` values + `DATABASE_URL`.

**Verified**
- `alembic upgrade head` creates all 7 tables with `tenant_id` present on each, against a real PostgreSQL 16 instance.
- Activity/notification repository CRUD, mark-as-read, and persistence across a backend restart all confirmed against real Postgres — no duplicate seed rows on the second startup.
- All 7 original routes (`/`, `/health`, `/process`, `/quote`, `/estimate`, `/quote/pdf`, `/dashboard`) return unchanged response shapes.
- Frontend `tsc --noEmit`, `eslint`, `next build` all clean — no frontend file touched this sprint.

## 2026-08-09 — `d01f07e` — docs: add example environment configuration

Added `apps/web/.env.local.example` (template for `NEXT_PUBLIC_API_URL`) after fixing the `.gitignore` pattern that had been silently excluding it.

## 2026-08-09 — `d58af5c` — chore: improve .gitignore and remove generated files from version control

- Rewrote the root `.gitignore` to add Python coverage (`__pycache__/`, `*.py[cod]`, `.venv/`, the stray `SIMO-OS.VENVA` folder, `quote.pdf`), editor/OS coverage (`.vscode/`, `.idea/`, `.DS_Store`, etc.), and expanded log/build-artifact patterns.
- Fixed `apps/web/.gitignore`'s `.env*` pattern with `!.env.*.example` negation so template env files can be tracked.
- Untracked (not deleted from disk) 54 already-committed `.pyc`/`__pycache__` files and `.vscode/settings.json`, which had been swept into the Sprint 001 commit before the backend had any Python-specific `.gitignore` rules.

## 2026-08-09 — `2e2f284` — docs: add SYSTEM_ARCHITECTURE

Added the canonical `SYSTEM_ARCHITECTURE.md` reference: folder structure, backend/frontend module map, full route table, API flow diagrams, design principles, coding standards, and the Sprint 002–016 roadmap.

## 2026-08-09 — `3cf51c8` — Sprint #001 - Professional Application Shell

The largest commit to date. Summary (full detail in `docs/SPRINTS/sprint-001.md`):

**Backend (additive only — no existing route changed)**
- New `app/activity/` module: repository-backed Recent Activity feed (`GET/POST /activity`, in-memory, seeded with sample events).
- New `app/notifications/` module: notification centre (`GET/POST /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{notification_id}/read`, in-memory, seeded).
- `app/main.py`: two `include_router` calls added plus seed calls — no existing route body touched.

**Frontend**
- Full application shell: collapsible sidebar with mobile drawer, topbar, global search (Cmd/Ctrl+K command palette), notifications dropdown, user profile menu, dark mode (class-based, persisted, no flash on load).
- Dashboard rebuilt from reusable components (`StatGrid`/`StatCard` with animated transitions, `RecentActivityPanel`, `QuickActions`, `DashboardStatusBar` for loading/error/offline), all polling every 5 seconds.
- New functional pages: `/quotes/new` (calls the real `POST /quote` engine), `/customers/new` and `/projects/new` (log real activity events, honestly badged as not yet persisted), `/ai-assistant` (calls `POST /process`), plus index pages for Quotes/Customers/Projects and a "coming soon" `/settings`.
- 14 obsolete files (3 duplicate empty `Card.tsx` components, the dead/broken `Dashboard.tsx`, empty stub components, and 7 files that were accidentally blocking real folder names) archived to `apps/web/_legacy/`, not deleted.

**Verification:** `tsc --noEmit` clean, `eslint` clean (6 real issues found and fixed), `next build` succeeds, all original and new backend routes smoke-tested.

## 2026-07-28 — `f812e56` — Initial commit from create-turbo

The starting point: a stock `create-turbo` scaffold (`apps/web`, `apps/docs`, `packages/ui`, `packages/eslint-config`, `packages/typescript-config`). The Python backend (`app/`) was not part of this commit — it was added to the working tree later, outside version control, and only entered git history via the Sprint 001 commit above.

---

*Add a new entry above this line at the top of the next section whenever a sprint or notable change lands. Keep the git commit hash so this stays traceable back to `git log`.*
