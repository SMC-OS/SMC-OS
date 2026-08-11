# SIMO OS — User Roles & Permissions

**Status (Sprint 006): real login works end-to-end, and two modules (`customers`, `projects`) require it.** `POST /api/v1/auth/login` / `GET /api/v1/auth/me` (`app/auth/`, Sprint 003) are backed by a real, seeded owner account. Sprint 004 wired the frontend to them for the first time — a real `/login` page, token storage, and `/api/v1/customers/*` requiring a valid token (ADR-021). Sprint 006 extended the same requirement to `/api/v1/projects/*` (ADR-022), including its status-update endpoint. Every other route (`/api/v1/quote`, `/api/v1/activity`, `/api/v1/notifications`, etc.) remains public (ADR-020) — enforcement was applied surgically to the modules that needed it, not broadly. This document describes the current state honestly, and the planned model for what's still ahead.

---

## 1. Current state

The frontend now has a real login flow: `apps/web/app/login/page.tsx` calls `POST /api/v1/auth/login`, stores the returned JWT (`apps/web/lib/auth-storage.ts`, localStorage), and `components/auth/AuthProvider.tsx` (a React context mirroring `ThemeProvider`'s shape) tracks whether a valid token is present. `components/shell/UserProfileMenu.tsx`'s **Sign out** is real — it clears the token and redirects to `/login`. Profile and Settings remain `disabled` — nothing new to show/configure for either yet, unrelated to this sprint.

`/customers`, `/customers/new`, `/customers/[id]`, `/projects`, `/projects/new`, and `/projects/[id]` all redirect to `/login` if no valid token is present (a client-side check-on-mount guard, not Next.js middleware/SSR-level — proportionate to an internal tool with one seeded user today). `lib/api.ts`'s `request()` attaches the stored token to every backend call automatically and clears it on a `401` (treating that as "session expired," not just this one call failing).

`/settings` still shows a "Coming soon" state — there's a session now, but nothing to configure with it yet.

**Still true:** anyone with network access can call `/api/v1/quote`, `/api/v1/activity`, `/api/v1/notifications`, `/api/v1/process`, `/api/v1/dashboard`, etc. without a token — only `/api/v1/customers/*` (ADR-021) and `/api/v1/projects/*` (ADR-022) require one.

---

## 2. Planned model (partially built)

Per `docs/ROADMAP.md`, Sprint 003 delivered single-tenant JWT *machinery*; Sprints 004 and 006 are where it's actually enforced, on the two modules (`customers`, `projects`) that introduced real business data. Future business-data modules (quote persistence, materials) will face the same decision on a case-by-case basis, not an automatic blanket rule. Role-based permissions arrive in **v1.0, Sprint 015** (staff management + RBAC), once multi-tenancy (Sprint 012) exists.

Based on the business context this system is being built for (a stone/construction company), the anticipated roles are:

| Anticipated role | Anticipated scope | Status |
|---|---|---|
| Owner | Full access — the role the current placeholder user assumes | Not implemented |
| Staff / employee | Scoped access to their assigned projects, quotes, and schedule | Not implemented |
| Customer (client portal) | Read-only access to their own project/quote/invoice status | Not implemented — client portal itself is a v1.0 item (Sprint 013) |

**These are anticipated, not designed.** No permission matrix, no database representation, and no enforcement logic exists yet. Treat this table as an input to Sprint 003/015 design work, not as a specification of something already built.

---

## 3. What to check before assuming auth is enforced

If you're reading this because you're about to build something that depends on "the current user" or "permissions": `get_current_user` (`app/auth/dependencies.py`) is attached to `/api/v1/auth/me`, all of `/api/v1/customers/*`, and all of `/api/v1/projects/*` — nothing else. There are still no permissions/roles, only "has a valid token or doesn't." Check `docs/API_SPEC.md`'s route table's "Auth required?" column and `docs/DECISIONS.md` ADR-020/ADR-021/ADR-022 — if a route you care about still says "No", nothing has changed since this document was written.
