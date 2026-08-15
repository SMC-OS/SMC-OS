# Sprint 013 — Read-Only Client Portal

**Status:** ✅ Done. Implemented and verified against the live local PostgreSQL 16 instance; not yet committed to git.

## Objective

`docs/ROADMAP.md`'s v1.0 table lists Sprint 013 as "Client Portal (project tracking, documents, messaging)" — three distinct capabilities bundled into one line. Inspection confirmed none of the three existed yet (no document storage/upload, no messaging model, no portal auth of any kind). `docs/USER_ROLES.md` had already flagged the core architectural question: a client portal "would likely need a different auth model entirely (not a `users` row)."

Asked to choose a scope, the explicit decision was **tracking only**: a customer can view the status of their own project(s) and quote(s) via a link, with no account, no login, no `users` row, no JWT — matching every prior sprint's one-capability-per-sprint, machinery-first cadence (Sprint 008 = tenants schema only, Sprint 010 = roles machinery only, Sprint 011 = invitations only).

**Deliberately out of scope, by design, not oversight:** document storage/upload (beyond the one specific, already-existing invoice PDF — see below); messaging/chat; any write capability for the customer; a customer login/account of any kind; a frontend list/revoke management UI (the `GET`/`DELETE` API routes ship and are tested, but nothing in the UI consumes them yet — same "ship inert-but-tested machinery" precedent `require_role` had between Sprint 010 and Sprint 011).

**Downloadable invoice, added after initial scoping:** the strict scope confirmed for this sprint explicitly named "downloadable invoice" as in-scope alongside project status and quote info — narrower than, and not to be confused with, the broader "documents" capability deliberately deferred above. `GET /api/v1/portal-links/token/{token}/invoice/{quote_id}` reuses the existing `app/quotes/pdf.py` PDF generator (no new PDF logic written), gated to the token's own `customer_id`, not just its tenant.

## Scope delivered

**Backend**
- New `app/portal/` module (`models.py`/`service.py`/`router.py`), following the exact file shape every business-data module uses (`app/customers/`, `app/invitations/`, etc.).
- Token mechanism reuses `app/invitations/service.py`'s exactly: `secrets.token_urlsafe(32)`, SHA-256-hashed before persistence (`token_hash`, unique), the raw token returned only once. **The one deliberate departure:** a portal link is reusable, not single-use — `PortalLink.status` is `"active"|"revoked"` only, no `"accepted"` state, no accept step. `PortalService.derive_status()` derives `"expired"` at read time from `expires_at`, same convention as `InvitationService.derive_status()`.
- `app/database/models.py` — new `PortalLink` table: `id`, `tenant_id` (NOT NULL FK), `customer_id` (NOT NULL FK), `created_by_user_id` (NOT NULL FK → users), `token_hash` (unique), `status`, `expires_at`, `created_at`.
- `app/database/crud.py` — `create_portal_link`, `get_portal_link_by_id`, `get_portal_link_by_token_hash`, `list_portal_links(tenant_id, customer_id=None)`, `update_portal_link_status`, `list_projects_by_customer(tenant_id, customer_id)`, `list_quotes_by_customer(tenant_id, customer_id)` — the last two filter by both `tenant_id` and `customer_id`, defense in depth.
- `app/portal/router.py` — `POST /api/v1/portal-links` (any authenticated tenant user — deliberately **not** `require_role(OWNER)`, unlike inviting a teammate; sharing a project link is routine Staff work, not a tenant-control decision), `GET /api/v1/portal-links` (tenant-scoped list, optional `?customer_id=` filter), `DELETE /api/v1/portal-links/{id}` (tenant-scoped revoke, cross-tenant → `404`), public `GET /api/v1/portal-links/token/{token}`, and public `GET /api/v1/portal-links/token/{token}/invoice/{quote_id}` (PDF download, reuses `app/quotes/pdf.py::PDFGenerator`, gated to the token's own `customer_id`).
- **Relationship-linkage bypass closed at creation time, not discovered later:** `PortalService.create_link()` validates the given `customer_id` resolves under the caller's own tenant (`crud.get_customer_by_id`, already tenant-scoped since Sprint 012) before creating a row, raising `CustomerNotFoundError` → `404` — the exact same check ADR-029 added to `app/projects/service.py`/`app/quotes/service.py`, reused rather than reinvented.
- **Public response is minimal, no PII beyond what's needed:** `PortalPublicOut` returns `tenant_name`, `customer_name` (name only, never email/phone), `status`, `expires_at`, and project/quote lists — `PortalProjectOut` excludes `notes` (may hold internal staff remarks), `PortalQuoteOut` excludes `customer_id`. A revoked/expired token still returns `200` with `status` set and empty lists — same "always 200, the shape carries the state" convention `InvitationPublicOut` uses. Only a genuinely unknown token hash returns `404`.
- `app/core/config.py` — `portal_link_expire_days: int = 90`, deliberately much longer than `invitation_expire_days`'s 7 (an invitation is a one-time "join now" prompt; a portal link should outlive roughly a job's duration).
- `app/api/v1/__init__.py` — mounts the new router alongside the existing 6.

**Backend — tenant isolation, day one, not deferred**
- Every list/get/revoke query filters by `tenant_id` (ADR-029 convention).
- The public token route resolves `tenant_id`/`customer_id` from the token row itself, never from caller input — a token minted under tenant A structurally cannot surface tenant B's data, confirmed by `test_portal_cross_tenant_isolation`.

**Migration**
- `alembic/versions/880e12adf384_add_portal_links_table.py` — one additive migration, `portal_links` table with 3 explicitly-named FK constraints, symmetric `upgrade()`/`downgrade()`. Generated via `alembic revision --autogenerate` against the already-updated models — autogenerate detected exactly this one new table and nothing else, confirming no other model/migration drift existed.

**Frontend**
- New public page `apps/web/app/portal/[token]/page.tsx` — structurally the fetch/loading/error/status-conditional shell from `apps/web/app/invite/[token]/page.tsx`, with the entire account-creation form half removed (no form, no `acceptInvite`-equivalent, no redirect — just a rendered project/quote list). Confirmed the root layout has no pathname-based shell-bypass mechanism (`/login` and `/invite/[token]` already render inside the full `AppShell` today); the portal page follows that same existing precedent rather than introducing new shell-bypass logic. Each quote row has an "Invoice" download button, wired to `api.downloadPortalInvoice()` (same blob-download pattern as the existing authenticated `downloadInvoice`, minus the bearer token).
- `apps/web/app/customers/[id]/page.tsx` — new "Client portal" card: generate a link, copy it (`navigator.clipboard.writeText`), modeled directly on `apps/web/app/settings/page.tsx`'s invitation-creation UI. No separate list/revoke UI ships this sprint.
- New `apps/web/types/portal.ts` (mirrors `app/portal/models.py`); `apps/web/lib/api.ts` gains `createPortalLink`, `getPortalLinks`, `revokePortalLink` (authenticated), `getPortalByToken`, `downloadPortalInvoice` (public).

**Docs**
- `docs/DECISIONS.md` — new ADR-030 (token design, customer-scoped-not-project-scoped rationale, non-Owner-gated-creation rationale, minimal-PII response rationale, no-`users`-row/JWT rationale).
- `docs/API_SPEC.md`, `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md` — updated route-by-route, module table, folder structure, frontend route table.
- `docs/ROADMAP.md` — **not** touched, per the same explicit instruction and reasoning `sprint-012.md` already recorded: its Sprint 008–016 table is a stale, pre-SaaS-replan draft; reconciling it remains a separate, out-of-scope decision.

## Design decisions (with rationale)

**Token scope: per-customer, not per-project.** A `portal_links` row grants access to *all* of one `customer_id`'s projects and quotes, not one specific job. A customer with two concurrent jobs (e.g. a kitchen and a bathroom) shouldn't need two links, and it keeps the generation UX to one button with no project picker. No `project_id` column was added — no unused nullable column, unlike `Invitation.role`, which ADR-028 kept for a real, stated future-use reason.

**Creation is not Owner-gated.** Contrast `POST /api/v1/invitations` (`require_role(OWNER)`, ADR-028): inviting a teammate is a materially bigger, tenant-control decision. Sharing a project link with a customer is routine Staff work — gating it to Owner-only would be an unjustified restriction on normal day-to-day use.

**Reusable, not single-use — the one real departure from the invitation precedent.** An invitation is consumed once (accept → create a user → done). A portal link is meant to be opened by the customer repeatedly, for as long as the job is active. Modeling it as single-use would mean re-issuing a new link every time the customer wants to check status, which defeats the point.

## Test-suite coverage

`tests/test_portal.py`, 19 tests, modeled on `tests/test_invitations.py` and Sprint 012's cross-tenant suite: creation (success, unknown customer → `404`, cross-tenant customer → `404`), auth requirement on all three management routes, tenant-scoped listing, revoke (success, unknown → `404`, cross-tenant → `404`), public token view (success, unknown token → `404`), **reusability** (`test_portal_link_is_reusable` — the same active token fetched twice, both succeed, no state change), revoked/expired reads (status set, empty data, no leak), two dedicated isolation tests (`test_portal_returns_only_that_customers_projects_and_quotes`, `test_portal_cross_tenant_isolation`), and 4 invoice-download tests (success — real PDF bytes; unknown `quote_id` → `404`; a quote belonging to a *different* customer in the same tenant → `404`; a revoked link's quote → `404`).

## Audit results

| Check | Result |
|---|---|
| `pytest` (134 tests: 115 from Sprint 012 + 19 new `test_portal.py`) | ✅ 134 passed |
| Portal invoice download: valid active link + own customer's quote → real PDF | ✅ Confirmed (`test_download_portal_invoice_success`) |
| Portal invoice download: unknown quote, a different customer's quote, or a revoked link → `404` | ✅ Confirmed (3 tests) |
| Portal link creation scoped to caller's tenant; unknown/cross-tenant `customer_id` → `404`, nothing persisted | ✅ Confirmed |
| List/revoke tenant-scoped; cross-tenant `id` → `404` | ✅ Confirmed |
| Public token view returns only that customer's own projects/quotes, never another customer's or another tenant's | ✅ Confirmed (`test_portal_returns_only_that_customers_projects_and_quotes`, `test_portal_cross_tenant_isolation`) |
| Revoked/expired link reads as such, `200`, empty data — no leak, no `404` for a known-but-dead token | ✅ Confirmed |
| Active link is reusable — fetched twice, no state change | ✅ Confirmed (`test_portal_link_is_reusable`) |
| `alembic upgrade head` (`880e12adf384`) — autogenerate detected only the new table | ✅ Clean, no drift |
| `alembic check` | ✅ No new upgrade operations detected |
| `eslint .` | ✅ 0 errors, 0 warnings |
| `tsc --noEmit` | ✅ Clean |
| `next build` | ✅ All 15 routes compile, including new `/portal/[token]` |

## Follow-up items raised, not part of Sprint 013 scope

- Documents (upload/storage/serving) and messaging remain unstarted — the two capabilities `docs/ROADMAP.md`'s Sprint 013 line bundled in but this sprint deliberately excluded.
- No frontend UI lists or revokes existing portal links yet (the API routes exist and are tested) — a natural next increment once there's a concrete need.
- `docs/ROADMAP.md`'s Sprint 008–016 table remains the stale, pre-SaaS-replan draft flagged since `sprint-008.md` — reconciling it is still a separate, larger documentation decision, explicitly not done here.
- Sprint 014 is not started.
