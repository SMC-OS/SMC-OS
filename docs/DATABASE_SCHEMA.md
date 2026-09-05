# GeoCore — Database Schema

**Status: 8 tables as of Sprint 008/009 (the original 7 plus `tenants`); tenant-isolation-enforced as of Sprint 012.** PostgreSQL 16, SQLAlchemy 2.0 declarative models (`app/database/models.py`), Alembic migrations (`alembic/`), and a real engine/session layer (`app/database/database.py`) all exist. `users` (Sprint 003, tenant-aware since Sprint 009), `customers` (Sprint 004), `projects` (Sprint 006), `quotes` (Sprint 007), and `tenants` (Sprint 008) have real HTTP API surfaces; `materials` (Sprint 005) is real and seeded but **internal-only** — read by `/api/v1/quote`, `/api/v1/estimate`, `/api/v1/process`, not exposed as its own route (a confirmed scope decision, not an oversight).

---

## 1. What actually holds data today

### 1.1 Hardcoded catalogue (`app/data/`) — superseded by Sprint 005, `services.py` still live

- `materials.py`, `pricing.py` — the original 3-entry hardcoded dicts. **Superseded as of Sprint 005** by the database-backed catalogue (`app/materials/`, §1.4) — no longer imported anywhere, left in place per ADR-008 (archive, don't delete without approval) rather than deleted.
- `services.py` — `SERVICES: list[str]`, 4 static service names. Still live — a genuinely static company service list, not per-material data, so it wasn't part of the Sprint 005 move.

### 1.4 Material catalogue (`app/materials/`) — database-backed since Sprint 005

`MaterialService` (`app/materials/service.py`) reads the `materials` table directly (no repository interface — that pattern is for the pre-database era, per ADR-001/ADR-019; `app/materials/` follows `app/customers/`'s precedent). Seeded on startup (`app/materials/seed.py`, guarded like every other seed) with ~30 rows: 15 named materials across the 5 roadmap categories (quartz, granite, marble, porcelain, Dekton), each in 20mm and 30mm (the 30mm price is the 20mm price × a documented markup constant, not hand-picked per row). **This is an illustrative reference catalogue, not sourced from a live supplier feed** — no such data source exists in this project; see `docs/SPRINTS/sprint-005.md` for the full caveat. Consumed internally by `quotes/calculator.py`, `assistant/sales.py`, `assistant/search.py` — no `/api/v1/materials` route exists (confirmed scope decision).

### 1.2 PostgreSQL-backed repositories (`app/activity/`, `app/notifications/`) — Postgres since Sprint 002

Both are built behind a repository interface (`ActivityRepository`, `NotificationRepository` — `ABC` classes), introduced in Sprint 001 specifically so this swap wouldn't require touching the service or router layer. As of Sprint 002, `PostgresActivityRepository`/`PostgresNotificationRepository` are the default implementation — data survives a server restart, and `InMemory*Repository` still exists in the same files but is no longer constructed by default (available for tests or a future in-memory mode).

- **`ActivityEvent`** (pydantic, `app/activity/models.py`) ↔ **`activity_log`** (SQLAlchemy, `app/database/models.py`): `id`, `type`, `title`, `description`, `timestamp` — direct 1:1 mapping, `str(uuid.UUID) ↔ uuid.UUID` for the id.
- **`Notification`** (pydantic, `app/notifications/models.py`) ↔ **`notifications`** table, modelled as `NotificationRecord` in SQLAlchemy (named differently to avoid a class name collision with the pydantic model) — same direct mapping.

### 1.3 Quote persistence (`app/quotes/`) — database-backed since Sprint 007

Previously: `QuoteRequest` was calculated against and returned in the response, never saved — every quote was gone the moment the response was sent. **As of Sprint 007**, `QuoteService.create()` (`app/quotes/service.py`) wraps the existing pure `QuoteCalculator` and persists every result via `crud.create_quote(...)`, for both `POST /api/v1/quote` and `POST /api/v1/estimate` (one seam, not two copies). It also logs a real `ActivityEvent` server-side, same pattern as customers/projects.

**Important asymmetry, by schema design, not a bug:** `QuoteRequest.customer` (free-text name) is required and still works standalone — `/estimate`'s regex path has no way to resolve a real customer — but the `quotes` table has **no text name column**, only `customer_id` (FK). An unlinked quote's customer name exists only in the calculated HTTP response, never in the database row. Linking a real customer (`customer_id`, optional) is the only way a quote's customer is retrievable later, e.g. from `GET /api/v1/quotes/{id}` or its downloadable invoice.

### 1.5 Job pipeline (`app/projects/`) — database-backed since Sprint 006

`ProjectService` (`app/projects/service.py`) — same route-level pattern as `app/customers/`/`app/materials/` (ADR-019). The `projects` table gained a `status` column this sprint (migration `786f58ce4406`, safe as `NOT NULL` — the table had 0 rows). `ProjectStatus` (`app/projects/models.py`) is a 7-stage pipeline — `enquiry`, `quoted`, `booked`, `templated`, `fabricated`, `installed`, `complete` — stored as a plain `String`, same convention as `ActivityType`/`NotificationType`. `PATCH /api/v1/projects/{id}/status` is the first update endpoint in the API beyond create — a deliberate, narrow exception to the Customers precedent (list/detail/create only): a job pipeline is meaningless without a way to move a project between stages. See ADR-022.

### 1.6 Tenants (`app/tenants/`) — database-backed since Sprint 008, the 8th table

`TenantService` (`app/tenants/service.py`) — same route-level pattern as `app/customers/` (ADR-019), `Depends(get_current_user)`-gated with the existing single-tenant auth (not tenant-scoped auth — that's Sprint 009). `slug` is unique and auto-generated from `name` if not supplied (`TenantService._slugify`), with a random-suffix retry on collision. `status` defaults to `"active"` and is currently inert — nothing reads it yet (no trial/billing concept exists before Sprint 018). Creating a tenant logs a `tenant_created` `ActivityEvent`, matching every other module's `create()`. See `docs/DECISIONS.md` ADR-025 for the full reasoning, and `docs/SPRINTS/sprint-008.md` for the sprint record.

**This is the table the other 7 tables' `tenant_id` columns now genuinely point at** (see §2's Multi-tenancy note below) — but nothing yet assigns a real tenant to any row, and no query filters by one. That's Sprint 012.

---

## 2. Schema (Sprint 002)

Every table below exists in PostgreSQL as of Sprint 002's migration (`alembic/versions/a22b1189f8e7_*.py`). **Columns are a starting point drawn from the existing pydantic models and the roadmap's informal shapes, not a finalised design** — foreign keys are present where an obvious relationship exists (`quotes.customer_id`, `projects.customer_id` → `customers.id`), but indexes, constraints, and any columns a future sprint's UI actually needs are that sprint's work, not Sprint 002's.

| Table | Columns | API surface today |
|---|---|---|
| `customers` | `id` (UUID, PK), `tenant_id` (UUID, nullable), `name`, `email`, `phone`, `created_at` | **Live** — `GET/POST /api/v1/customers`, `GET /api/v1/customers/{id}` (Sprint 004, auth-required) |
| `quotes` | `id`, `tenant_id`, `customer_id` (FK → `customers.id`), `material`, `thickness`, `kitchen_length`, `island`, `waterfall`, `splashback`, `upstands`, `postcode`, `price_per_slab`, `price_before_vat`, `vat`, `total`, `created_at` | **Live** — `POST /api/v1/quote`/`/estimate` persist (public); `GET /api/v1/quotes`, `GET /api/v1/quotes/{id}`, `GET /api/v1/quotes/{id}/invoice` (Sprint 007, auth-required) |
| `projects` | `id`, `tenant_id`, `customer_id` (FK → `customers.id`), `name`, `notes`, `status` (Sprint 006), `created_at` | **Live** — `GET/POST /api/v1/projects`, `GET /api/v1/projects/{id}`, `PATCH /api/v1/projects/{id}/status` (Sprint 006, auth-required) |
| `materials` | `id`, `tenant_id`, `name`, `category`, `thickness`, `slab_size`, `finish`, `price`, `created_at` | **Live internally** — seeded, read by `/api/v1/quote`/`/estimate`/`/process` (Sprint 005); no dedicated route |
| `users` | `id`, `tenant_id` (**NOT NULL** since Sprint 009), `name`, `email` (unique), `role`, `password_hash`, `created_at` | `POST /api/v1/auth/signup`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me` (Sprint 003, tenant-aware since Sprint 009) |
| `activity_log` | `id`, `tenant_id`, `type`, `title`, `description`, `timestamp` | **Live** — `GET/POST /activity` |
| `notifications` | `id`, `tenant_id`, `title`, `message`, `type`, `read`, `timestamp` | **Live** — `GET/POST /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{notification_id}/read` |
| `tenants` | `id`, `name`, `slug` (unique), `status`, `created_at` | **Live** — `GET/POST /api/v1/tenants`, `GET /api/v1/tenants/{id}` (Sprint 008, auth-required) |

**Multi-tenancy:** every one of the original 7 tables carries a `tenant_id` (UUID) column, per ADR-013 — added in Sprint 002, at zero enforcement cost, because retrofitting it onto tables with real data later would be far more expensive. **As of Sprint 008, a real `tenants` table exists and `tenant_id` on all 7 tables is a genuine `ForeignKey("tenants.id")`** (previously a bare UUID with nothing to point at) — see ADR-025. **As of Sprint 009, `users.tenant_id` is the first of the 7 to become `NOT NULL`** — every user genuinely belongs to exactly one tenant (see ADR-026) — while `customers`, `quotes`, `projects`, `materials`, `activity_log`, and `notifications` stay nullable. **As of Sprint 012 (ADR-029), every business-data query on `customers`, `projects`, `quotes`, `activity_log`, and `notifications` is filtered by the caller's `tenant_id`** — `customers.tenant_id`, `quotes.tenant_id`, `projects.tenant_id`, `activity_log.tenant_id`, and `notifications.tenant_id` each gained a plain index for it (migration `a8d91098a01e`). Columns stay nullable throughout — an anonymous `/quote`/`/estimate` call or a startup seed row still has `tenant_id = NULL`, invisible to every tenant's authenticated browsing routes. `materials` remains the sole deliberate exception: a shared reference catalogue, not tenant-owned data, so it stays unfiltered by design.

### Sprint 036 — universal quoting, construction records, automations and tasks

| Table | Change | Migration |
| --- | --- | --- |
| `quotes` | `+ quote_kind` ('stone'\|'general', NOT NULL default 'stone'), `title`, `trade`, `site_address_line1/2`, `site_city`, `site_postcode`, `scope_of_works`, `notes`, `exclusions`, `terms`, `valid_until`, `currency` (NOT NULL default 'GBP'), `vat_rate` (NOT NULL default 0.2), `subtotal`, `discount_amount`, `sent_at`. **NOT NULL dropped** on `material`, `thickness`, `kitchen_length`, `length_mm`. | `b3c4d5e6f7a8` |
| `quote_items` | `+ line_kind` ('stone'\|'labour'\|'material'\|'other', NOT NULL default 'stone'), `description`, `unit`, `unit_price`. **NOT NULL dropped** on `material`, `thickness`, `length_mm`, `width_mm`. `quantity` widened INTEGER → DOUBLE PRECISION. | `b3c4d5e6f7a8` |
| `customers` | `+ customer_type` (NOT NULL default 'individual'), `company_name`, `address_line1/2`, `city`, `postcode`, `notes` | `f1a2b3c4d5e6` |
| `projects` | `+ project_type`, `description`, `site_address_line1/2`, `site_city`, `site_postcode`, `start_date` (DATE), `target_completion_date` (DATE), `estimated_value` | `a2b3c4d5e6f7` |
| `tasks` | **New.** `id`, `tenant_id` (NOT NULL, indexed), `assigned_user_id`, `created_by_user_id`, `title`, `body`, `status`, `due_at` (indexed), `source_type`/`source_id` (polymorphic, same convention as `notifications`), `dedupe_key` (UNIQUE), `completed_at`, `created_at` | `c4d5e6f7a8b9` |
| `automations` | **New.** `id`, `tenant_id` (NOT NULL, indexed), `created_by_user_id`, `name`, `description`, `template_key`, `trigger_type` (indexed), `conditions` (JSONB), `actions` (JSONB), `enabled`, `created_at`, `updated_at` | `c4d5e6f7a8b9` |
| `automation_runs` | **New.** `id`, `tenant_id` (NOT NULL, indexed), `automation_id` (FK, indexed), `trigger_type`, `subject_type`/`subject_id`, `status`, `detail`, `dedupe_key` (UNIQUE), `created_at` | `c4d5e6f7a8b9` |
| `tenants` | `+ currency` (NOT NULL default 'GBP'), `trades` (comma-separated keys), `onboarding_completed_at`, `logo_storage_filename` | `d5e6f7a8b9c0` |

**Every change is additive or NOT-NULL-dropping.** No row is deleted or rewritten by any Sprint 036 migration, and the full pre-sprint test suite passed unchanged against the new schema. Dropping NOT NULL is a pure widening — existing rows keep every value, no existing query can start failing, and Postgres performs it as a catalogue-only change. See ADR-039 for why sentinels were rejected in favour of nullable columns, and why the universal-quoting downgrade deliberately refuses once a general quote exists.

`automations.conditions`/`actions` are the first JSON columns in this schema. The normalised alternative was rejected because both are always read and written whole, as a complete rule, and are never queried into or joined against; their shape is validated at the Pydantic boundary on every write. JSONB rather than JSON so a future "which automations use action X" query is possible without a migration.

`tasks.dedupe_key` and `automation_runs.dedupe_key` are both UNIQUE, so automation idempotency is enforced by the database rather than only attempted in code — the same defence-in-depth Sprint 024 established for `notifications.dedupe_key`.

---

## 3. What Sprint 002 deliberately did not build (now fully closed out, Sprint 007)

Explicit decision (see `docs/DECISIONS.md` and `docs/SPRINTS/sprint-002.md`): no new CRUD API endpoints for any of the 5 new tables at the time. The API surface reading/writing them arrived with each table's own sprint: `customers` → Sprint 004 ✅, `materials` → Sprint 005 ✅ internal-only, `projects` → Sprint 006 ✅, `quotes` → Sprint 007 ✅, `users` → Sprint 003's auth work ✅. All 5 are now real, plus the 8th table, `tenants`, added and given its own API surface in Sprint 008 ✅. `app/database/crud.py` has helpers for every table: `activity_log`/`notifications` (Sprint 002), `users` (Sprint 003), `customers` (Sprint 004), `materials` (Sprint 005), `projects` including its status-update (Sprint 006), `quotes` including the two aggregate helpers backing `/api/v1/dashboard` (Sprint 007), and `tenants` (Sprint 008).

## 4. Local development setup

`docker-compose.yml` (repo root) runs a single `postgres:16-alpine` service. Copy `.env.example` to `.env`, run `docker compose up -d`, then `alembic upgrade head`. See `docs/SYSTEM_ARCHITECTURE.md` §2.3 for details. `DATABASE_URL` is read from `.env` by `app/database/database.py` (and by `alembic/env.py`, which imports the same value — one source of truth for the connection string).
