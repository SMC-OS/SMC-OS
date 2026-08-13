# Sprint 009 — Tenant-Aware Authentication

**Status:** ✅ Done. Implemented and verified against the live local PostgreSQL 16 instance; not yet committed to git.

## Objective

Second sprint of the SaaS-transformation phase (Phase 2). Make signup and login genuinely tenant-scoped: every user belongs to exactly one tenant (`users.tenant_id` becomes `NOT NULL` — the first of the 7 Sprint-002 columns to actually enforce anything), and the JWT itself carries `tenant_id`. Adds `POST /api/v1/auth/signup`, the first real way to create a new company workspace without touching the database by hand.

**Explicitly out of scope, by design:** roles/permissions beyond "every signup gets an Owner" (Sprint 010), invitations / multiple users per tenant (Sprint 011), and — critically — tenant data isolation. No query in `customers`, `projects`, `quotes`, `materials`, `activity`, `notifications`, or `dashboard` gained a tenant filter. A user now definitely has a tenant; nothing yet stops them from reading another tenant's business data. That's Sprint 012, still not started.

## Scope delivered

**Backend**
- `app/auth/security.py` — `create_access_token(subject, tenant_id)`; `decode_access_token()` now returns the full payload dict, not just `sub`.
- `app/auth/dependencies.py` — `get_current_user` rejects any token missing a well-formed `tenant_id` claim (401) — every pre-Sprint-009 token, a clean cutover per ADR-012's precedent. The DB row remains authoritative; the claim is checked for shape only, never substituted for `user.tenant_id`.
- `app/auth/models.py` — new `SignupRequest`; `UserOut` gains `tenant_id`/`tenant_name` (built by hand via `AuthService.build_user_out()`, not automatic `from_attributes` — `tenant_name` isn't a `users` column).
- `app/auth/service.py` — `create_user()` requires `tenant_id`; new `signup()` creates a `Tenant` (reusing `app.tenants.service.tenant_service`, no duplicated slugify logic) + first `User` (`role="Owner"`); new `EmailAlreadyRegisteredError`, checked before any row is written so a duplicate signup never orphans a tenant.
- `app/auth/router.py` — new `POST /auth/signup` (201, catches `EmailAlreadyRegisteredError` → 409); `login`/`me` now build tenant-aware responses via `build_user_out()`.
- `app/auth/seed.py` — the seeded owner is now created via `AuthService.signup()` (the same path a real company uses), getting a real "Default Workspace" tenant instead of bespoke logic.
- `app/database/crud.py` — `create_user()` requires `tenant_id`.
- `app/database/models.py` — `User.tenant_id` is `Mapped[uuid.UUID]` (no longer optional), matching the new `NOT NULL` constraint.
- New Alembic revision `c28dd4348080` — backfills any existing `NULL` `users.tenant_id` (the pre-Sprint-009 seeded owner) to a fresh "Default Workspace" tenant, then adds the `NOT NULL` constraint. No-op on a fresh database.

**Frontend**
- `apps/web/types/auth.ts` — `AuthUser` gains `tenant_id`/`tenant_name`; new `SignupRequest` type.
- `apps/web/lib/api.ts` — new `api.signup()`, `api.getMe()`.
- `apps/web/components/auth/AuthProvider.tsx` — new `tenantName` state (set on login/signup, hydrated via `/auth/me` on mount when a token exists) and `signup()` method.
- New `apps/web/app/signup/page.tsx` — company name, owner name, email, password; signs the new owner in and redirects to `/customers` on success; a 409 shows "An account with that email already exists."
- `apps/web/app/login/page.tsx` — reciprocal link to `/signup`.

## Backfill, stated plainly

The pre-existing seeded owner account (`owner@simo-os.local`, created in earlier sprints before `tenants` existed) had `tenant_id = NULL`. The migration assigned it to a brand-new "Default Workspace" tenant automatically — confirmed via direct `psql` query before/after. No manual data fix was needed, and the account's login/password were untouched.

## Auth posture, stated plainly

A **JWT shape change, clean cutover, not backwards-compatible.** Any token issued before this sprint lacks the `tenant_id` claim and is rejected with a `401` — the same "old shape just stops working" precedent as ADR-012's `/api/v1` cutover. In practice this self-heals on the frontend: `lib/api.ts`'s `request()` already clears a token on any `401`, so a stale pre-Sprint-009 session just prompts a fresh sign-in.

## Audit results

| Check | Result |
|---|---|
| `pytest` (69 tests: 68 from Sprint 008 + prior work, 1 net-new... see note) | ✅ 69 passed |
| `alembic upgrade head` → `downgrade -1` → `upgrade head` | ✅ Clean round-trip |
| Existing seeded owner backfilled to a real tenant, login still works | ✅ Confirmed via `psql` + live smoke test |
| `POST /api/v1/auth/signup` creates tenant + owner, returns a usable token | ✅ Confirmed via tests + live smoke test |
| Duplicate-email signup returns `409`, no orphaned tenant | ✅ Confirmed |
| `GET /api/v1/auth/me` returns `tenant_id`/`tenant_name` | ✅ Confirmed |
| Token missing `tenant_id` claim rejected (401) | ✅ Confirmed via a hand-crafted old-shape JWT in `test_token_missing_tenant_id_is_rejected` |
| Existing auth-enforced routes (`customers`, `tenants`) still work with new tokens | ✅ Confirmed via live smoke test |
| No existing route's behavior changed otherwise | ✅ Full pre-existing suite passes unchanged |
| `eslint .` | ✅ 0 errors, 0 warnings |
| `next build` | ✅ 14 routes compile (13 + new `/signup`) |

**Note on test count:** `tests/test_auth.py` went from 6 to 11 tests (5 new: signup success, duplicate-email 409, old-shape-token rejection, `/me` tenant fields, login tenant fields folded into the existing success test) — combined with Sprint 008's `test_tenants.py` (7 tests), the suite is now 69 total, up from 58 pre-Sprint-008.

## Follow-up items raised, not part of Sprint 009 scope

- Sprint 010 (teams, roles & permissions) is next — `role` is populated correctly (`"Owner"` on every signup) but nothing checks it yet.
- Sprint 011 (invitations) — right now a tenant can only ever have the one Owner created at signup; there's no way to add a second user to an existing tenant.
- Sprint 012 (tenant isolation enforcement) — still the big one. Flagged explicitly in `docs/USER_ROLES.md` §1 so nobody mistakes "every user has a tenant" for "tenants can't see each other's data."
- The two pre-existing, unrelated documentation gaps noted in `sprint-008.md` (missing AI-draft API docs, `count_quotes_today`'s timezone comparison) remain unfixed — still out of scope for a tenancy sprint.
