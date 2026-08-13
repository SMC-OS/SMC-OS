# SIMO OS — User Roles & Permissions

**Status (Sprint 009): real login + signup work end-to-end, every user belongs to a tenant, and four modules (`customers`, `projects`, `quotes`-browsing, `tenants`) require a valid token.** `POST /api/v1/auth/login`, `POST /api/v1/auth/signup`, `GET /api/v1/auth/me` (`app/auth/`, Sprint 003 + Sprint 009) are backed by real accounts — no longer a single seeded owner only. Sprint 004 wired the frontend to auth for the first time (`/login`, token storage, `/api/v1/customers/*` requiring a valid token, ADR-021). Sprint 006 extended the same requirement to `/api/v1/projects/*` (ADR-022). Sprint 007 extended it to `/api/v1/quotes/*` (ADR-023) — but **only browsing**. Sprint 008 added `/api/v1/tenants/*`, reusing the same gate. **Sprint 009 (ADR-026) is the one that makes "which tenant" a real, enforced fact about every user** — but still doesn't use that fact to isolate any business data (that's Sprint 012, unstarted). Every other route remains public (ADR-020) — enforcement was applied surgically to the modules/actions that needed it, not broadly. This document describes the current state honestly, and the planned model for what's still ahead.

---

## 1. Current state

The frontend has a real signup + login flow. `apps/web/app/signup/page.tsx` (Sprint 009) calls `POST /api/v1/auth/signup` — company name, owner name, email, password — creating a brand-new tenant and its first (Owner) user in one call, and signs the new owner straight in. `apps/web/app/login/page.tsx` calls `POST /api/v1/auth/login`. Both store the returned JWT (`apps/web/lib/auth-storage.ts`, localStorage). `components/auth/AuthProvider.tsx` (a React context mirroring `ThemeProvider`'s shape) tracks whether a valid token is present and, since Sprint 009, also resolves and holds the signed-in user's company name (`tenantName`) — fetched via `GET /api/v1/auth/me` on mount when a stored token exists, so a page refresh doesn't lose it. `components/shell/UserProfileMenu.tsx`'s **Sign out** is real — it clears the token and redirects to `/login`. Profile and Settings remain `disabled` — nothing new to show/configure for either yet.

`/customers`, `/customers/new`, `/customers/[id]`, `/projects`, `/projects/new`, `/projects/[id]`, `/quotes`, and `/quotes/[id]` all redirect to `/login` if no valid token is present (a client-side check-on-mount guard, not Next.js middleware/SSR-level). `/quotes/new` is the one exception — it works signed out (matches `POST /quote` staying public). `lib/api.ts`'s `request()` attaches the stored token to every backend call automatically and clears it on a `401` (treating that as "session expired," not just this one call failing) — this is also what makes an old-shape (pre-Sprint-009) token self-heal: the first authenticated call after upgrading gets a `401`, the stored token is cleared, and the user is prompted to sign in again, no manual intervention needed.

`/settings` still shows a "Coming soon" state.

**Still true:** anyone with network access can call `POST /api/v1/quote`, `POST /api/v1/estimate`, `/api/v1/activity`, `/api/v1/notifications`, `/api/v1/process`, `/api/v1/dashboard`, etc. without a token. **Also still true, and worth stating plainly:** a valid token now always carries a real `tenant_id` (ADR-026), but **no protected route filters anything by it yet** — a Staff or Owner user from Tenant A, if a second tenant existed with data in it, could currently list/read/create Tenant B's customers/projects/quotes with a valid token, because none of those modules' queries are tenant-scoped. This is not a Sprint 009 bug — it's the explicitly-deferred scope of Sprint 012, called out here so nobody mistakes "every user has a tenant" for "tenants are isolated from each other."

---

## 2. Planned model (partially built)

Per the approved SaaS roadmap, Sprint 003 delivered single-tenant JWT *machinery*; Sprints 004, 006, 007, and 008 enforced "has a valid token" on the business-data/schema modules that introduced something worth protecting. **Sprint 009 made the token itself tenant-aware** (every user belongs to exactly one tenant, `NOT NULL` in the database). Sprint 010 is where real roles/permissions beyond "Owner vs. nothing" land; Sprint 011 adds invitations (so a tenant can have more than one user); Sprint 012 is where tenant isolation is actually enforced on business data.

Based on the business context this system is being built for (a stone/construction company), the anticipated roles are:

| Anticipated role | Anticipated scope | Status |
|---|---|---|
| Owner | Full access within their tenant — the role every signup's first user gets (`role="Owner"`, Sprint 009) | **Partially implemented** — the role value exists and is set correctly, but nothing yet checks it (no route distinguishes an Owner from a Staff user's permissions) |
| Staff / employee | Scoped access to their assigned projects, quotes, and schedule, within their tenant | Not implemented — no invitation flow exists yet to create a second user in a tenant (Sprint 011) |
| Customer (client portal) | Read-only access to their own project/quote/invoice status | Not implemented — client portal is a later roadmap item |

**These are still anticipated, not fully designed or enforced.** `role` is a real, populated column as of Sprint 009 (every signup sets it), but no permission matrix or enforcement logic reads it yet — that's Sprint 010. Treat this table as an input to that sprint's design work, not as a specification of something already built.

---

## 3. What to check before assuming auth is enforced

If you're reading this because you're about to build something that depends on "the current user," "the current tenant," or "permissions": `get_current_user` (`app/auth/dependencies.py`) is attached to `/api/v1/auth/me`, all of `/api/v1/customers/*`, all of `/api/v1/projects/*`, `/api/v1/quotes/*` (the browsing routes), and all of `/api/v1/tenants/*` — nothing else. It guarantees "a valid token, and that token's user has a real `tenant_id`" (Sprint 009) — it does **not** guarantee any query is filtered by that tenant (Sprint 012), and there are still no permission checks beyond "has a valid token or doesn't" (Sprint 010). `current_user.tenant_id` (the DB row, not the JWT claim — see ADR-026) is the value any future tenant-scoping code should read. Check `docs/API_SPEC.md`'s route table's "Auth required?" column and `docs/DECISIONS.md` ADR-020/ADR-021/ADR-022/ADR-023/ADR-025/ADR-026 — if a route or guarantee you care about isn't listed there, nothing has changed since this document was written.
