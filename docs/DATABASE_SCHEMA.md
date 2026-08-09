# SIMO OS — Database Schema

**Status: there is no database.** `app/database/models.py`, `app/database/database.py`, and `app/database/crud.py` are all empty files. No SQLAlchemy or other ORM is configured, no PostgreSQL connection exists, there's no `.env` entry for DB credentials, and no migration tool (Alembic or otherwise) is set up. This document exists so the gap is explicit rather than assumed — do not build against a schema described below as "planned" as if it already exists.

---

## 1. What actually holds data today

Nothing persists across a server restart. Three different mechanisms currently stand in for a database:

### 1.1 Hardcoded catalogue (`app/data/`)

Plain Python dictionaries, edited by hand, imported directly into `quotes/calculator.py`, `assistant/sales.py`, and `assistant/search.py`.

- `materials.py` — `MATERIALS: dict[str, {category, thickness, slab_size, finish}]`. Exactly 3 entries today: `calacatta gold`, `calacatta oro`, `nero marquina`.
- `pricing.py` — `PRICES: dict[str, float]`, one flat £-per-slab figure per material.
- `services.py` — `SERVICES: list[str]`, 4 static service names.

### 1.2 In-memory repositories (`app/activity/`, `app/notifications/`)

Introduced in Sprint 001, deliberately built behind a repository interface (`ActivityRepository`, `NotificationRepository` — both `ABC` classes) so they can be swapped for a real database-backed implementation without changing the service or router layer above them. Today both use `InMemory*Repository`, which is a Python list living in process memory — restarting `uvicorn` empties it, and Sprint 001's `seed.py` files reseed sample data on the next startup.

- **`ActivityEvent`** (`app/activity/models.py`): `id: str (uuid4)`, `type: ActivityType`, `title: str`, `description: str | None`, `timestamp: datetime`.
- **`Notification`** (`app/notifications/models.py`): `id: str (uuid4)`, `title: str`, `message: str`, `type: NotificationType`, `timestamp: datetime`, `read: bool`.

### 1.3 Request/response models with no storage at all (`app/quotes/models.py`)

`QuoteRequest` is a pydantic model used purely to validate and shape an incoming request — it is calculated against and returned in the response, never saved anywhere. Every quote the system calculates today is gone the moment the response is sent, unless the frontend happens to log it as an `ActivityEvent` (which only records a title/description string, not the structured quote data).

---

## 2. Planned schema (Sprint 002 — not yet designed in detail, not yet built)

The roadmap (`docs/ROADMAP.md`) names the entities Sprint 002 needs to introduce, based on what the application already models informally above. **Columns below are a starting point drawn from the existing pydantic models, not a finalised schema** — the actual table design is Sprint 002 work and should be revisited then, including proper foreign keys, indexes, and constraints.

| Planned table | Source of today's informal shape | Notes |
|---|---|---|
| `customers` | New — `/customers/new` currently only logs an activity event, no fields are formally modelled yet | Needs its own model; today's form collects name/email/phone client-side only |
| `quotes` | `QuoteRequest` + the response shape of `POST /quote` | Would need a foreign key to `customers` and `materials` |
| `projects` | New — `/projects/new` currently only logs an activity event | Needs its own model; today's form collects name/customer/notes client-side only |
| `materials` | `app/data/materials.py` + `pricing.py` | Real supplier pricing and a full catalogue are Sprint 005 work, not just a schema change |
| `users` | New — no user model exists anywhere yet | Needed before Sprint 003's auth work can do anything |
| `activity_log` | `ActivityEvent` (`app/activity/models.py`) | Direct table-ification of the existing pydantic model is the most likely path |
| `notifications` | `Notification` (`app/notifications/models.py`) | Same — direct table-ification is the most likely path |

**Multi-tenancy note:** the roadmap recommends adding a `tenant_id` column to every table above at creation time in Sprint 002, even though multi-tenant logic isn't enforced until Sprint 012 — this is called out in `docs/DECISIONS.md` as a decided-but-not-yet-implemented item.

---

## 3. Migration path

Because `ActivityRepository` and `NotificationRepository` already exist as abstract interfaces, the Sprint 002 migration for those two entities is: implement `PostgresActivityRepository` / `PostgresNotificationRepository` against SQLAlchemy models, then change one line each in `activity/service.py` / `notifications/service.py` to construct the service with the new repository. No router or frontend code needs to change. Every other table (customers, quotes, projects, materials, users) is new work, not a migration of an existing in-memory structure.
