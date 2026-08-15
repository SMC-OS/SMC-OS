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
**Status:** IMPLEMENTED (Sprint 003 — `app/auth/`)

Stateless tokens were chosen over sessions so a future mobile app or client portal doesn't need a rework to authenticate. `POST /api/v1/auth/login` issues an `HS256` JWT (`sub`=user id, `exp`), `GET /api/v1/auth/me` validates one via `app/auth/dependencies.py`'s `get_current_user`. Passwords are `bcrypt`-hashed in the new `users.password_hash` column. See ADR-020 for the scope decision on where this is actually enforced.

## ADR-012: API versioning — `/api/v1` prefix
**Status:** IMPLEMENTED (Sprint 003)

Every route except `GET /`/`GET /health` (kept unversioned as infra/health-check endpoints) now lives under `/api/v1` (see `docs/API_SPEC.md`). Cutover was clean, not dual-mounted — the old unprefixed paths return `404` — because only the frontend consumes this API and there was no external client to break.

## ADR-013: Multi-tenancy model — row-level `tenant_id`, not separate schemas
**Status:** IMPLEMENTED for the column (all 7 tables, Sprint 002); IMPLEMENTED as a real FK (Sprint 008, see ADR-025); DECIDED-NOT-IMPLEMENTED for enforcement (Sprint 012)

Simpler to operate at this scale than per-tenant schemas. Adding the column early (Sprint 002) even though it isn't enforced until Sprint 012 was judged cheap insurance against an expensive later migration. **Update, Sprint 008:** a real `tenants` table now exists and the column is a genuine `ForeignKey("tenants.id")` on all 7 tables (previously a plain nullable UUID with no table to point at) — see ADR-025 for the full detail. Still nullable, still nothing reads or filters by it today; that's Sprint 012.

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

`PostgresActivityRepository`/`PostgresNotificationRepository` call `SessionLocal()` directly inside each method (`with SessionLocal() as db:`) rather than receiving a session through FastAPI's `Depends(get_db)`. **Why:** `activity_service`/`notification_service` are module-level singletons constructed once at import time (ADR-001 predates the database and this hasn't changed), not per-request objects — there is no request-scoped session available to inject into them. `app/database/database.py`'s `get_db()` dependency exists for future route-level code (Sprint 004+, once `customers`/`quotes`/`projects` get real endpoints) that isn't built around a singleton and can take a request-scoped session normally. `app/auth/` (Sprint 003) is the first module to actually use it, per ADR-011.

## ADR-020: Sprint 003 auth ships as machinery only — no existing route is gated by it
**Status:** IMPLEMENTED (Sprint 003); superseded for `customers` specifically by ADR-021 (Sprint 004)

`get_current_user` (`app/auth/dependencies.py`) is a working, reusable FastAPI dependency, but it is not attached to any of the routes in `docs/API_SPEC.md` — `/api/v1/quote`, `/api/v1/activity`, `/api/v1/notifications`, etc. all remain fully public. **Why:** deliberate scope decision made with the person building this before Sprint 003 started. There's no real per-user data yet (Sprint 004's CRM is the first module that will have any), so protecting today's routes would mean the frontend needs an `Authorization` header on every call with only one seeded user to test against, for no actual data-isolation benefit. Enforcement is deferred to whichever future sprint first has something worth protecting. This remains historically accurate for Sprint 003 — Sprint 004 is that future sprint, for `customers` only (see ADR-021); `/quote`, `/activity`, `/notifications`, etc. are still fully public.

## ADR-021: `customers` is the first module with enforced JWT auth
**Status:** IMPLEMENTED (Sprint 004 — `app/customers/router.py`)

All three `/api/v1/customers/*` routes require `Depends(get_current_user)` — this is exactly the trigger ADR-020 described: real per-user business data (customer records) now exists. **Why now, and why customers first:** Sprint 004 is literally the first sprint to introduce real business data via the roadmap; leaving it public would mean the first genuine CRM data in the system is unauthenticated while the machinery to prevent that already existed. **Consequence:** the frontend needed a way to obtain and hold a token for the first time — `apps/web/lib/auth-storage.ts` (localStorage), `components/auth/AuthProvider.tsx` (React context, mirrors `ThemeProvider`'s shape), and a new `/login` page were added as the minimum needed to support this, not a full account/settings UX. `lib/api.ts`'s `request()` now attaches the stored token to every call (harmless on the still-public routes) and clears it on a `401`. Every other route from Sprint 001–003 remains public, unaffected by this decision — enforcement was applied surgically to the one module that triggered it, not broadly.

## ADR-022: `projects` is the second module with enforced JWT auth; its status-update endpoint is the first write beyond create
**Status:** IMPLEMENTED (Sprint 006 — `app/projects/router.py`)

All four `/api/v1/projects/*` routes require `Depends(get_current_user)`, extending ADR-021's reasoning: projects are real business data linked to real customers, so the same logic applies. **No new frontend auth work was needed** — Sprint 004's login/token plumbing already covers any protected route, `lib/api.ts`'s `request()` already attaches the stored token everywhere.

**The one deliberate deviation from the Customers precedent:** Sprint 004 shipped list/detail/create only, no update. A "job pipeline" (`enquiry → quoted → booked → templated → fabricated → installed → complete`) is meaningless without a way to move a project between stages, so `PATCH /api/v1/projects/{id}/status` exists as a narrow, single-purpose exception — it can only change `status`, nothing else about a project. This is the first update-beyond-create endpoint in the API. Every other route's "no update" posture (customers, materials) is unaffected — this was a reasoned, scoped exception for the one feature that structurally required it, not a general policy change.

## ADR-023: `quotes` is the third module with enforced JWT auth — but only its browsing routes, not creation
**Status:** IMPLEMENTED (Sprint 007 — `app/quotes/router.py`)

`GET /api/v1/quotes`, `GET /api/v1/quotes/{id}`, and `GET /api/v1/quotes/{id}/invoice` require `Depends(get_current_user)` — real business data, same reasoning as ADR-021/ADR-022. **The deliberate asymmetry:** `POST /api/v1/quote` and `POST /api/v1/estimate` (where a quote is actually created) stay public. Locking those down would mean an unauthenticated visitor could no longer get a price estimate at all — a regression against the original engine's contract, and `/estimate`'s free-text path has no notion of "the current user" to check anyway. Only *browsing what's already been calculated* (the list, a specific record, its invoice) is gated. This is a genuinely different shape from customers/projects, where creation and browsing are both protected — a considered choice, not an inconsistency.

**Also this sprint:** quotes are persisted for the first time (`app/quotes/service.py` wraps the existing pure `QuoteCalculator`), and `POST /api/v1/quote/pdf` is removed in favour of `GET /api/v1/quotes/{id}/invoice` — generating an invoice now requires an already-persisted quote, downloadable again later, not just once at calculation time. See `docs/SPRINTS/sprint-007.md` for the full design (including why `quotes` has no text customer-name column, only `customer_id`).

## ADR-024: AI Quotation Generator v1 extracts structured fields only, never computes pricing
**Status:** IMPLEMENTED (AI Quotation Generator v1, `d306c99`)

`app/quotes/ai_draft.py`'s `AIDraftService` and `app/quotes/ai_models.py`'s `AIQuoteDraft` schema have no price/VAT/total field anywhere — not just an instruction the model is told to follow, but a structural guarantee: the pydantic response shape it's forced into via OpenAI's structured outputs has nowhere to put a monetary figure, so a bad or manipulated model response can extract a wrong material or a wrong length, but it cannot inject a price into the system. Every extracted value is also re-validated server-side against the real material catalogue and known thickness values (`AIDraftService._validate`) before being returned — three layers total: (1) structured-output JSON-shape enforcement, (2) refusal/error handling, (3) server-side truth-checking against the database, which is the layer that actually matters. **Why:** pricing is SIMO OS's core business logic (`app/quotes/calculator.py`) — letting an LLM anywhere near it, even indirectly, would mean a hallucinated or adversarially-prompted number could reach a customer's invoice. The AI's job is narrowly "turn free text into a pre-filled form for a human to review," never "decide what something costs." (This ADR was referenced by `ai_draft.py`'s docstring before it was written — added in Sprint 008 to close that gap, not a Sprint 008 design decision itself.)

## ADR-026: Tenant-aware authentication — `users.tenant_id` becomes real, JWT gains a `tenant_id` claim
**Status:** IMPLEMENTED (Sprint 009)

Sprint 008 (ADR-025) built the `tenants` table and made every `tenant_id` column a real FK but left every one of them nullable and unenforced. Sprint 009 makes `users.tenant_id` — and only that one column — actually load-bearing: it's now `NOT NULL` (migration `c28dd4348080`), every user belongs to exactly one tenant, and `POST /api/v1/auth/signup` creates a new `Tenant` + its first `User` (role `"Owner"`) together, reusing `app.tenants.service.tenant_service.create()` rather than duplicating slug-generation logic. The other 6 tables (`customers`, `quotes`, `projects`, `materials`, `activity_log`, `notifications`) stay nullable — this sprint is deliberately narrow, not a preview of Sprint 012's full enforcement.

**JWT shape change, clean cutover:** `create_access_token()` now embeds `tenant_id` alongside `sub`; `decode_access_token()` returns the whole payload instead of just the `sub` string. `get_current_user` rejects any token missing a `tenant_id` claim — which is every token issued before this sprint — with a `401`, the same "old shape just stops working, no dual-mode shim" precedent ADR-012 set for the `/api/v1` prefix cutover. **The database row remains the actual authority**, not the claim: `get_current_user` still fetches the full `User` row by `sub` and returns it; the `tenant_id` claim is only checked for presence/shape, never substituted for `user.tenant_id`. This avoids two sources of truth ever disagreeing.

**Backfill, not a breaking migration:** the pre-Sprint-009 seeded owner account (created before `tenants` existed, `tenant_id` was `NULL`) is assigned to a newly-created "Default Workspace" tenant by the migration itself before the `NOT NULL` constraint is added — no manual intervention needed, no account left orphaned. `app/auth/seed.py` now goes through `AuthService.signup()` (the same code path a real company's first signup uses) instead of a bare `create_user()` call, so the seeded owner and every future first-user-of-a-company are created identically.

**Explicitly out of scope, by design:** teams/multiple users per tenant beyond the Owner (Sprint 010 — roles/permissions), invitations (Sprint 011), and — critically — no query in any *business-data* module (`customers`, `projects`, `quotes`, `materials`, `activity`, `notifications`, `dashboard`) was touched or gained a tenant filter. A logged-in user now definitely belongs to a tenant, but nothing yet uses that fact to isolate their data from another tenant's — that remains Sprint 012, unstarted.

## ADR-025: Multi-tenancy — a real `tenants` table, still fully unenforced
**Status:** IMPLEMENTED for the schema (Sprint 008); DECIDED-NOT-IMPLEMENTED for enforcement (Sprint 012)

Sprint 002 added a nullable `tenant_id` UUID column to every table as cheap insurance (ADR-013), with no `tenants` table to point at and nothing reading it. Sprint 008 cashes that in: a real `tenants` table now exists (`id`, `name`, `slug` unique, `status`, `created_at`), and all 7 existing `tenant_id` columns are converted from a bare UUID into a real `ForeignKey("tenants.id")` — via two separate, independently-revertible Alembic migrations (create the table; then add the 7 FK constraints), not one bundled change. Every column stays **nullable** and **no query anywhere is filtered by it** — every existing route keeps reading/writing across all rows exactly as before Sprint 008, verified by the full existing test suite passing unchanged. A minimal `app/tenants/` module (list/get/create, `Depends(get_current_user)` — the existing single-tenant auth gate, reused rather than inventing a new one) exists so the table has something to populate it, but nothing yet ties a logged-in user to a specific tenant row. **Why split into two migrations:** the table-creation and the FK-constraint-addition are independently safe and independently revertible — if the FK step ever needed to be rolled back alone (e.g. a constraint-naming issue), the table and any rows in it wouldn't need to go with it. **Why `status` defaults to `"active"`, not `"trial"`:** no trial/billing concept exists yet (that's Sprint 018+); defaulting to a status the system doesn't yet act on differently would be a value with no behaviour behind it, and defaulting to something implying a lifecycle that doesn't exist would violate ADR-006's honesty precedent. **What this is not:** tenant-aware authentication (Sprint 009 — JWTs don't carry `tenant_id` yet, `users.tenant_id` isn't enforced `NOT NULL` yet) or isolation enforcement (Sprint 012 — no service method filters by tenant yet). This sprint is schema and CRUD plumbing only, the same "ship the machinery, enforce it later" shape Sprint 003's JWT auth had until Sprint 004 (ADR-020/021).

## ADR-027: Roles formalized as `UserRole`; `require_role()` added, wired into nothing
**Status:** IMPLEMENTED for the machinery (Sprint 010); DECIDED-NOT-IMPLEMENTED for enforcement (no target sprint yet — depends on Sprint 011)

`role` (`users.role`) was a free `str | None` since Sprint 003. Sprint 010 constrains it to `app.auth.models.UserRole` (`OWNER = "Owner"`, `STAFF = "Staff"`) — validated at the Pydantic/API boundary the same way `ProjectStatus` constrains `Project.status` (ADR-022's precedent): no native Postgres enum, no DB `CHECK` constraint, still a plain `String` column. `AuthService.signup()` now assigns `UserRole.OWNER.value` instead of the string literal `"Owner"`.

**`require_role(*allowed_roles)`** (`app/auth/dependencies.py`) is a dependency factory mirroring `get_current_user`'s shape: given one or more `UserRole` values, it returns a FastAPI dependency that 403s any authenticated user whose role isn't in the allowed set. **It is not attached to any route.** Every user in the system today — the seeded owner and every signup's first user — is a `UserRole.OWNER`; there is no way yet to create a `UserRole.STAFF` user (Sprint 011's invitations don't exist yet), so gating any current route by role would restrict nobody. Attaching it now would be enforcement theatre — a check that always passes isn't meaningfully enforcement, and a route wrongly gated to `OWNER`-only today would silently continue working for every real user while looking more restrictive than it is. Tested directly as a unit (`tests/test_permissions.py`), not through an HTTP route, since there is no route to test it through yet.

**Why build this now, before Sprint 011:** the roadmap explicitly separates "roles/permissions" (Sprint 010) from "invitations" (Sprint 011) — see `docs/USER_ROLES.md` §2. This sprint delivers the former in isolation: the enum and the checking primitive exist and are tested, so Sprint 011 (or whichever sprint first has a second real role to protect against) can attach `require_role(...)` to a route as a one-line change instead of inventing the mechanism at the same time it's first needed — the same "ship the machinery, enforce it later" shape ADR-011 (JWT auth) and ADR-025 (tenant FK) both already followed successfully.

## ADR-028: Staff invitations — opaque hashed token, Staff-only, `require_role(OWNER)` finally attached to a route
**Status:** IMPLEMENTED (Sprint 011)

The first sprint that lets a tenant have more than one user. `app/invitations/` (`models.py`/`service.py`/`router.py`) adds a `POST /api/v1/invitations` (Owner-only, creates a pending invite for an email), `GET /api/v1/invitations` (Owner-only, lists the tenant's invites), `DELETE /api/v1/invitations/{id}` (Owner-only, revokes one), a public `GET /api/v1/invitations/token/{token}` (lets an unauthenticated invitee see what they're accepting before committing), and a public `POST /api/v1/invitations/token/{token}/accept` (creates the `Staff` user and logs them in). This is also the first route anywhere gated by `require_role(UserRole.OWNER)` (ADR-027) — the machinery built in Sprint 010 finally has a real second role (`Staff`) to protect against, so gating `POST`/`GET`/`DELETE /invitations` by `OWNER` is meaningfully restrictive rather than enforcement theatre.

**Why an opaque hashed token, not a self-contained JWT:** a JWT would need no DB row at all, but the Owner needs to list pending invitations and revoke one before it's accepted — both require a queryable row that outlives the token's issuance. The token itself is `secrets.token_urlsafe(32)`, hashed with SHA-256 before it's ever written to the `invitations` table (`token_hash`, unique) — the same "never persist the recoverable secret" convention `password_hash` already established. The raw token exists only in `create_invitation()`'s return value and the one HTTP response that creates it; nothing else in the system, including this table, can recover it. `GET .../token/{token}` and `POST .../token/{token}/accept` re-hash the presented token and look up by `token_hash`, never by a stored plaintext value.

**Why Staff-only, not a `role` field on `InvitationCreate`:** `create_invitation()` always writes `UserRole.STAFF.value`. The `role` column exists on the table (so a future sprint can widen this without a migration), but letting an Owner mint a second Owner via this flow is a materially bigger decision — implicitly delegating full tenant control — than "invite a teammate" implies, and wasn't part of what was scoped or agreed for this sprint. Left to a future sprint if the business need actually arises.

**Why `expires_at` is a real column but `"expired"` isn't a stored status:** `status` is one of `"pending" | "accepted" | "revoked"` (plain `String`, same convention as `User.role`/`Project.status`) — `"expired"` is derived at read time (`InvitationService.derive_status()`) by comparing a still-`"pending"` row's `expires_at` against the current time, and surfaced wherever a row's status is shown (`GET /invitations`, `GET /invitations/token/{token}`) without ever writing anything back. `accept_invitation()` does the equivalent check inline (it needs to distinguish `"expired"` from `"revoked"`/`"accepted"` for its error message, and checks `status != "pending"` first so an already-revoked-then-expired row still reports `"revoked"`, not `"expired"`). Storing `"expired"` would mean either a background job to flip it (nothing like that exists anywhere in this codebase) or a stale value between expiry and the next write — deriving it is strictly simpler and can't go stale.

**Why cross-tenant invitation lookups 404, not 403:** `revoke_invitation()` treats "invitation belongs to a different tenant" identically to "invitation doesn't exist" (`InvitationNotFoundError` either way) — the same reasoning `docs/USER_ROLES.md` §3 and the tenant-scoped modules already apply: confirming *that* another tenant's invitation exists, even while correctly refusing to act on it, is itself a cross-tenant information leak.

**What this is not:** tenant data isolation enforcement in general (Sprint 012, still unstarted — this sprint's own queries are scoped by `tenant_id` because invitations are inherently tenant-scoped data, not because of a general enforcement mechanism); a permission matrix beyond "Owner can manage invitations, anyone can accept one with a valid token" (deciding which *other* routes should become `OWNER`-only remains explicitly deferred, per ADR-027); email delivery (no email is actually sent — the raw token is returned directly in the `POST /invitations` response body, the same "ship the mechanism, wire up delivery separately" shape as `docs/SPRINTS/sprint-007.md`'s invoice PDF landing before any email-sending existed); and any frontend UI (no page renders an invite-management screen or an accept-invite flow — same posture as Sprint 008's and Sprint 010's backend-only sprints, since a second role existing in the API is a precondition for a useful invite UI, not the other way around).
