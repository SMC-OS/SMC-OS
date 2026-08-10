# SIMO OS — Architecture Decisions

Lightweight ADR log. Each entry: what was decided, why, and its current status. Add a new entry rather than editing history when a decision changes — note the supersession instead.

**Status categories:**
- **IMPLEMENTED** — the decision is implemented in the current codebase.
- **DECIDED-NOT-IMPLEMENTED** — a decision has been made but the implementation does not exist yet.
- **PLANNED** — explicitly planned future work/architecture that has not yet been implemented (the *what* and *when* are scheduled; the specific technical approach may still be open).
- **UNDECIDED** — no final decision has been made yet.

---

## ADR-001: Repository pattern for anything needing storage before the database exists
**Status:** IMPLEMENTED (`app/activity/repository.py`, `app/notifications/repository.py`)

Both Sprint 001 modules that need to hold data (Recent Activity, Notifications) are built as `Repository (ABC) → Service → Router`, with an `InMemory*Repository` as the only implementation today. **Why:** Sprint 002 needs to swap in PostgreSQL without rewriting the service layer, the router, or any frontend code. Any future module that needs storage before Sprint 002 lands should follow the same shape.

## ADR-002: Backend changes are additive-only until Sprint 003's restructuring
**Status:** IMPLEMENTED (Sprint 001)

New capability is added as a new module with its own `router.py`, mounted in `main.py` via `app.include_router(...)`. Existing route bodies in `main.py` are not edited unless the task is specifically about that route. **Why:** the brief for Sprint 001 required every existing endpoint to keep working exactly as before, and this was the simplest way to guarantee it — verified by smoke-testing every original route after each change.

## ADR-003: Single frontend API client
**Status:** IMPLEMENTED (`apps/web/lib/api.ts`)

No component calls `fetch()` directly — every backend call goes through `lib/api.ts`. **Why:** makes the future move to `/api/v1`, auth headers, or a WebSocket layer a one-file change instead of a search-and-replace across every component.

## ADR-004: Polling now, swappable for real-time later
**Status:** IMPLEMENTED (`apps/web/hooks/usePolling.ts`)

Every live panel (dashboard stats, activity, notifications) polls every 5 seconds through one shared hook, rather than each panel implementing its own interval. **Why:** the brief asked for the dashboard to be "prepared for WebSockets later" without implementing them yet — routing all live data through one primitive means a future real-time layer replaces one function, not every consuming component.

## ADR-005: Class-based dark mode via Tailwind v4 custom variant
**Status:** IMPLEMENTED (`apps/web/app/globals.css`, `components/theme/ThemeProvider.tsx`)

Tailwind v4 removed the `darkMode: "class"` config option; class-based toggling is instead enabled with `@custom-variant dark (&:where(.dark, .dark *));` in CSS. Theme is persisted to `localStorage` and applied via an inline `<script>` in `layout.tsx` before hydration to avoid a flash of the wrong theme. **Why:** the brief required dark mode support with a manual toggle, not just OS-preference following.

## ADR-006: Honest UI over fake functionality for unbuilt modules
**Status:** IMPLEMENTED (Sprint 001 — Customers, Projects, Settings)

Where a feature isn't built yet, the UI says so explicitly (a "Coming in Sprint N" badge) rather than a dead button or a form that silently fails. Where a form can't persist a real record yet, it still does something real — logs a genuine `ActivityEvent` — instead of pretending to save. **Why:** direct instruction from the person building this ("Do NOT use dead buttons or fake placeholders"), and it keeps the app demonstrably truthful about its own state.

## ADR-007: No new frontend dependencies without a concrete need
**Status:** IMPLEMENTED (Sprint 001)

The icon set (`components/ui/icons.tsx`), the `cn()` classname helper (`lib/utils.ts`), and dropdown/click-outside handling (`hooks/useClickOutside.ts`) are hand-rolled rather than pulling in `lucide-react`, `clsx`, or a headless UI library. **Why:** the app doesn't need them yet at this scale; revisit if/when the component surface grows enough to justify the dependency weight. Not a permanent ban — a reasoned trade-off for the current size of the app.

## ADR-008: Archive, don't delete, obsolete files
**Status:** IMPLEMENTED (`apps/web/_legacy/`)

Files identified as dead or duplicate are moved to `_legacy/` with a documented reason in `_legacy/README.md`, not `git rm`'d or deleted from disk. **Why:** explicit standing instruction — nothing gets permanently removed without separate approval.

## ADR-009: `BrainRouter` is a temporary keyword dictionary, not real AI
**Status:** IMPLEMENTED as a known placeholder, not a final design

`app/brain/router.py` maps literal keywords ("price", "quartz", "instagram"...) to an agent name via a Python `dict`. This is explicitly acknowledged as a stand-in, not a design decision to keep. Its eventual replacement is tracked separately as ADR-017 (PLANNED).

## ADR-010: ORM and migrations — SQLAlchemy 2.0 + Alembic
**Status:** IMPLEMENTED (`app/database/database.py`, `app/database/models.py`, `alembic/`)

Recommended pairing for FastAPI + PostgreSQL. Standard, well-supported, no exotic alternative considered necessary at this scale.

## ADR-011: Auth strategy — JWT bearer tokens, not server-side sessions
**Status:** DECIDED-NOT-IMPLEMENTED (Sprint 003)

Stateless tokens were chosen over sessions so a future mobile app or client portal doesn't need a rework to authenticate. No token issuance, validation, or user model exists yet.

## ADR-012: API versioning — `/api/v1` prefix
**Status:** DECIDED-NOT-IMPLEMENTED (Sprint 003)

Every route today is unprefixed (see `docs/API_SPEC.md`). Adding the prefix now, before any real client depends on the unversioned paths, was judged cheaper than retrofitting it later.

## ADR-013: Multi-tenancy model — row-level `tenant_id`, not separate schemas
**Status:** IMPLEMENTED for the column (all 7 tables, Sprint 002); DECIDED-NOT-IMPLEMENTED for enforcement (Sprint 012)

Simpler to operate at this scale than per-tenant schemas. Adding the column early (Sprint 002) even though it isn't enforced until Sprint 012 was judged cheap insurance against an expensive later migration. The column is a plain nullable UUID, not a foreign key — no `tenants` table exists yet, and nothing reads or filters by it today.

## ADR-014: Frontend data fetching — hand-rolled polling now, TanStack Query later
**Status:** DECIDED-NOT-IMPLEMENTED (TanStack Query adoption planned for Sprint 004)

`usePolling` (ADR-004) is deliberately minimal. TanStack Query is the planned upgrade once more than one screen needs caching/deduping of live data — not adopted in Sprint 001 to avoid a dependency the app didn't need yet.

## ADR-015: AI provider — OpenAI SDK for router/estimator/assistants
**Status:** DECIDED-NOT-IMPLEMENTED (Sprint 006 onward)

`openai` is already in `requirements.txt` but is not imported anywhere in `app/` yet. ElevenLabs (also installed, also unused) is reserved for a future voice module, not prioritised before v1.0.

## ADR-016: Hosting / infrastructure
**Status:** UNDECIDED

Candidates noted (Render/Railway/Fly.io for backend + managed Postgres, Vercel for the Next.js frontend) but no hosting provider has been selected. This blocks nothing in Sprint 002's local development work, but needs resolving before any deployment. Not to be conflated with PLANNED — there is no committed choice here yet, only options under consideration.

## ADR-017: Real AI-based intent router, replacing `BrainRouter`'s keyword dictionary
**Status:** PLANNED (Sprint 008, per `docs/ROADMAP.md`)

The *what* and *when* are scheduled — `BrainRouter` (ADR-009) is explicitly not the long-term design, and Sprint 008 is where it gets replaced. The *how* is not yet decided: whether that's LLM-based classification, embeddings-based similarity, or another approach, and which provider, has not been chosen. Distinct from DECIDED-NOT-IMPLEMENTED entries above, where the specific technical approach is already settled.

## ADR-018: Local PostgreSQL via a single-service Docker Compose file
**Status:** IMPLEMENTED (`docker-compose.yml`)

One `postgres:16-alpine` service, no other infrastructure (no pgAdmin, no app container, no production deployment config). Credentials come from the root `.env` (gitignored; `.env.example` is the tracked template) via `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/`POSTGRES_PORT`, with sensible defaults if unset. **Why:** gives every developer a reproducible local database with one command (`docker compose up -d`) without deciding anything about production hosting — ADR-016 (hosting) remains UNDECIDED and this doesn't presuppose an answer to it.

## ADR-019: Postgres-backed repositories open a session per call, not via FastAPI dependency injection
**Status:** IMPLEMENTED (`app/activity/repository.py`, `app/notifications/repository.py`)

`PostgresActivityRepository`/`PostgresNotificationRepository` call `SessionLocal()` directly inside each method (`with SessionLocal() as db:`) rather than receiving a session through FastAPI's `Depends(get_db)`. **Why:** `activity_service`/`notification_service` are module-level singletons constructed once at import time (ADR-001 predates the database and this hasn't changed), not per-request objects — there is no request-scoped session available to inject into them. `app/database/database.py`'s `get_db()` dependency exists for future route-level code (Sprint 004+, once `customers`/`quotes`/`projects` get real endpoints) that isn't built around a singleton and can take a request-scoped session normally.
