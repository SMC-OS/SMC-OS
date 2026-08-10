# Sprint 002 — Database Foundation

**Status:** ✅ Done, pending commit approval. Implemented against a live PostgreSQL 16 instance and fully smoke-tested; not yet committed to git (awaiting explicit approval — see `docs/CHANGELOG.md`'s Sprint 002 entry for the placeholder commit reference).

## Objective

Give SIMO OS a real database, replacing the in-memory repositories introduced in Sprint 001 with PostgreSQL-backed persistence, without changing any frontend code or the external API surface.

## Scope delivered

**Infrastructure**
- `docker-compose.yml` (root) — single `postgres:16-alpine` service, dev-only. No pgAdmin, no app container, no production config.
- `.env.example` (root, tracked) / `.env` (root, gitignored) — `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/`POSTGRES_PORT` and `DATABASE_URL`.
- `requirements.txt` — re-encoded from UTF-16 to UTF-8 (pre-existing bug, now fixed); added `sqlalchemy==2.0.36`, `alembic==1.14.0`, `psycopg[binary]==3.2.3`.

**Database layer — new `app/database/` module**
- `database.py` — SQLAlchemy engine, `SessionLocal`, declarative `Base`, `get_db()` FastAPI dependency (not yet used by any route — provided for future route-level work). Reads `DATABASE_URL` via `python-dotenv`, deliberately not through a new settings module (`core/config.py` stays empty — that's Sprint 003).
- `models.py` — 7 tables: `Customer`, `Quote`, `Project`, `Material`, `User`, `ActivityLog`, `NotificationRecord` (named to avoid colliding with the pydantic `Notification` model). Every table has a nullable `tenant_id` (ADR-013). `Quote`/`Project` have a `customer_id` FK to `customers.id`.
- `crud.py` — CRUD helpers, scoped to exactly what `activity_log`/`notifications` need. No generic CRUD for the other 5 tables (no API surface uses them yet).
- `alembic/`, `alembic.ini` — migration tooling. `alembic/env.py` imports `app.database.database.DATABASE_URL` and `app.database.models` directly, so migrations always target the same database the app does. One migration so far: `a22b1189f8e7` (initial schema, all 7 tables).

**Repository swap — per ADR-001, zero router/frontend changes**
- `app/activity/repository.py` — `PostgresActivityRepository` added; `activity_service` (in `service.py`) now constructs it by default. `InMemoryActivityRepository` still exists, unused by default.
- `app/notifications/repository.py` — same pattern: `PostgresNotificationRepository` added and made the default. `mark_read()` defensively catches a malformed (non-UUID) id and returns `None`, preserving the in-memory version's behaviour of never raising for a bad id — the router still turns that into the documented 404.
- `app/activity/seed.py` / `app/notifications/seed.py` — no code change needed. Their existing "only seed if the repository is already non-empty" guard (written in Sprint 001, originally for the in-memory-reload case) works identically against Postgres: verified it prevents duplicate rows across a real restart.

## Explicitly out of scope for this sprint (by decision, not oversight)

- **No new API endpoints** for `customers`, `quotes`, `projects`, `materials`, or `users` — the tables exist, nothing reads or writes them via HTTP yet. CRM UI (Sprint 004), Material Library (Sprint 005), Projects pipeline (Sprint 006), auth (Sprint 003) each bring their own table's endpoints.
- `pytest`/CI — Sprint 003, per the roadmap. This sprint used the same manual/scripted smoke-testing approach as Sprint 001.
- `core/config.py` / `pydantic-settings` — Sprint 003. `database.py` reads `DATABASE_URL` directly via `python-dotenv` to avoid anticipating that work.

## Audit results

| Check | Result |
|---|---|
| `alembic upgrade head` against a real PostgreSQL 16 instance | ✅ Succeeds, creates all 7 tables |
| `tenant_id` present on every core table | ✅ Confirmed via `information_schema.columns` |
| Activity repository: add + list | ✅ `POST`/`GET /activity` round-trip correctly |
| Notification repository: add + list + mark-read | ✅ `POST`/`GET /notifications`, `PATCH .../read` all correct; malformed id still returns 404 |
| Persistence across a real backend restart | ✅ Data (including a manually-marked-read notification) survived a full process stop/start |
| Seed guard prevents duplicate rows on restart | ✅ Activity stayed at 7 rows, notifications at 5, across two startups (not 13/9) |
| All 7 original routes (`/`, `/health`, `/process`, `/quote`, `/estimate`, `/quote/pdf`, `/dashboard`) | ✅ All return 200, byte-identical response shapes to `docs/API_SPEC.md` |
| `tsc --noEmit` (frontend) | ✅ 0 errors — no frontend file touched this sprint |
| `eslint .` (frontend) | ✅ 0 errors, 0 warnings |
| `next build` (frontend) | ✅ Succeeds (verified via the same temporary local-font workaround as Sprint 001, in a disposable copy only — see `docs/SPRINTS/sprint-001.md`'s "Not verified" note; never applied to real source) |
| `requirements.txt` encoding | ✅ Fixed — UTF-8/ASCII, confirmed with `file` |

### Sandbox verification note

The verification environment had no Docker available, so `docker-compose.yml` itself could not be run directly in this sandbox. It was verified by: (1) confirming it's a standard single-service `postgres:16-alpine` compose file with no unusual configuration, and (2) running the exact same schema/migration/repository work against a real PostgreSQL 16 server (via the `pgserver` package's bundled binaries, started manually with matching credentials) to prove the SQLAlchemy models, Alembic migration, and repository code are all correct against genuine Postgres — not simulated. `docker compose up -d` itself should be verified once more on a machine with Docker before relying on it day-to-day.

## Not verified

Same visual/browser caveat as Sprint 001 — no running browser in the sandbox, and this sprint touched no frontend code regardless.

## Follow-up items raised, not part of Sprint 002 scope

- The pre-existing 36-file line-ending-only working-tree diff (LF→CRLF, zero content change, flagged in the original Sprint 002 brief) remains untouched — not part of this sprint's commit.
- `services/simo-router/`, `apps/web/services/`, `apps/web/utils/` (undocumented, empty/untracked directories) — left completely untouched, per explicit instruction.
- `CHANGELOG.md`'s Sprint 002 entry currently says "(uncommitted)" in place of a commit hash — update it to the real short hash once this sprint is committed.
