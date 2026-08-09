# Sprint 002 — Database Foundation

**Status:** ⬜ Not started. Nothing in this document has been built yet — it is the plan, not a record of work done. Do not treat any of the below as implemented; check `app/database/{models,database,crud}.py` (all empty as of Sprint 001) before assuming otherwise.

## Objective (planned)

Give SIMO OS a real database, replacing the hardcoded catalogue and in-memory repositories introduced in Sprint 001 with PostgreSQL-backed persistence, without changing any frontend code.

## Planned scope

Per `docs/ROADMAP.md`:

- PostgreSQL + SQLAlchemy 2.0 + Alembic set up
- Core models created: `Customer`, `Quote`, `Project`, `Material`, `User`, `ActivityLog`, `Notification` — see `docs/DATABASE_SCHEMA.md` §2 for the informal starting shapes these should draw from (not a finalised schema)
- `InMemoryActivityRepository` and `InMemoryNotificationRepository` swapped for Postgres-backed implementations of the existing `ActivityRepository`/`NotificationRepository` interfaces (`app/activity/repository.py`, `app/notifications/repository.py`) — per ADR-001 in `docs/DECISIONS.md`, this should require no changes to `service.py`, `router.py`, or any frontend code
- Per ADR-013, add a `tenant_id` column to every new table now, even though multi-tenancy isn't enforced until Sprint 012

## Explicitly out of scope for this sprint

- CRM UI (Sprint 004)
- Real material catalogue / supplier pricing (Sprint 005)
- Authentication (Sprint 003) — the `User` table is created here, but login/JWT logic is not

## Dependencies

Sprint 001 (done) — this sprint builds directly on the repository-pattern groundwork it laid for `activity`/`notifications`.

## When this sprint completes

Update this file with what was actually built (mirroring the structure of `docs/SPRINTS/sprint-001.md`: scope delivered, audit results, follow-ups raised), change its Status line to ✅ Done, and update the corresponding row in `docs/ROADMAP.md`.
