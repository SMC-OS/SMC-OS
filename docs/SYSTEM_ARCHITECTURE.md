# SIMO OS — System Architecture

**Status:** Canonical reference, current as of Sprint 018 implementation (18 August 2026)
**Stack:** FastAPI (Python) · Next.js 16 / React 19 (TypeScript) · Tailwind CSS v4 · PostgreSQL 16 via SQLAlchemy 2.0 + Alembic · `/api/v1` + JWT auth · tenant-isolated SaaS data · client portal tracking/documents/messaging · explicit development/test/production runtime policy · structured request logging · provider-neutral non-root backend container · Turborepo/pnpm workspace

This document describes the system as it actually exists today — not the aspirational end state. Anything not yet built is explicitly marked as such, with the sprint that delivers it. Treat this as the source of truth for architecture decisions; update it at the end of every sprint.

---

## 1. Overview

SIMO OS is a monorepo with two independently-runnable halves:

- **Backend** (`SMC-OS/app/`) — a FastAPI application. Every product route lives under `/api/v1`; `GET /`, dependency-free `GET /health`, and database-aware `GET /ready` are unversioned. Sprint 018 uses an import-safe application factory and FastAPI lifespan: logging is configured first, the upload mount is validated, and development/test seeders run only when enabled. Production settings are fail-closed, seed nothing, require an existing writable persistent upload path, and never run Alembic during application startup. `python -m app.core.runtime_check` is the read-only release preflight.
- **Frontend** (`SMC-OS/apps/web/`) — a Next.js App Router application, the sole consumer of the backend API, styled with Tailwind v4 and a hand-built component system (no UI library).

They communicate over HTTP only. The frontend never imports backend code or vice versa. `NEXT_PUBLIC_API_URL` remains the single point of configuration for the backend origin. Development/test retain the `http://127.0.0.1:8000` fallback; an explicit `APP_ENV=production` build requires a non-loopback absolute HTTPS origin and fails during configuration evaluation if it is missing or unsafe.

A third directory, `SMC-OS-Docs/`, is a separate, disconnected Turborepo used for planning documents (`VISION.md`, `BLUEPRINT.md`) and is not part of the running system.

---

## 2. Repository & Folder Structure

### 2.1 Backend — `SMC-OS/app/`

```
app/
├── main.py                  # Import-safe FastAPI factory, lifespan, configured CORS/middleware, router mounts
├── core/                    # ✅ Sprint 018 runtime contract (ADR-034)
│   ├── config.py              # APP_ENV policy, production validation, CORS/readiness/upload settings
│   ├── runtime_check.py        # Read-only sanitized production preflight command
│   ├── startup.py              # Upload-mount validation + policy-gated seeders; never Alembic
│   ├── health.py               # Dependency-free /health + bounded PostgreSQL /ready
│   ├── middleware.py           # X-Request-ID propagation and safe request-completion logs
│   ├── logging.py              # JSON production/readable development formatting
│   └── errors.py               # Safe error bodies + correlated unhandled-exception logging
│
├── api/v1/                  # ✅ Sprint 003 — /api/v1 route restructuring (ADR-012)
│   ├── __init__.py          #    api_router: assembles core + auth sub-routers under /api/v1
│   └── core.py               #    /process, /quote, /estimate, /quote/pdf, /dashboard (moved from main.py, bodies unchanged)
│
├── auth/                     # ✅ Sprint 003 — JWT login/me machinery (ADR-011); tenant-aware since Sprint 009 (ADR-026); role machinery since Sprint 010 (ADR-027), first enforced Sprint 011 (ADR-028)
│   ├── models.py               #    LoginRequest, SignupRequest (Sprint 009), TokenResponse, UserOut (+tenant_id/tenant_name, Sprint 009), UserRole enum (Sprint 010)
│   ├── security.py              #    bcrypt hashing, JWT encode/decode (pyjwt) — payload gains tenant_id (Sprint 009)
│   ├── service.py                #    AuthService — authenticate(), create_user(), signup() (Sprint 009), build_user_out(); create_user() reused by app.invitations (Sprint 011)
│   ├── router.py                  #    APIRouter: POST /auth/signup (Sprint 009), POST /auth/login, GET /auth/me
│   ├── dependencies.py             #    get_current_user — requires tenant_id claim since Sprint 009; used by customers/projects/quotes/tenants. require_role() (Sprint 010) — attached to app.invitations since Sprint 011 (ADR-028), its first real route
│   └── seed.py                      #    Seeds one owner account (+ its Default Workspace tenant, Sprint 009) via AuthService.signup() if `users` is empty
│
├── customers/                # ✅ Sprint 004 — first real business-data module, auth-enforced (ADR-021)
│   ├── models.py                #    CustomerCreate, CustomerOut
│   ├── service.py                 #    CustomerService — list_all/get/create; create() also logs an ActivityEvent
│   └── router.py                   #    APIRouter: GET/POST /customers, GET /customers/{id} — all Depends(get_current_user)
│
├── projects/                  # ✅ Sprint 006 — job pipeline, second auth-enforced module (ADR-022)
│   ├── models.py                  #    ProjectStatus (7-stage enum), ProjectCreate, ProjectOut, ProjectStatusUpdate
│   ├── service.py                   #    ProjectService — list_all/get/create/update_status; create() logs an ActivityEvent
│   └── router.py                     #    APIRouter: GET/POST /projects, GET /projects/{id}, PATCH /projects/{id}/status
│
├── activity/                # ✅ Sprint 001 shell, ✅ Postgres-backed since Sprint 002
│   ├── models.py            #    ActivityEvent, ActivityEventCreate, ActivityType enum
│   ├── repository.py        #    ActivityRepository (ABC) + InMemory + PostgresActivityRepository (default)
│   ├── service.py           #    ActivityService — business logic, holds the singleton
│   ├── router.py            #    APIRouter: GET/POST /activity
│   └── seed.py               #    Sample data for a fresh install — guarded, only seeds an empty table
│
├── notifications/            # ✅ Sprint 001 shell, ✅ Postgres-backed since Sprint 002
│   ├── models.py             #    Notification, NotificationCreate, NotificationType enum
│   ├── repository.py         #    NotificationRepository (ABC) + InMemory + PostgresNotificationRepository (default)
│   ├── service.py             #    NotificationService
│   ├── router.py              #    APIRouter: GET/POST /notifications, PATCH .../read
│   └── seed.py                 #    Sample data for a fresh install — guarded, only seeds an empty table
│
├── tenants/                    # ✅ Sprint 008 — tenants table + CRUD, schema/plumbing only (ADR-025)
│   ├── models.py                #    TenantCreate, TenantOut
│   ├── service.py                 #    TenantService — list_all/get/create; auto-slugifies, logs an ActivityEvent
│   └── router.py                   #    APIRouter: GET/POST /tenants, GET /tenants/{id} — Depends(get_current_user), NOT tenant-scoped auth
│
├── invitations/                # ✅ Sprint 011 — Staff invitations, first tenant with >1 user (ADR-028)
│   ├── models.py                 #    InvitationCreate, InvitationOut, InvitationCreateOut (+raw token), InvitationPublicOut, AcceptInvitationRequest
│   ├── service.py                  #    InvitationService — create/list/revoke/accept; opaque token hashed (sha256) before persisting; derive_status() computes "expired" at read time
│   └── router.py                    #    APIRouter: POST/GET /invitations, DELETE /invitations/{id} — Depends(require_role(OWNER)); GET/POST /invitations/token/{token}[/accept] — public
│
├── portal/                    # ✅ Sprint 013 — read-only client portal, no users row (ADR-030)
│   ├── models.py                #    PortalLinkCreate, PortalLinkOut, PortalLinkCreateOut (+raw token), PortalProjectOut, PortalQuoteOut, PortalPublicOut
│   ├── service.py                 #    PortalService — link/public-view/invoice/document access; Sprint 017 adds active-token message list/post, with inbound customer activity + tenant notification
│   └── router.py                   #    Authenticated link management plus public token view/invoice/documents; Sprint 017 adds public GET/POST .../messages, scoped only by the resolved active token
│
├── documents/                 # ✅ Sprint 016 — client portal document upload/download, local disk (ADR-032)
│   ├── models.py                #    DocumentOut (excludes storage_filename — never exposed to any client)
│   ├── service.py                 #    DocumentService — upload_document (20MB cap enforced against actual bytes, extension allowlist, generated uuid4() storage filename)/list_documents/get_document/file_path
│   └── router.py                   #    APIRouter: POST/GET /documents, GET /documents/{id}/download — Depends(get_current_user), any role, NOT Owner-only; no public routes here (those live on app/portal/router.py, see above)
│
├── messages/                  # ✅ Sprint 017 — customer-level portal messaging (ADR-033)
│   ├── models.py                 #    MessageCreate/MessageOut; 5,000-char plain-text policy, nullable sender_user_id
│   ├── service.py                #    MessageService — tenant/customer validation, staff create/list, chronological threads
│   └── router.py                 #    APIRouter: POST/GET /messages — authenticated, any tenant role; public token routes remain on app/portal/router.py
│
├── users/                     # ✅ Sprint 015 — team management: list team, deactivate a teammate (ADR-031)
│   ├── models.py                #    TeamMemberOut (named to avoid colliding with app.auth.models.UserOut)
│   ├── service.py                 #    UserManagementService — list_users/deactivate_user; soft-deactivate only (users.is_active), never a row delete; CannotDeactivateSelfError (409); UserNotFoundError (404) for unknown-or-cross-tenant, same error for both
│   └── router.py                   #    APIRouter: GET /users, POST /users/{id}/deactivate — Depends(require_role(OWNER)), second real attachment point after app.invitations; deactivation logs an ActivityEvent
│
├── quotes/                    # ✅ Sprint 007 — persisted, auth-enforced, third such module (ADR-023)
│   ├── models.py               #    QuoteRequest (+ optional customer_id, Sprint 007), QuoteOut
│   ├── calculator.py            #    QuoteCalculator — pure pricing + VAT logic; takes db, looks up (material, thickness)
│   ├── slab_calculator.py        #    Real area-based yield formula, documented constants (Sprint 005)
│   ├── service.py                 #    ✅ Sprint 007 — QuoteService: persists every calculate(), logs an ActivityEvent
│   ├── router.py                   #    ✅ Sprint 007 — GET /quotes, GET /quotes/{id}, GET /quotes/{id}/invoice
│   ├── pdf.py                       #    ✅ Sprint 007, rewritten — letterhead + VAT table, io.BytesIO, real download
│   ├── generator.py                  #    ⚠ Superseded by service.py (Sprint 007) — no longer imported, kept per ADR-008
│   └── validator.py                   #    ⬜ empty — no request validation yet
│
├── assistant/                        # ⚠ Partially implemented — keyword-based, not AI
│   ├── sales.py                       #    ✅ SalesAssistant — matches material keywords
│   ├── search.py                       #    ✅ SearchAssistant — scores material matches
│   ├── estimator.py                     #    ✅ EstimatorAssistant — regex-based text→quote
│   └── {construction, customer_service, #    ⬜ empty stubs — 9 files, no logic yet
│         executive, finance, marketing,
│         projects, purchasing, scheduling,
│         seo, social}.py
│
├── brain/                             # ⚠ Partially implemented — no real AI yet
│   ├── manager.py                      #    ✅ BrainManager — dispatches to Sales/Search only
│   ├── router.py                        #    ✅ BrainRouter — hardcoded keyword→agent dict
│   └── {context, memory, permissions,    #    ⬜ empty — planned for Sprint 008+
│         planner, reasoner, state}.py
│
├── materials/                            # ✅ Sprint 005 — database-backed catalogue, internal only
│   ├── service.py                         #    MaterialService — list_all, get_by_name_and_thickness
│   └── seed.py                             #    Seeds ~30 rows (5 categories x ~3 materials x 2 thicknesses) if empty
│
├── data/                                # ⚠ Superseded by app/materials/ (Sprint 005) — no longer imported
│   ├── materials.py, pricing.py           #    Left in place per ADR-008, not deleted
│   └── services.py                         #    Still live — static list of 4 service names, unrelated to materials
│
├── database/                             # ✅ Sprint 002 — persistence layer, ✅ Sprint 003 adds User CRUD
│   ├── database.py                        #    Engine, SessionLocal, declarative Base, get_db() dependency — reads app.core.config.settings
│   ├── models.py                           #    Customer, Quote, Project, Material, User (+ password_hash, Sprint 003), ActivityLog, NotificationRecord
│   └── crud.py                              #    CRUD helpers: app.activity/app.notifications (Sprint 002) + app.auth's user lookups (Sprint 003)
│
└── {apps/dashboard, customers,            # ⬜ Empty placeholder directories reserved
     dashboard, integrations, memory,       #    for future modules — do not assume
     projects, voice, wake}/                #    anything lives here yet
```

**Reading the symbols:** ✅ implemented and working · ⚠ implemented but limited/temporary · ⬜ empty placeholder, not built.

### 2.2 Frontend — `SMC-OS/apps/web/`

```
apps/web/
├── app/                          # Next.js App Router — one folder per route
│   ├── layout.tsx                 # Root layout: fonts, ThemeProvider, AuthProvider (Sprint 004), AppShell, anti-flash script
│   ├── page.tsx                    # "/" — Dashboard
│   ├── login/page.tsx               # "/login" — Sprint 004, real login form, redirects to /customers on success
│   ├── quotes/
│   │   ├── page.tsx                 # "/quotes" — index (recent quote_created activity + CTA)
│   │   └── new/page.tsx              # "/quotes/new" — functional quote calculator (POST /quote)
│   ├── customers/
│   │   ├── page.tsx                  # "/customers" — ✅ Sprint 004, real list from GET /api/v1/customers, auth-gated
│   │   ├── [id]/page.tsx               # "/customers/[id]" — ✅ Sprint 004, read-only detail view
│   │   └── new/page.tsx                 # "/customers/new" — ✅ Sprint 004, real persistence via POST /api/v1/customers
│   ├── projects/
│   │   ├── page.tsx                   # "/projects" — ✅ Sprint 006, real list, stage Badge per row, auth-gated
│   │   ├── [id]/page.tsx                # "/projects/[id]" — ✅ Sprint 006, detail + "Advance to <next stage>" control
│   │   └── new/page.tsx                  # "/projects/new" — ✅ Sprint 006, real persistence, customer <select>, POST /api/v1/projects
│   ├── ai-assistant/page.tsx            # "/ai-assistant" — talks to POST /process
│   └── settings/page.tsx                 # "/settings" — real content, not a placeholder (exact sprint undocumented, predates Sprint 013); Sprint 015 adds a "Team" card
│
├── components/
│   ├── ui/                        # Reusable primitives — no business logic
│   │   ├── Card.tsx, Button.tsx, Badge.tsx, Avatar.tsx, Field.tsx (Field/Input/Select/Checkbox)
│   │   └── icons.tsx                # Hand-authored SVG icon set (no icon library dependency)
│   ├── auth/AuthProvider.tsx       # ✅ Sprint 004 — token/session context, mirrors ThemeProvider's shape
│   ├── layout/                     # The application shell itself
│   │   ├── AppShell.tsx              # Top-level layout: Sidebar + Topbar + main content
│   │   ├── Sidebar.tsx                # Collapsible desktop sidebar + mobile drawer
│   │   ├── SidebarContext.tsx          # Collapse/mobile-open state, persisted to localStorage
│   │   └── Topbar.tsx                   # Search trigger, theme toggle, notifications, profile menu
│   ├── shell/                      # Shell-level features, one level above layout/
│   │   ├── CommandPalette.tsx        # Global search (Cmd/Ctrl+K)
│   │   ├── NotificationsPanel.tsx     # Bell dropdown, polls /notifications
│   │   ├── UserProfileMenu.tsx         # Avatar dropdown — Sign out is real since Sprint 004; Profile/Settings still disabled
│   │   ├── ComingSoon.tsx               # Shared "not built yet" state card
│   │   └── ModuleIndexPage.tsx           # Shared index-page pattern — only Quotes uses it now (Customers, Projects have real lists)
│   ├── dashboard/                  # Dashboard-specific components
│   │   ├── StatGrid.tsx / StatCard.tsx  # Animated stat cards, polls /dashboard
│   │   ├── RecentActivityPanel.tsx        # Polls /activity
│   │   ├── QuickActions.tsx                # Links to the three "new" pages
│   │   └── DashboardStatusBar.tsx           # Loading/error/offline banner
│   └── theme/ThemeProvider.tsx      # Dark mode context, localStorage-persisted
│
├── hooks/
│   ├── usePolling.ts               # Generic 5s-interval fetch hook (the polling primitive)
│   ├── useDashboardStats.ts / useActivity.ts / useNotifications.ts   # Thin wrappers over usePolling
│   ├── useOnlineStatus.ts           # navigator.onLine + online/offline events
│   ├── useCountUp.ts                 # Animated number transitions
│   └── useClickOutside.ts             # Dropdown dismissal
│
├── lib/
│   ├── api.ts                      # Single HTTP client — every backend call goes through this; attaches JWT since Sprint 004
│   ├── auth-storage.ts               # ✅ Sprint 004 — plain (non-React) localStorage token wrapper, used by lib/api.ts + AuthProvider
│   ├── navigation.ts                  # Single source of truth for sidebar + command palette nav
│   ├── activity.ts                     # Icon/colour mapping per ActivityType
│   ├── projects.ts                      # ✅ Sprint 006 — label/Badge-tone mapping per ProjectStatus
│   └── utils.ts                          # cn(), formatCurrencyGBP(), formatRelativeTime()
│
├── types/                          # Shared TypeScript types, mirroring backend pydantic models
│   ├── dashboard.ts, activity.ts, notification.ts, quote.ts
│   ├── auth.ts, customer.ts          # ✅ Sprint 004
│   └── project.ts                     # ✅ Sprint 006
│
├── _legacy/                        # Archived, not deleted — see _legacy/README.md
│
└── {hooks, lib, services, styles,   # `services/`, `styles/`, `utils/` exist but are still
     types, utils}/                    empty — reserved, nothing to document yet
```

### 2.3 Local development database (Sprint 002)

- `SMC-OS/docker-compose.yml` — single `postgres:16-alpine` service, dev-only, no other infrastructure. Reads `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/`POSTGRES_PORT` from the root `.env` (falls back to `simo`/`simo`/`simo_os`/`5432` if unset).
- `SMC-OS/.env.example` — template for the backend `.env` (gitignored): the same `POSTGRES_*` values plus `DATABASE_URL`, the SQLAlchemy connection string `app/database/database.py` actually reads.
- `SMC-OS/alembic/`, `SMC-OS/alembic.ini` — migration tooling. `alembic/env.py` imports `app.core.config.settings` (Sprint 003 — previously a constant in `database.py`) and `app.database.models` directly, so migrations always target the same database the app does and `--autogenerate` sees every model.
- Run `docker compose up -d` then `alembic upgrade head` to stand up a fresh local database.

### 2.4 Production runtime boundary (Sprint 018)

- `Dockerfile` and `.dockerignore` define a provider-neutral Python 3.12 slim backend image. Its dedicated application user is non-root and its default command starts only Uvicorn on port 8000.
- The same immutable image is used for the one-off `alembic upgrade head` release job. Migration success and sole-head state are verified before application containers start; no entrypoint or lifespan hook runs Alembic.
- Production `UPLOAD_DIR` is an absolute, pre-mounted persistent path. A missing or unwritable mount fails startup. The supported topology is one backend instance, or multiple instances sharing the same supported filesystem; independent instance-local disks are not safe for documents.
- Container liveness calls `/health`. Deployment readiness and traffic promotion call `/ready` separately after migration verification. See `docs/PRODUCTION_RUNBOOK.md` for release, rollback, health, backup/restore, and persistence smoke procedures.

### 2.5 Other repo contents (not part of the running app)

- `SMC-OS/packages/ui/` — Turborepo starter boilerplate (Button/Card/Code), not imported by `apps/web`. Leave as-is until a decision is made to either adopt or remove it (flagged in the original architecture report as a duplicate "shared UI" system).
- `SMC-OS/apps/web/app/smc-home-backup.tsx` and `SMC-OS/smc-home-backup.tsx` — leftover backup files, not routes (Next.js only picks up `page.tsx`). Harmless but should eventually be removed or archived.
- `SMC-OS-Docs/` — planning-only repo, no runtime relationship to `SMC-OS`.

---

## 3. Backend Modules

| Module | Responsibility | State |
|---|---|---|
| `app.main` | Import-safe FastAPI factory, lifespan assembly, configurable CORS, request context, exception handlers, health and product router mounting | ✅ Sprint 018 runtime hardening |
| `app.api.v1` | Assembles every `/api/v1` route (ADR-012) | ✅ Sprint 003 |
| `app.auth` | JWT signup/login/`/me` — issuance + validation, enforced on `app.customers`/`app.projects`/`app.quotes`/`app.tenants`. Tenant-aware since Sprint 009 (ADR-026): every user belongs to a tenant, JWT carries `tenant_id`, old-shape tokens rejected. `role` is a real `UserRole` enum since Sprint 010 (ADR-027); `require_role()` is attached to `app.invitations` since Sprint 011 (ADR-028), its first real route | ✅ Sprint 003, tenant-aware Sprint 009, role machinery Sprint 010, first enforced Sprint 011 |
| `app.customers` | Real customer list/detail/create — first business-data module, first auth-enforced module | ✅ Sprint 004 |
| `app.projects` | Real project list/detail/create + status pipeline — second auth-enforced module, first update endpoint beyond create | ✅ Sprint 006 |
| `app.activity` | Recent Activity feed — log and list timestamped events | ✅ Postgres-backed (Sprint 002) |
| `app.notifications` | Notification centre — create, list, mark read | ✅ Postgres-backed (Sprint 002) |
| `app.quotes` | Quote pricing engine + persistence + downloadable invoices — third auth-enforced module (GET/browsing routes only; POST /quote and /estimate stay public); also hosts AI Quotation Generator v1 (`ai_draft.py`) | ✅ Sprint 007 (+ AI draft, `d306c99`) |
| `app.materials` | Database-backed material catalogue (list, lookup by name+thickness) | ✅ Sprint 005 — internal only, no route |
| `app.tenants` | `tenants` table CRUD (list/get/create) — schema/plumbing only, not yet tied to auth or data isolation | ✅ Sprint 008 |
| `app.invitations` | Staff invitations — create/list/revoke (Owner-only, `require_role`) + public token-view/accept. First module letting a tenant have >1 user; reuses `app.auth.service.auth_service.create_user()` | ✅ Sprint 011 |
| `app.portal` | Client portal — reusable per-customer link plus public tracking, invoice/document access, and two-way message list/post. No customer `users` row or login; every content route resolves tenant/customer from the active token (ADR-029/030/033) | ✅ Sprint 013 (+ documents Sprint 016, messaging Sprint 017) |
| `app.documents` | Client portal document upload/download — staff upload a file against a customer (any tenant user, not Owner-only); local-disk storage, generated filename, explicit extension allowlist, 20MB cap; public download routes live on `app.portal`, not here (ADR-032) | ✅ Sprint 016 |
| `app.messages` | Customer-level plain-text message thread — authenticated staff create/list routes plus public active-token create/list routes on `app.portal`; 5-second frontend polling, inbound customer activity + notification (ADR-033) | ✅ Sprint 017 |
| `app.users` | Team management — list a tenant's users, deactivate a Staff member's access (Owner-only, `require_role`). Soft-deactivation only, no row delete; deactivation also ends that user's already-issued token on its next request (`get_current_user`) | ✅ Sprint 015 |
| `app.data` | `services.py` (still live); `materials.py`/`pricing.py` superseded by `app.materials` | ⚠ mixed — see §2.1 |
| `app.assistant` | Per-domain "AI" agents | ⚠ 3 of 12 implemented, keyword-based |
| `app.brain` | Routes free text to an assistant | ⚠ hardcoded keyword dict, not AI |
| `app.core` | Explicit runtime settings and sanitized preflight; upload/seed lifespan; liveness/readiness; request-ID middleware; structured logging; safe exception handlers | ✅ Sprint 018 (ADR-034) |
| `app.database` | ORM models (9 tables), DB session, CRUD helpers | ✅ Sprint 002, extended Sprint 003 — see §3.1 |

### 3.1 The repository pattern (important — read before touching activity/notifications)

Both `app.activity` and `app.notifications` are built as **repository → service → router**, specifically so the in-memory storage could be swapped for PostgreSQL without changing the service, router, or any frontend code. That swap happened in Sprint 002:

```
ActivityRepository (ABC)              NotificationRepository (ABC)
   ├── InMemoryActivityRepository        ├── InMemoryNotificationRepository
   │     (Sprint 001, still present,     │     (Sprint 001, still present,
   │      unused by default)             │      unused by default)
   └── PostgresActivityRepository        └── PostgresNotificationRepository
         (Sprint 002 — default)                (Sprint 002 — default)
```

`ActivityService` and `NotificationService` depend only on the abstract interface; their module-level singletons (`activity_service`, `notification_service`) now construct with the Postgres repository by default — no router or frontend code changed. Both Postgres repositories open and close their own `SessionLocal()` session per call (see `app/database/database.py`) rather than receiving one via FastAPI dependency injection, because the singletons are constructed once at import time, not per-request — there is no request-scoped session available to hand them. Future route-level code (Sprint 004+) that reads/writes the other 5 tables should use the `get_db()` FastAPI dependency instead. **Any new module that needs storage should follow this same repository-behind-an-interface pattern.**

---

## 4. Frontend Modules

| Layer | Responsibility | Depends on |
|---|---|---|
| `app/*` (pages) | Route-level composition, one file per URL | `components/`, `hooks/`, `lib/` |
| `components/ui` | Dumb, reusable primitives — no data fetching, no business logic | Tailwind tokens only |
| `components/layout` | The shell itself: sidebar, topbar, collapse/mobile state | `components/ui`, `SidebarContext` |
| `components/shell` | Shell-level features (search, notifications dropdown, profile menu, shared page patterns) | `hooks/`, `lib/api.ts` |
| `components/dashboard` | Dashboard-specific composition | `hooks/`, `lib/`, `components/ui` |
| `components/theme` | Dark mode state | `localStorage`, `matchMedia` |
| `hooks/` | Data fetching (polling), UI state (online status, click-outside, count-up animation) | `lib/api.ts` |
| `lib/api.ts` | **The only place that calls `fetch()` against the backend** | `types/` |
| `types/` | TypeScript mirrors of backend pydantic models | — |

**Rule: nothing outside `lib/api.ts` calls `fetch()` directly.** If a new module needs a new backend call, add it to `lib/api.ts` first, then consume it through a hook.

---

## 5. Routing

### 5.1 Backend API routes

| Method | Path | Module | Notes |
|---|---|---|---|
| GET | `/` | `main.py` | Welcome message — unversioned, infra endpoint |
| GET | `/health` | `core.health` | Dependency-free liveness, `{"status":"healthy"}` — unversioned and unauthenticated. |
| GET | `/ready` | `core.health` | Bounded PostgreSQL `SELECT 1`; safe ready/unreachable 200/503 — unversioned and unauthenticated. Does not certify Alembic revision. |
| POST | `/api/v1/auth/signup` | `auth` | Creates a new tenant + its first (Owner) user, returns a token. New in Sprint 009. |
| POST | `/api/v1/auth/login` | `auth` | Issues a JWT for a valid email/password — payload now carries `tenant_id` (Sprint 009). New in Sprint 003. |
| GET | `/api/v1/auth/me` | `auth` | Returns the current user (+ tenant) for a valid bearer token. New in Sprint 003, tenant fields Sprint 009. |
| POST | `/api/v1/process` | `brain` → `assistant` | Keyword-routed, not AI |
| POST | `/api/v1/quote` | `quotes` | Full pricing calculation, thickness-aware since Sprint 005, **persists since Sprint 007**. Unrecognised material/thickness `400`, not a raw `500`. Stays public (ADR-023); since Sprint 012 (ADR-029), a valid token optionally tags the quote with the caller's tenant, otherwise it's created tenant-less (invisible to every tenant's browsing routes). A given `customer_id` must belong to the caller's own tenant when authenticated — `404` otherwise. |
| POST | `/api/v1/estimate` | `assistant.estimator` → `quotes` | Free-text → quote, persists since Sprint 007 |
| GET | `/api/v1/quotes` | `quotes` | **Auth required.** Optional `?limit=`. New in Sprint 007. |
| GET | `/api/v1/quotes/{quote_id}` | `quotes` | **Auth required.** `404` if not found. New in Sprint 007. |
| GET | `/api/v1/quotes/{quote_id}/invoice` | `quotes` | **Auth required.** Real downloadable PDF. New in Sprint 007 — replaces the removed `/quote/pdf`. |
| GET | `/api/v1/dashboard` | `main.py` | **Auth required since Sprint 012** (was fully public). Real numbers since Sprint 007, now the caller's own tenant's numbers only (ADR-029). |
| GET | `/api/v1/customers` | `customers` | **Auth required, tenant-scoped since Sprint 012 (ADR-029).** Optional `?limit=`. New in Sprint 004. |
| POST | `/api/v1/customers` | `customers` | **Auth required.** Also logs an `ActivityEvent`. New in Sprint 004. |
| GET | `/api/v1/customers/{customer_id}` | `customers` | **Auth required, tenant-scoped since Sprint 012.** `404` if not found or not the caller's tenant. New in Sprint 004. |
| GET | `/api/v1/projects` | `projects` | **Auth required, tenant-scoped since Sprint 012 (ADR-029).** Optional `?limit=`. New in Sprint 006. |
| POST | `/api/v1/projects` | `projects` | **Auth required.** Defaults `status="enquiry"`, logs an `ActivityEvent`. `customer_id` (if given) must belong to the caller's own tenant — `404` otherwise (ADR-029). New in Sprint 006. |
| GET | `/api/v1/projects/{project_id}` | `projects` | **Auth required, tenant-scoped since Sprint 012.** `404` if not found or not the caller's tenant. New in Sprint 006. |
| PATCH | `/api/v1/projects/{project_id}/status` | `projects` | **Auth required, tenant-scoped since Sprint 012.** `404`/`422` as documented. The first update-beyond-create endpoint. New in Sprint 006. |
| GET | `/api/v1/tenants` | `tenants` | **Auth required.** Since Sprint 012 (ADR-029), returns only the caller's own tenant — previously returned every tenant in the system, a cross-tenant leak. Optional `?limit=` (accepted, unused). New in Sprint 008. |
| POST | `/api/v1/tenants` | `tenants` | **Auth required.** Auto-slugifies `name` if `slug` omitted. Logs an `ActivityEvent`. Creates an unlinked tenant — the caller's own `tenant_id` doesn't change (audited, unchanged behavior, ADR-029). New in Sprint 008. |
| GET | `/api/v1/tenants/{tenant_id}` | `tenants` | **Auth required, tenant-scoped since Sprint 012.** `404` unless `tenant_id` is the caller's own. New in Sprint 008. |
| GET | `/api/v1/activity` | `activity` | **Auth required, tenant-scoped since Sprint 012 (ADR-029)** — previously fully public. Optional `?limit=` and `?type=` query params. Postgres-backed since Sprint 002 — survives a restart. |
| POST | `/api/v1/activity` | `activity` | **Auth required since Sprint 012.** Log a new event, tagged with the caller's tenant. Postgres-backed since Sprint 002. |
| GET | `/api/v1/notifications` | `notifications` | **Auth required, tenant-scoped since Sprint 012 (ADR-029)** — previously fully public. Optional `?limit=`. Postgres-backed since Sprint 002 — survives a restart. |
| GET | `/api/v1/notifications/unread-count` | `notifications` | **Auth required since Sprint 012.** Scoped to the caller's tenant. |
| POST | `/api/v1/notifications` | `notifications` | **Auth required since Sprint 012.** Create a notification, tagged with the caller's tenant. Postgres-backed since Sprint 002. |
| PATCH | `/api/v1/notifications/{notification_id}/read` | `notifications` | **Auth required, tenant-scoped since Sprint 012.** `404` if not found or not the caller's tenant. Postgres-backed since Sprint 002. |

`/api/v1` versioning landed in Sprint 003 (ADR-012) — the old unprefixed paths return `404`. JWT auth exists (`/api/v1/auth/*`) since Sprint 003 and is required on `/api/v1/customers/*` (Sprint 004, ADR-021), `/api/v1/projects/*` (Sprint 006, ADR-022), and `/api/v1/quotes/*` (Sprint 007, ADR-023) — `POST /api/v1/quote`/`/estimate` deliberately stay public, every other route remains public too (ADR-020). See `docs/USER_ROLES.md`.

### 5.2 Frontend routes

| Path | Page | Functional today? |
|---|---|---|
| `/` | Dashboard | ✅ Fully live, polls every 5s |
| `/login` | Sign in | ✅ Sprint 004 — real login against `/api/v1/auth/login`. Links to `/signup`. |
| `/signup` | Create workspace | ✅ Sprint 009 — company name + owner details, creates a tenant via `/api/v1/auth/signup`, signs the new owner in |
| `/quotes` | Quotes index | ✅ Sprint 007 — real list from the database, redirects to `/login` if not authenticated |
| `/quotes/[id]` | Quote detail | ✅ Sprint 007 — full price breakdown, linked customer, Download Invoice |
| `/quotes/new` | New Quote | ✅ Real pricing calculation, persists, optional customer link, Download Invoice once calculated (public — matches `POST /quote`'s auth posture; download itself needs sign-in) |
| `/customers` | Customers index | ✅ Sprint 004 — real list from the database, redirects to `/login` if not authenticated |
| `/customers/[id]` | Customer detail | ✅ Sprint 004 — customer details; Sprint 013/014 portal-link management; Sprint 016 documents; Sprint 017 adds a chronological Messages card with send form and 5-second polling |
| `/portal/[token]` | Client portal | ✅ Public active-token view: Sprint 013 tracking/invoices, Sprint 016 documents, Sprint 017 two-way plain-text Messages section with independent 5-second polling |
| `/customers/new` | New Customer | ✅ Sprint 004 — real persistence, redirects to the new customer's detail page |
| `/projects` | Projects index | ✅ Sprint 006 — real list, stage Badge per row, redirects to `/login` if not authenticated |
| `/projects/[id]` | Project detail | ✅ Sprint 006 — shows linked customer/notes, "Advance to \<next stage\>" control |
| `/projects/new` | New Project | ✅ Sprint 006 — real persistence, optional customer link via `<select>`, redirects to the new project's detail page |
| `/ai-assistant` | AI Assistant | ✅ Functional — calls `POST /process` |
| `/settings` | Settings | ✅ real content, not a placeholder: "Invite a teammate" + "Pending & past invitations" cards (Owner-only) — added prior to Sprint 013, exact sprint undocumented (sprint-010.md/sprint-011.md/sprint-012.md's own records each state no frontend UI shipped in those sprints). Sprint 015 adds a "Team" card, placed first: lists teammates with role/active-status Badges and a Deactivate button (Owner-only; hidden on the caller's own row) |

---

## 6. API Flow

### 6.1 Dashboard polling (the core pattern — every live panel follows this shape)

```
StatGrid / RecentActivityPanel / NotificationsPanel
        │
        ▼
useDashboardStats() / useActivity() / useNotifications()   (hooks/)
        │  wraps
        ▼
usePolling(fetcher, { intervalMs: 5000 })                   (hooks/usePolling.ts)
        │  calls immediately, then every 5s
        ▼
api.getDashboardStats() / api.getActivity() / api.getNotifications()   (lib/api.ts)
        │  fetch(`${NEXT_PUBLIC_API_URL}/...`)
        ▼
FastAPI route  →  Service  →  Repository (Postgres-backed as of Sprint 002)
```

`usePolling` returns `{ data, status, error, refetch }`. `status` drives the loading/error UI (`DashboardStatusBar`); `useOnlineStatus()` independently tracks `navigator.onLine` so an offline banner shows even if a request hasn't failed yet.

### 6.2 Quote creation flow (Sprint 007 — persistence moved server-side)

```
User fills the form on /quotes/new (optionally links a real customer)
        │
        ▼
api.createQuote(QuoteRequest)  →  POST /quote
        │
        ▼
QuoteService.create()  (quotes/service.py)
        │  ├─ QuoteCalculator.calculate()  (pure pricing, uses app.materials)
        │  ├─ crud.create_quote(...)        persists the row
        │  └─ activity_service.log(...)      logs a real ActivityEvent server-side
        ▼
QuoteResult (+ id, created_at) rendered on the page
        │
        ▼
Shows up in RecentActivityPanel within 5s (next poll) — no frontend logActivity() call anymore
        │
        ▼
"Download Invoice" → api.downloadInvoice(id) → GET /api/v1/quotes/{id}/invoice (auth required) → real PDF
```

The Customer and Project "new" flows follow the same server-side-logging shape (Sprint 004/006) — this sprint brought Quotes in line with them, the last of the three to move off frontend-side `logActivity()`.

### 6.3 AI Assistant flow

```
User types free text on /ai-assistant
        │
        ▼
api.processPrompt(text)  →  POST /process
        │
        ▼
BrainManager.process()  →  BrainRouter.think()  (keyword match, not AI)
        │
        ├── "sales"  →  SalesAssistant.reply()
        ├── "search" →  SearchAssistant.search()
        └── anything else → generic {"status": "received"} stub
        │
        ▼
Raw JSON response rendered on the page, with the resolved agent shown as a badge
```

### 6.4 Production release and request lifecycle (Sprint 018)

```text
operator supplies APP_ENV=production + secrets + persistent UPLOAD_DIR
        │
        ├── python -m app.core.runtime_check       (read-only, sanitized)
        ├── alembic upgrade head                  (one-off release job)
        └── verify alembic current == sole head
                │
                ▼
start default Uvicorn container                   (no migration, no seeding)
        │
        ├── lifespan configures logging
        ├── validates the existing writable upload mount
        └── begins serving after initialization succeeds
                │
                ├── GET /health → process liveness
                └── GET /ready  → bounded PostgreSQL reachability
                        │
                        ▼
authenticated/storage smoke → traffic promotion
```

For every request, the outer request-context middleware accepts a bounded safe `X-Request-ID` or generates a UUID, stores it in request/context-local state, returns it in the response, and emits one `http_request_completed` event. Production output is JSON to stdout/stderr. Logs use matched route templates and exclude query strings, concrete token-bearing URLs, authorization headers, bodies, secret values, and database URLs. Unexpected errors preserve the existing safe JSON response while emitting a correlated `unhandled_exception` event.

---

## 7. Design Principles

1. **Additive backend changes only, until Sprint 003's restructuring.** New capability is added as a new module with its own router, mounted in `main.py` with `app.include_router(...)`. Existing route bodies are never edited in place unless the task is specifically about that route.
2. **Repository pattern for anything that needs storage before the database exists.** See §3.1. This is not optional — it's the only reason Sprint 002 will be a clean swap instead of a rewrite.
3. **Single API client.** All HTTP calls go through `lib/api.ts`. This is what makes the migration to `/api/v1`, auth headers, or a WebSocket layer a one-file change later instead of a grep-and-replace across every component.
4. **The shell is not a page — it's infrastructure.** `AppShell`, `Sidebar`, `Topbar`, and everything under `components/shell/` exist so that a new module (e.g. Contracts, in v1.0) only needs a new folder under `app/` and a `lib/navigation.ts` entry. It should never need to touch layout code.
5. **Honesty over fake functionality.** Where a feature isn't built yet (Customers, Projects, Settings), the UI says so explicitly — a "Coming in Sprint N" badge, not a dead button or a silently-failing form. Forms that can't persist still do something real (log to Recent Activity) rather than pretending to save.
6. **Polling now, swappable for WebSockets later.** Every live data hook goes through the single `usePolling` primitive specifically so a future real-time layer replaces one function, not every component that displays live data.
7. **No new dependencies without a reason.** The icon set, the `cn()` classname helper, and the dropdown/click-outside logic are all hand-rolled rather than pulling in `lucide-react`, `clsx`, or a headless UI library, because the app doesn't need them yet at this scale. Revisit this if/when the component surface grows enough to justify the dependency weight.
8. **Archive, don't delete, until told otherwise.** Obsolete files move to `_legacy/` with a documented reason (see `apps/web/_legacy/README.md`), not `rm`. This is a standing instruction, not a one-off.
9. **Production startup serves; release jobs migrate.** Configuration validation and upload-mount checks belong to application startup, but schema changes remain an explicit, observable one-off release operation completed before containers receive traffic (ADR-034).
10. **Liveness, readiness, and schema state are separate gates.** `/health` proves the process can answer HTTP, `/ready` proves PostgreSQL is reachable within a bound, and Alembic commands prove revision state. No one signal substitutes for the others.

---

## 8. Coding Standards

### 8.1 Backend (Python / FastAPI)

- One module per business domain (`activity/`, `notifications/`, `quotes/`), each with `models.py` (pydantic), `service.py` (logic), `router.py` (HTTP layer). Add `repository.py` if the module needs storage before Sprint 002.
- Route handlers stay thin — they call a service method and return its result. Business logic lives in the service, not the router.
- Pydantic models are the single source of truth for request/response shape. The frontend's `types/*.ts` should mirror them by hand until there's a codegen step (not yet set up).
- Enums (`ActivityType`, `NotificationType`) are `str, Enum` subclasses so they serialise cleanly to JSON and stay in sync with the frontend's TypeScript union types.
- No bare `except:` blocks; no silent failures. If a new endpoint can fail meaningfully, raise `HTTPException` with a real status code (see `notifications/router.py`'s 404 on an unknown ID for the pattern).

### 8.2 Frontend (TypeScript / React / Tailwind)

- **`"use client"` only where needed** — on components that use hooks, state, or browser APIs. Static composition components (e.g. `ModuleIndexPage`'s callers) stay server components where possible.
- **Colour via CSS variables, never hardcoded hex in components.** Every colour is one of the tokens defined in `app/globals.css` (`background`, `surface`, `foreground`, `muted`, `border`, `accent`, `success`, `warning`, `danger`, `info`) and consumed as a Tailwind utility (`bg-surface`, `text-muted`, etc.). This is what makes dark mode automatic — components never need a `dark:` variant of their own.
- **Dark mode is class-based**, toggled on `<html>` via `ThemeProvider`, matched in CSS via the `@custom-variant dark (&:where(.dark, .dark *));` declaration in `globals.css` (Tailwind v4 has no `darkMode: "class"` config option — this is the v4-native equivalent).
- **No inline `fetch()` in components.** Always through `lib/api.ts` → a hook.
- **Effects only for synchronising with external systems** (browser APIs, subscriptions), never to derive state from other state — see the Sprint 001 audit for concrete examples of this rule being enforced by `eslint-plugin-react-hooks`. When an effect must set state from a browser-only API on mount, that's acceptable but should carry a comment explaining why (SSR can't read `localStorage`/`matchMedia`/`navigator.onLine`).
- **`cn()` from `lib/utils.ts`** for conditional class names — not a new dependency.
- **Path alias `@/*`** maps to `apps/web/` root (see `tsconfig.json`) — use it (`@/components/...`, `@/lib/...`) rather than relative `../../../` chains.
- **One component, one file, PascalCase filename matching the export.** Hooks are camelCase `useX.ts` under `hooks/`.

### 8.3 Verification bar (every sprint, before it's called done)

- `tsc --noEmit` — zero errors
- `eslint .` — zero errors, zero warnings
- `next build` — zero errors (Google Fonts require outbound network access; irrelevant sandboxes should verify with a temporary local-font swap, not skip the check)
- Every existing backend route smoke-tested with a real request after any backend change
- New/changed routes smoke-tested the same way

---

## 9. Roadmap — Sprint 002 to Sprint 016

Sprint 001 (application shell) is complete and audited — see `SPRINT-001-AUDIT.md`. Estimates are in developer-days (relative sizing, not a fixed-price quote), assuming AI-assisted development at the pace demonstrated in Sprint 001. **P0** = blocking/sequenced, **P1** = important but flexible ordering, **P2** = valuable, can slip a sprint.

### v0.1 — Foundation & Stabilise (Sprint 001 ✅ done, 002–003 remaining)

| Sprint | Feature | Priority | Depends on |
|---|---|---|---|
| **001** ✅ | Application shell, dashboard rebuild, Recent Activity + Notifications (in-memory) | P0 | — |
| **002** ✅ | Database foundation: PostgreSQL (Docker Compose, dev) + SQLAlchemy 2.0 + Alembic; core models (`Customer`, `Quote`, `Project`, `Material`, `User`, `ActivityLog`, `NotificationRecord`), all with `tenant_id` | P0 | Sprint 001 |
| **002** ✅ | Swap the in-memory activity/notification repositories for Postgres-backed ones — zero frontend changes, zero API surface changes, per §3.1 | P0 | Sprint 002 DB models |
| **003** ✅ | API restructuring: split `main.py` into `APIRouter` modules under `/api/v1`; `core/config.py` via `pydantic-settings` + `.env`; CRUD endpoints for `customers`/`quotes`/`projects`/`materials`/`users` deliberately deferred to their own sprints, not added in Sprint 002 | P0 | Sprint 002 |
| **003** ✅ | Error handling middleware (400/404/422 instead of raw 500s) | P0 | Sprint 003 routing |
| **003** ✅ | Basic JWT auth machinery, single-tenant — `login`/`me` implemented, but not applied to any route yet (ADR-020) and `UserProfileMenu`/`/settings` not wired up yet | P0 | Sprint 002 `User` model |
| **003** ✅ | `pytest` + coverage on the quote calculator and auth flow; basic CI (lint + test on push) | P0 | — |

### v0.2 — Core Business Operations

| Sprint | Feature | Priority | Depends on |
|---|---|---|---|
| **004** ✅ | CRM: customer list/detail/create, backed by the database — replaces `/customers/new`'s activity-log-only form with real persistence. First auth-enforced module (ADR-021). | P0 | v0.1 auth + DB |
| **005** ✅ | Full Material Library (quartz/granite/marble/porcelain/Dekton, reference pricing — see `docs/SPRINTS/sprint-005.md` for the "not a live supplier feed" caveat) + accurate slab-yield calculator (real area-based formula, replaces the placeholder in `slab_calculator.py`) | P0 | v0.1 DB |
| **006** ⬜ | AI Quotation Generator v1 (LLM-assisted text→quote extraction via the already-installed OpenAI SDK) — **deferred**, not part of Sprint 006 as actually delivered: no `OPENAI_API_KEY` configured, real usage costs money, tracked as its own future sprint | P1 | Sprint 005 |
| **006** ✅ | Projects module: job pipeline (enquiry → quoted → booked → templated → fabricated → installed → complete) — replaces `/projects/new`'s activity-log-only form. Second auth-enforced module (ADR-022), first update-beyond-create endpoint. | P1 | Sprint 004 |
| **007** ✅ | Invoice generator: proper PDF layout, VAT breakdown, letterhead, returned as a real download (`GET /api/v1/quotes/{id}/invoice`, not written to local disk). Required persisting quotes for the first time — the `quotes` table's original purpose, finally used. Third auth-enforced module (ADR-023). | P1 | Sprint 005 |
| **007** ✅ | Dashboard polish: all 4 stat cards computed from real data (`customers`/`projects` counts, `quotes_today`, all-time `revenue`) — previously hardcoded | P1 | Sprints 001–007 |

### v0.3 — AI Workforce & Automation

| Sprint | Feature | Priority | Depends on |
|---|---|---|---|
| **008** | Real AI Router: replace `BrainRouter`'s keyword `dict` with LLM/embeddings-based intent classification | P0 | v0.2 complete |
| **009** | Implement the 9 stub assistants (customer service, marketing, SEO, scheduling, finance, purchasing, construction, social, executive) | P1 | Sprint 008 |
| **010** | AI Sales Assistant + AI Customer Support (chat-based, grounded in CRM/material data) | P1 | Sprint 009 |
| **011** | Appointment booking + calendar integration; marketing dashboard + social scheduler; automation (lead nurture, quote-expiry reminders); Analytics v1 | P2 | Sprint 004–010 |

### v1.0 — Production SaaS Platform

| Sprint | Feature | Priority | Depends on |
|---|---|---|---|
| **012** | Multi-tenant architecture refactor (de-risked if Sprint 002 added a `tenant_id` column to every table up front) | P0 | Sprint 002 |
| **013** | Client Portal (project tracking, documents, messaging) | P1 | Sprint 012 |
| **014** | Contracts + digital signatures; Payment tracking (Stripe/GoCardless) | P1 | Sprint 012 |
| **015** | Staff management + RBAC; Supplier database + purchasing workflow | P2 | Sprint 012 |
| **016** | AI Renovation Planner / Design Assistant / Stone Visualiser (vision model + rendering); full observability; security hardening; subscription billing | P2 | Sprint 012, highest R&D risk in the roadmap |

Full context on architecture decisions (ORM choice, auth strategy, multi-tenancy model, CI/CD timing) and risk mitigations behind this roadmap lives in `SIMO-OS-Architecture-Report.md`.

---

*This document should be updated at the close of every sprint — folder structure, route tables, and the "done vs. not built" markers throughout §2–§6 are the parts most likely to go stale first. Last updated for runtime architecture: Sprint 018 (18 August 2026). Note: §9's Sprint 008–016 sequence below is preserved as historical, potentially stale roadmap material; Sprint 018 deliberately does not reconcile or modify `docs/ROADMAP.md`.*
