# SIMO OS — User Roles & Permissions

**Status: no authentication, user accounts, or role/permission system exists in the codebase today.** There is no `User` model (`app/database/models.py` is empty), no login endpoint, no session or token handling, and no authorisation check on any route — every endpoint listed in `docs/API_SPEC.md` is completely public. This document describes the current placeholder state honestly, and the planned model for when auth is actually built. Nothing below "Planned" should be treated as working.

---

## 1. Current state

The frontend shows a single hardcoded user in `components/shell/UserProfileMenu.tsx`:

```ts
const CURRENT_USER = { name: "Simo", role: "Owner" };
```

This is display-only — it is not read from a login session (none exists), not validated against anything, and not connected to any backend concept of a user. The menu's Profile, Settings, and Sign out items are rendered `disabled`, each with a tooltip explaining that authentication isn't implemented yet.

The `/settings` page similarly shows an honest "Coming in Sprint 003" state rather than a working settings form, because there is no account to configure.

No backend route checks who's calling it. Anyone with network access to the API can call any endpoint, including creating quotes, activity events, and notifications.

---

## 2. Planned model (not yet built)

Per `docs/ROADMAP.md`, authentication arrives in **Sprint 003** (single-tenant JWT auth, unblocking the disabled `UserProfileMenu` items and a real `/settings` page) and role-based permissions arrive in **v1.0, Sprint 015** (staff management + RBAC), once multi-tenancy (Sprint 012) exists.

Based on the business context this system is being built for (a stone/construction company), the anticipated roles are:

| Anticipated role | Anticipated scope | Status |
|---|---|---|
| Owner | Full access — the role the current placeholder user assumes | Not implemented |
| Staff / employee | Scoped access to their assigned projects, quotes, and schedule | Not implemented |
| Customer (client portal) | Read-only access to their own project/quote/invoice status | Not implemented — client portal itself is a v1.0 item (Sprint 013) |

**These are anticipated, not designed.** No permission matrix, no database representation, and no enforcement logic exists yet. Treat this table as an input to Sprint 003/015 design work, not as a specification of something already built.

---

## 3. What to check before assuming auth exists

If you're reading this because you're about to build something that depends on "the current user" or "permissions": there is no current user and there are no permissions. Check `app/core/config.py` and `app/database/models.py` — if they're still empty, none of this has changed since this document was written.
