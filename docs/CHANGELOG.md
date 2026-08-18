# SIMO OS — Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/). Derived from `git log` on the `SMC-OS` repository. Dates are commit dates, not necessarily when work started.

---

## 2026-08-18 — (uncommitted) — Sprint #018 — Production Runtime Hardening

Full design and release policy are recorded in `docs/superpowers/specs/2026-08-18-sprint-018-production-runtime-hardening-design.md`, `docs/DECISIONS.md` ADR-034, and `docs/PRODUCTION_RUNBOOK.md`.

**Scope note:** Launch-readiness hardening only. No product feature, tenant/auth rule, hosting provider, object storage, virus scanning, quota, email/password reset, billing, rate limit, WebSocket/SSE, full APM platform, roadmap reconciliation, or Sprint 019 work is included.

**Runtime/configuration:** Adds explicit `APP_ENV=development|test|production` policy, a sanitized read-only `python -m app.core.runtime_check` preflight, fail-closed production JWT/seed/database/CORS/upload validation, and `SEED_DATA_ENABLED`. Development/test keep their local defaults and optional seed convenience. Production seeding is forbidden and application import/startup never runs Alembic.

**Startup/health/observability:** Moves runtime initialization into FastAPI lifespan so module import performs no database writes. Production startup validates that the persistent upload mount already exists and is writable. `/health` remains dependency-free and response-compatible; new `/ready` performs a bounded PostgreSQL `SELECT 1` with safe 200/503 bodies. Request middleware validates or generates `X-Request-ID` and production emits allowlisted JSON request/error/startup/readiness events without query strings, authorization headers, bodies, secrets, raw database errors, or concrete token-bearing paths.

**Release/container/frontend:** Adds a provider-neutral Python 3.12 slim non-root backend image whose default command starts only Uvicorn. Production migrations remain a separate one-off `alembic upgrade head` release job completed before application startup and traffic promotion. The frontend retains its loopback development fallback but an explicit production build requires a safe absolute HTTPS API origin.

**Operations:** Documents the migration-first release sequence, separate schema-compatible application rollback, explicit operator-only downgrade conditions, health interpretation, and the persistent upload-volume ownership/backup/restore/restart contract. Local filesystem storage remains limited to one backend instance or instances sharing the same supported filesystem.

**Verification status:** Implementation verification is in progress. Exact backend, Alembic, frontend, image, container, and persistence-smoke results will be recorded only after the integrated Sprint 018 release gates run; this entry does not claim those checks have passed.

## 2026-08-18 — (uncommitted) — Sprint #017 — Client Portal Messaging

Full detail in `docs/DECISIONS.md` ADR-033 and `docs/SPRINTS/sprint-017.md`.

**Scope note:** Closes the final part of the client-portal gap deferred since Sprint 013: tracking, documents, and messaging are now implemented. `docs/ROADMAP.md` remains untouched.

**Backend:** Adds the customer-level `messages` table and `app/messages/` module; authenticated staff can post/list a customer's chronological thread, while active portal tokens can post/list only their own customer's thread. Staff messages carry nullable `sender_user_id` attribution and create no activity/notification. Each inbound customer message creates one `CUSTOMER_MESSAGE_RECEIVED` activity event and one tenant-scoped informational notification. Bodies are plain text, reject blank input, and cap at 5,000 characters. No rate limiter, attachments, editing/deleting, or WebSockets/SSE were added.

**Frontend:** Adds polling message threads and send forms to `/customers/[id]` and `/portal/[token]`. Both poll every five seconds and render message bodies as escaped JSX text with preserved line breaks.

**Verification:** 21 targeted Sprint 017 tests pass; full backend, Alembic round-trip, frontend lint/type/build, tenant-isolation review, and final diff/scope results are recorded in `docs/SPRINTS/sprint-017.md`.

## 2026-08-16 — (uncommitted) — Sprint #016 — Client Portal Documents (Upload/Download)

Full detail in `docs/DECISIONS.md` ADR-032 and `docs/SPRINTS/sprint-016.md`.

**Scope note:** Closes the "documents" half of the client-portal gap deferred since Sprint 013 (ADR-030), named again in Sprint 014's and Sprint 015's follow-ups — three sprints running. Messaging remains deferred. `docs/ROADMAP.md`'s stale Sprint 016 line (AI features/observability/security/billing) is untouched and unaddressed.

**Backend**
- Migration `b0bddd0fb66b`: new `documents` table (additive-only). New setting `upload_dir` (local disk). New dependency `python-multipart==0.0.20`, required for `UploadFile`, flagged explicitly.
- New `app/documents/` module — `POST`/`GET /api/v1/documents`, `GET /api/v1/documents/{id}/download`, none `require_role`-gated. Upload security policy: 20MB cap enforced against actual bytes, explicit extension allowlist (not denylist), generated `uuid4()` storage filename never derived from user input, `storage_filename` never exposed in any response.
- Two new public routes on the **existing** `app/portal/router.py` (not a new router) — `GET /token/{token}/documents` and `.../download` — mirroring the existing invoice-download route's exact shape.

**Frontend**
- `apps/web/app/customers/[id]/page.tsx` gains a Documents card (upload + list + download).
- `apps/web/app/portal/[token]/page.tsx` gains a Documents section (list + download, no login).
- New `apps/web/types/document.ts`; `apps/web/lib/api.ts` gains 5 new methods, downloads use the existing blob-fetch-and-save pattern.

**Tests**
- New `tests/test_documents.py` (12 tests): upload success/cross-tenant/oversized/disallowed-extension, staff list/download/cross-tenant-download/unknown-document, portal list/download/cross-customer-rejection/revoked-link-rejection.
- Full suite: 157/157 passing.

**Verified:** `pytest` (157/157), `alembic check` ("No new upgrade operations detected"), a clean `downgrade -1`/`upgrade head` round-trip, `pnpm lint` (0 errors/warnings), `pnpm build` (TypeScript clean, 15 routes, same as Sprint 015 baseline), `git diff --check` (clean), and a manual smoke test against the real running app confirming upload/list/download/rejection/revocation end-to-end, including a direct on-disk check that stored filenames are generated UUIDs, never original names.

## 2026-08-15 — (uncommitted) — Sprint #015 — Team Management (View Team, Deactivate a Teammate)

Full detail in `docs/DECISIONS.md` ADR-031 and `docs/SPRINTS/sprint-015.md`.

**Scope note:** `docs/USER_ROLES.md` names an open permission-matrix gap — deciding which routes should require `OWNER` specifically (tenant settings? billing? removing a teammate?) — and this sprint resolves the "removing a teammate" example. `docs/ROADMAP.md`'s literal Sprint 015 line ("Staff management + RBAC; Supplier database + purchasing workflow") is stale: RBAC shipped in Sprint 010–011, four sprint-numbers early. The roadmap's Supplier/Purchasing line remains entirely unaddressed; `docs/ROADMAP.md` not touched.

**Backend**
- Migration `dae9516f388b`: `users.is_active BOOLEAN NOT NULL DEFAULT true` (additive-only).
- New `app/users/` module — `GET /api/v1/users` (list team), `POST /api/v1/users/{id}/deactivate`, both `require_role(UserRole.OWNER)`-gated. Soft-deactivation, not row deletion (`Invitation.invited_by_user_id`/`PortalLink.created_by_user_id` are `NOT NULL` FKs to `users.id`). Self-deactivation blocked at the service layer (409); cross-tenant lookups → 404. Deactivation logs a new `ActivityType.TEAM_MEMBER_DEACTIVATED` event.
- `app/auth/dependencies.py`: `get_current_user` now also rejects a deactivated user's token (401, same generic message as an invalid token) — no extra query, the row is already fetched. A deactivated teammate's portal links deliberately keep working — no cascade-revoke.

**Frontend**
- `apps/web/app/settings/page.tsx` gains a "Team" card (first, above "Invite a teammate"): teammates with role/active-status `Badge`s, a Deactivate button on active rows other than the caller's own.
- `AuthProvider` gains `userId` (mount effect, login, signup, acceptInvite; cleared on logout) so the UI can hide the self-deactivate action — the server enforces the real rule regardless.
- New `apps/web/types/user.ts`; `apps/web/lib/api.ts` gains `getUsers()`/`deactivateUser(id)`.

**Tests**
- New `tests/test_users.py` (9 tests): list-team success/role-gated, deactivate flips `is_active` + logs activity, activity isolation, self-deactivate 409, unknown/cross-tenant deactivate 404, portal link survives deactivation (no cascade), deactivated user's existing token rejected (401).
- Full suite: 145/145 passing.

**Verified:** `pytest` (145/145: 136 pre-existing + 9 new), `alembic check` ("No new upgrade operations detected"), a clean `downgrade -1`/`upgrade head` round-trip, `pnpm lint` (0 errors/warnings), `pnpm build` (TypeScript clean, 15 routes, same as Sprint 014 baseline), `git diff --check` (clean), and a manual smoke test against the real running app (uvicorn + local Postgres) confirming list/deactivate/403/401/409/no-cascade end-to-end.

## 2026-08-15 — (uncommitted) — Sprint #014 — Portal Link Activity Logging + Management UI

Full detail in `docs/SPRINTS/sprint-014.md`.

**Scope note:** `docs/ROADMAP.md`'s Sprint 014 line ("Contracts + digital signatures; Payment tracking") is stale, same as flagged in prior sprints' docs — this sprint instead closes the follow-up item `sprint-013.md` explicitly named (no frontend list/revoke UI for the already-shipped `GET`/`DELETE /portal-links` routes) plus a related gap found during this sprint's planning (portal link creation wasn't logging an `ActivityEvent`, unlike every other creation flow). The roadmap's original Sprint 014 scope remains unaddressed and unscheduled.

**Backend**
- `ActivityType.PORTAL_LINK_CREATED` added (`app/activity/models.py`); `PortalService.create_link()` now calls `activity_service.log()` after row creation — title "Portal link shared", description = customer name. Revoke deliberately does not log, matching `revoke_invitation()`'s precedent.
- No new routes, no migration — `ActivityLog.type` is a plain `String` column, confirmed no schema change was needed.

**Frontend**
- `apps/web/app/customers/[id]/page.tsx`'s "Client portal" card gained a list of existing links (created/expires dates, status `Badge`, Revoke button on active links), consuming the pre-existing Sprint 013 `getPortalLinks`/`revokePortalLink` client methods.
- One fix-round: `loadPortalLinks` now clears a stale `linksError` at the top of the function, so a prior failed load no longer hides a subsequent successful one.

**Tests**
- New in `tests/test_portal.py` (2 tests): `test_create_portal_link_logs_activity`, `test_create_portal_link_activity_not_visible_to_other_tenant` (real cross-tenant isolation check, ADR-029 convention).
- Full suite: 136/136 passing.

**Verified:** `pytest` (136/136, run twice), `pnpm lint` (0 errors/warnings), `pnpm build` (TypeScript clean, 15 routes, same as Sprint 013 baseline), `alembic check` ("No new upgrade operations detected"), and a manual smoke test against the real running app (uvicorn + local Postgres) confirming create → list → revoke and single-log-on-create behavior. UI Badge/list rendering was verified via diff-level review and a clean `next build`, not a literal browser check.

## 2026-08-15 — (uncommitted) — Sprint #013 — Read-Only Client Portal

Full detail in `docs/DECISIONS.md` ADR-030 and `docs/SPRINTS/sprint-013.md`.

**Scope note:** `docs/ROADMAP.md`'s Sprint 013 bundles tracking + documents + messaging under "Client Portal." This sprint deliberately covers tracking only, matching every prior sprint's one-capability-per-sprint cadence — documents and messaging remain unstarted, their own future sprints.

**Backend**
- New `app/portal/` module (`models.py`/`service.py`/`router.py`) — reuses `app/invitations/`'s exact hashed-token mechanism (`secrets.token_urlsafe(32)` + SHA-256, hash-only persistence) but reusable, not single-use: `PortalLink.status` is `"active"|"revoked"` only, no accept step.
- `POST /api/v1/portal-links` (any authenticated tenant user, not Owner-only), `GET /api/v1/portal-links`, `DELETE /api/v1/portal-links/{id}` (all tenant-scoped, cross-tenant → `404`), and public `GET /api/v1/portal-links/token/{token}`.
- `customer_id` must resolve under the caller's own tenant at creation time (`CustomerNotFoundError`, reusing Sprint 012's relationship-linkage-bypass pattern) — `404` otherwise.
- `app/database/models.py`: new `PortalLink` table. `app/database/crud.py`: `create_portal_link`, `get_portal_link_by_id`/`by_token_hash`, `list_portal_links`, `update_portal_link_status`, `list_projects_by_customer`, `list_quotes_by_customer`.
- Migration `880e12adf384`: adds `portal_links` (additive-only new table).
- `app/core/config.py`: `portal_link_expire_days` (default 90 — deliberately longer than `invitation_expire_days`'s 7).

**Frontend**
- New public page `apps/web/app/portal/[token]/page.tsx` — the fetch/loading/error/status-conditional shell from `apps/web/app/invite/[token]/page.tsx`, minus the entire account-creation form (no `users` row, no login).
- `apps/web/app/customers/[id]/page.tsx`: new "Client portal" card to generate and copy a portal link, modeled on `apps/web/app/settings/page.tsx`'s invitation UI.
- New `apps/web/types/portal.ts`; `apps/web/lib/api.ts` gains `createPortalLink`/`getPortalLinks`/`revokePortalLink`/`getPortalByToken`.

**Tests**
- New `tests/test_portal.py` (15 tests): creation/list/revoke, relationship-linkage-bypass (`customer_id` from another tenant → `404`), full cross-tenant isolation, reusability (same token fetched twice, no state change — the key difference from `Invitation.accept`), revoked/expired-reads-as-such-with-no-data.
- Full suite: 130/130 passing.

**Verified:** `pytest` (130/130), `alembic upgrade head` clean (autogenerate detected only the new table, no drift), `tsc --noEmit`/`eslint`/`next build` all clean (`/portal/[token]` compiles as a new route).

## 2026-08-15 — (uncommitted) — Sprint #012 — Tenant Data Isolation Enforcement

Full detail in `docs/DECISIONS.md` ADR-029.

**Backend**
- `app/database/crud.py`: `customers`/`projects`/`quotes`/`activity_log`/`notifications` functions now require (or, for the `create_*` helpers on `quotes`/`activity_log`/`notifications`, accept optional) `tenant_id` and filter/check ownership by it.
- `app/customers/`, `app/projects/`, `app/quotes/`, `app/tenants/`: every route now scopes its query by `current_user.tenant_id`; a cross-tenant id reads as `404`, matching ADR-028's precedent.
- `app/activity/router.py` and `app/notifications/router.py` gained `Depends(get_current_user)` for the first time — previously fully public, now auth-required and tenant-scoped.
- `GET /api/v1/dashboard` (`app/api/v1/core.py`) is now auth-required and returns only the caller's tenant's counts.
- `app/auth/dependencies.py`: new `get_current_user_optional` — lets `POST /api/v1/quote`/`/estimate` stay public (ADR-023) while opportunistically tagging the created quote with the caller's tenant when a valid token is presented.
- `app/tenants/router.py`: `GET /tenants` and `GET /tenants/{id}` now return only the caller's own tenant — previously returned every tenant in the system, a pre-existing cross-tenant leak this sprint closes.
- `app/projects/service.py` and `app/quotes/service.py`: new `CustomerNotFoundError`, raised when a supplied `customer_id` doesn't belong to the caller's own tenant — closes a relationship-level bypass that id-scoping alone didn't cover.
- Migration `a8d91098a01e`: adds a plain index on `tenant_id` for `customers`, `quotes`, `projects`, `activity_log`, and `notifications` (additive-only, no column/nullability change).

**Tests**
- New `tests/test_activity.py` and `tests/test_notifications.py` (no test file existed for either module before).
- Cross-tenant isolation tests added across `tests/test_customers.py`, `tests/test_projects.py`, `tests/test_quotes_api.py`, `tests/test_tenants.py`, `tests/test_activity.py`, `tests/test_notifications.py`, `tests/test_dashboard.py`, `tests/test_invitations.py` — plus a relationship-bypass test each for projects and quotes (an authenticated `customer_id` belonging to a different tenant is rejected with `404`).
- `tests/conftest.py`: new `other_tenant_auth_headers` fixture — signs up a genuinely separate tenant/owner so cross-tenant tests have two real tenants to assert isolation between.
- Fixed a test-only bug (not an app bug): several cleanup helpers deleted a `Tenant` row before the `ActivityLog` rows that now correctly FK-reference it under the tenant's own id, raising a `ForeignKeyViolation` in teardown.
- Full suite: 115/115 passing.

**Verified:** `pytest` (115/115), `tsc --noEmit` (frontend, clean), `eslint` (clean, cached — no frontend files changed), `next build` (clean, cached), clean Alembic `downgrade -1` / `upgrade head` round-trip.

## 2026-08-11 — (uncommitted) — Sprint #007 — Real Quote Persistence, Downloadable Invoices, Real Dashboard Stats

Full detail in `docs/SPRINTS/sprint-007.md`. Not yet committed — pending approval.

**Backend**
- Quotes are persisted for the first time: `app/quotes/service.py` (new) wraps the existing pure `QuoteCalculator`, saves every result to the `quotes` table (empty since Sprint 002), and logs a real `ActivityEvent` server-side. Both `POST /api/v1/quote` and `POST /api/v1/estimate` go through this one seam.
- New `app/quotes/router.py` — `GET /quotes`, `GET /quotes/{id}`, `GET /quotes/{id}/invoice`, all `Depends(get_current_user)` — the **third auth-enforced module** (ADR-023). Deliberately asymmetric: creating a quote (`POST /quote`/`/estimate`) stays public — only *browsing* what's already calculated is gated.
- `POST /api/v1/quote/pdf` **removed** — replaced by `GET /api/v1/quotes/{id}/invoice`, which downloads a real PDF for an already-persisted quote instead of calculating-and-writing-to-disk in one call.
- `app/quotes/pdf.py` rewritten: proper letterhead, a real VAT breakdown table, generated to `io.BytesIO()` (not `quote.pdf` on local disk) and returned as a real HTTP file download.
- `GET /api/v1/dashboard` now computes all four numbers for real (previously hardcoded): `customers`/`projects` are row counts, `quotes_today` counts today's quotes, `revenue` sums `quotes.total` all-time.
- `QuoteRequest` gains an optional `customer_id` — the `quotes` table only supports linking via FK, not a free-text name, so `/quotes/new` gets a customer picker (same UX Sprint 006 added to `/projects/new`). `customer` (free text) stays required for `/estimate`'s sake, but is only ever echoed in the response, never stored, unless linked.
- `app/quotes/generator.py` superseded (no longer imported), left in place per ADR-008.

**Frontend**
- `/quotes` and new `/quotes/[id]` — real list/detail, same pattern as customers/projects; both auth-gated (matching the new `GET /api/v1/quotes/*` requirement). `/quotes/new` itself stays public (matches `POST /quote`), but its "Download Invoice" button only renders when signed in.
- `apps/web/lib/api.ts` — `downloadInvoice()` added: fetches the PDF as a blob and triggers a real browser download (no new dependency).
- `/quotes/new`'s frontend `api.logActivity()` call removed — the backend logs it now, same as customers/projects.

**Tests**
- `tests/test_quotes_api.py` (new, 9 tests) + `tests/test_dashboard.py` (new, 1 test): persistence round trip, `401`/`404` behavior, invoice PDF content-type/disposition/magic-bytes, activity logged, `customer_id` round-trips, old `/quote/pdf` route confirmed gone, dashboard numbers move after creating real records.
- `tests/test_quotes.py`'s existing pure-calculator unit tests untouched — persistence is a layer above the calculator, not inside it.
- Full suite: 50/50 passing against the real local Postgres.

**Verified**
- `pytest` (50/50), `tsc --noEmit`, `eslint .`, `next build` all clean.
- Manually inspected a generated invoice PDF (rendered, not just byte-checked) — letterhead, VAT breakdown table, and totals all correct.
- Real headless-browser walkthrough (Playwright, transient dev tooling): login → create a customer → calculate a quote linked to it → invoice downloads as a real PDF (captured via Playwright's download event, magic bytes verified) → quotes list shows it → detail page shows the linked customer and full breakdown → dashboard's stat cards reflect the new counts/revenue. No console errors. Test data cleaned up afterward, dev server stopped.

## 2026-08-11 — `dc9736e` — Sprint #006 — Projects Module (Job Pipeline)

Full detail in `docs/SPRINTS/sprint-006.md`.

**Scope note:** Sprint 006 originally bundled "AI Quotation Generator v1" with the Projects module. No `OPENAI_API_KEY` is configured anywhere in this project and real LLM calls cost real money per request, so the AI generator was split out and deferred to its own future sprint — this entry covers Projects only.

**Backend**
- New `app/projects/` module: `models.py` (`ProjectStatus` — 7-stage pipeline enum, `ProjectCreate`, `ProjectOut`, `ProjectStatusUpdate`), `service.py` (`ProjectService` — list/get/create/update_status; `create()` logs a real `ActivityEvent`, same pattern Sprint 004 established for customers), `router.py` (4 routes, all `Depends(get_current_user)` — the second auth-enforced module, ADR-022).
- **First update-beyond-create endpoint in the API:** `PATCH /api/v1/projects/{id}/status`. A deliberate, narrow exception to the Customers precedent (list/detail/create only) — a job pipeline is meaningless without a way to move a project between stages.
- Migration `786f58ce4406` adds `status` (`String`, `NOT NULL`, default `"enquiry"`) to `projects` — safe, the table had 0 rows.
- `app/database/crud.py` — `create_project`, `get_project_by_id`, `list_projects`, `update_project_status` added.

**Frontend**
- New `apps/web/types/project.ts`, `apps/web/lib/projects.ts` (status label/Badge-tone mapping).
- `apps/web/lib/api.ts` — `getProjects`, `getProject`, `createProject`, `updateProjectStatus` added.
- `/projects` and `/projects/new` now use real persistence instead of activity-log-only behavior; new `/projects/[id]` detail page with an "Advance to \<next stage\>" control. `/projects/new`'s customer field is now a `<select>` populated from real customers (`api.getCustomers()`), replacing free text — a natural consequence of Sprint 004's CRM existing.

**Tests**
- `tests/test_projects.py` (new, 10 tests): create/list/get round trip, default status, status advance + reflected on GET, invalid status → `422`, `401` on all 4 routes without a token, `404` on an unknown id (GET and PATCH), activity logged on create, `customer_id` round-trips.
- Full suite: 40/40 passing against the real local Postgres.

**Also fixed:** a stray manual smoke-test row (`user_login`/"smoke test"/"x") left in `activity_log` since Sprint 003's very first verification pass, and a genuine gap in `tests/test_customers.py`-style cleanup that this sprint's own test briefly reproduced (a linked test customer's `ActivityEvent` wasn't being deleted) — both cleaned up, `activity_log`'s real baseline is 6 rows, not the 7 this changelog's Sprints 004/005 entries assumed.

**Verified**
- `pytest` (40/40), `tsc --noEmit`, `eslint .`, `next build` all clean.
- Manual smoke test: full pipeline walk (enquiry → ... → complete) via `PATCH .../status`, invalid stage → `422`, no token → `401`.
- Real headless-browser walkthrough (Playwright, transient dev tooling): login → create a customer → create a project linked to it → detail page shows correct name/status/customer/notes → advance to "Quoted" → list reflects the updated stage. No console errors. Test data cleaned up afterward, dev server stopped.

## 2026-08-11 — `6d8d241` — Sprint #005 — Full Material Library + Accurate Slab-Yield Calculator

Full detail in `docs/SPRINTS/sprint-005.md`.

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
