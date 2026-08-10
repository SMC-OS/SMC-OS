# SIMO OS — User Roles & Permissions

**Status (Sprint 003): login/token issuance exists in the backend; no route enforces it yet, and the frontend still shows a hardcoded user.** `app/database/models.py`'s `User` table now has a `password_hash` column, and `POST /api/v1/auth/login` / `GET /api/v1/auth/me` are real, working endpoints (`app/auth/`) — but every other route in `docs/API_SPEC.md` remains completely public (ADR-020, a deliberate scope decision, not an oversight). The frontend has not been wired to call login — `UserProfileMenu` and `/settings` are unchanged from Sprint 001. This document describes the current state honestly, and the planned model for when enforcement and the frontend login flow actually get built.

---

## 1. Current state

The frontend still shows a single hardcoded user in `components/shell/UserProfileMenu.tsx`:

```ts
const CURRENT_USER = { name: "Simo", role: "Owner" };
```

This is display-only — it is not read from a login session, not validated against anything, and not connected to the backend's new `/api/v1/auth/*` endpoints (that wiring is future work). The menu's Profile, Settings, and Sign out items are still rendered `disabled`.

The `/settings` page still shows a "Coming soon" state rather than a working settings form.

The backend side is real: `POST /api/v1/auth/login` checks a hashed password in the `users` table and issues a signed JWT; `GET /api/v1/auth/me` validates one. One owner account is seeded on startup from `.env` (`app/auth/seed.py`). But **no other route checks who's calling it** — anyone with network access can still call `/api/v1/quote`, `/api/v1/activity`, `/api/v1/notifications`, etc. without a token (ADR-020).

---

## 2. Planned model (partially built)

Per `docs/ROADMAP.md`, Sprint 003 delivered single-tenant JWT *machinery*. What's still ahead: wiring the frontend (`UserProfileMenu`, `/settings`) to actually call `/api/v1/auth/login`, and applying `Depends(get_current_user)` to routes once a later sprint has real per-user data worth protecting. Role-based permissions arrive in **v1.0, Sprint 015** (staff management + RBAC), once multi-tenancy (Sprint 012) exists.

Based on the business context this system is being built for (a stone/construction company), the anticipated roles are:

| Anticipated role | Anticipated scope | Status |
|---|---|---|
| Owner | Full access — the role the current placeholder user assumes | Not implemented |
| Staff / employee | Scoped access to their assigned projects, quotes, and schedule | Not implemented |
| Customer (client portal) | Read-only access to their own project/quote/invoice status | Not implemented — client portal itself is a v1.0 item (Sprint 013) |

**These are anticipated, not designed.** No permission matrix, no database representation, and no enforcement logic exists yet. Treat this table as an input to Sprint 003/015 design work, not as a specification of something already built.

---

## 3. What to check before assuming auth is enforced

If you're reading this because you're about to build something that depends on "the current user" or "permissions": `get_current_user` (`app/auth/dependencies.py`) exists and works, but it is not attached to any route outside `/api/v1/auth/me`. There are still no permissions/roles enforcement anywhere. Check `docs/API_SPEC.md`'s route table's "Auth required?" column and `docs/DECISIONS.md` ADR-020 — if a route you care about still says "No", nothing has changed since this document was written.
