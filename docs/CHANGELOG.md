# SIMO OS — Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/). Derived from `git log` on the `SMC-OS` repository. Dates are commit dates, not necessarily when work started.

---

## 2026-08-10 — (uncommitted) — Sprint #003 — API Restructuring, JWT Auth Machinery, Tests + CI

Full detail in `docs/SPRINTS/sprint-003.md`. Not yet committed — pending approval.

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
