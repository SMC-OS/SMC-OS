# SIMO OS — Database Schema

**Status: schema implemented as of Sprint 002; API surface growing sprint by sprint.** PostgreSQL 16, SQLAlchemy 2.0 declarative models (`app/database/models.py`), Alembic migrations (`alembic/`), and a real engine/session layer (`app/database/database.py`) all exist. All 7 tables below were created by the initial migration with a live `tenant_id` column each. `users` (Sprint 003) and `customers` (Sprint 004) now have real, working API surfaces alongside `activity_log`/`notifications` (Sprint 001–002) — `quotes`, `projects`, and `materials` remain schema-only, deferred to Sprints 005–006.

---

## 1. What actually holds data today

### 1.1 Hardcoded catalogue (`app/data/`) — unchanged by Sprint 002

Plain Python dictionaries, edited by hand, imported directly into `quotes/calculator.py`, `assistant/sales.py`, and `assistant/search.py`. Not migrated to the `materials` table yet — that's Sprint 005 (real supplier pricing, not just a schema move).

- `materials.py` — `MATERIALS: dict[str, {category, thickness, slab_size, finish}]`. Exactly 3 entries today: `calacatta gold`, `calacatta oro`, `nero marquina`.
- `pricing.py` — `PRICES: dict[str, float]`, one flat £-per-slab figure per material.
- `services.py` — `SERVICES: list[str]`, 4 static service names.

### 1.2 PostgreSQL-backed repositories (`app/activity/`, `app/notifications/`) — Postgres since Sprint 002

Both are built behind a repository interface (`ActivityRepository`, `NotificationRepository` — `ABC` classes), introduced in Sprint 001 specifically so this swap wouldn't require touching the service or router layer. As of Sprint 002, `PostgresActivityRepository`/`PostgresNotificationRepository` are the default implementation — data survives a server restart, and `InMemory*Repository` still exists in the same files but is no longer constructed by default (available for tests or a future in-memory mode).

- **`ActivityEvent`** (pydantic, `app/activity/models.py`) ↔ **`activity_log`** (SQLAlchemy, `app/database/models.py`): `id`, `type`, `title`, `description`, `timestamp` — direct 1:1 mapping, `str(uuid.UUID) ↔ uuid.UUID` for the id.
- **`Notification`** (pydantic, `app/notifications/models.py`) ↔ **`notifications`** table, modelled as `NotificationRecord` in SQLAlchemy (named differently to avoid a class name collision with the pydantic model) — same direct mapping.

### 1.3 Request/response models with no storage at all (`app/quotes/models.py`) — unchanged by Sprint 002

`QuoteRequest` is a pydantic model used purely to validate and shape an incoming request — it is calculated against and returned in the response, never saved anywhere. A `quotes` table exists (§2) but nothing writes to it yet; every quote the system calculates is still gone the moment the response is sent, unless the frontend logs it as an `ActivityEvent`.

---

## 2. Schema (Sprint 002)

Every table below exists in PostgreSQL as of Sprint 002's migration (`alembic/versions/a22b1189f8e7_*.py`). **Columns are a starting point drawn from the existing pydantic models and the roadmap's informal shapes, not a finalised design** — foreign keys are present where an obvious relationship exists (`quotes.customer_id`, `projects.customer_id` → `customers.id`), but indexes, constraints, and any columns a future sprint's UI actually needs are that sprint's work, not Sprint 002's.

| Table | Columns | API surface today |
|---|---|---|
| `customers` | `id` (UUID, PK), `tenant_id` (UUID, nullable), `name`, `email`, `phone`, `created_at` | **Live** — `GET/POST /api/v1/customers`, `GET /api/v1/customers/{id}` (Sprint 004, auth-required) |
| `quotes` | `id`, `tenant_id`, `customer_id` (FK → `customers.id`), `material`, `thickness`, `kitchen_length`, `island`, `waterfall`, `splashback`, `upstands`, `postcode`, `price_per_slab`, `price_before_vat`, `vat`, `total`, `created_at` | None — quote calculation still happens via `POST /quote` with no persistence |
| `projects` | `id`, `tenant_id`, `customer_id` (FK → `customers.id`), `name`, `notes`, `created_at` | None — Sprint 006 |
| `materials` | `id`, `tenant_id`, `name`, `category`, `thickness`, `slab_size`, `finish`, `price`, `created_at` | None — Sprint 005 |
| `users` | `id`, `tenant_id`, `name`, `email` (unique), `role`, `created_at` | None — Sprint 003 (auth) |
| `activity_log` | `id`, `tenant_id`, `type`, `title`, `description`, `timestamp` | **Live** — `GET/POST /activity` |
| `notifications` | `id`, `tenant_id`, `title`, `message`, `type`, `read`, `timestamp` | **Live** — `GET/POST /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{notification_id}/read` |

**Multi-tenancy:** every table carries a nullable `tenant_id` (UUID) column, per ADR-013 — added now, at zero enforcement cost, because retrofitting it onto tables with real data later would be far more expensive. There is no `tenants` table, so it is not a foreign key. Nothing reads or filters by it yet; enforcement is Sprint 012.

---

## 3. What Sprint 002 deliberately did not build

Explicit decision (see `docs/DECISIONS.md` and `docs/SPRINTS/sprint-002.md`): no new CRUD API endpoints for any of the 5 new tables. The database foundation and models exist; the API surface reading/writing them arrives with each table's own sprint (`customers` → Sprint 004 ✅, `quotes`/`projects` → Sprint 006, `materials` → Sprint 005, `users` → Sprint 003's auth work ✅). `app/database/crud.py` now has helpers for `activity_log`/`notifications` (Sprint 002), `users` (Sprint 003), and `customers` (Sprint 004) — still no generic CRUD for `quotes`/`projects`/`materials`.

## 4. Local development setup

`docker-compose.yml` (repo root) runs a single `postgres:16-alpine` service. Copy `.env.example` to `.env`, run `docker compose up -d`, then `alembic upgrade head`. See `docs/SYSTEM_ARCHITECTURE.md` §2.3 for details. `DATABASE_URL` is read from `.env` by `app/database/database.py` (and by `alembic/env.py`, which imports the same value — one source of truth for the connection string).
