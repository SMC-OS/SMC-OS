# Sprint 015 — Team Management (View Team, Deactivate a Teammate)

**Status:** ✅ Done. Implemented and verified against the real backend test suite, the frontend build/lint/typecheck, `alembic check` (including an explicit `upgrade`/`downgrade`/`upgrade` round-trip), and a manual smoke test against the real running app (uvicorn + local PostgreSQL 16). Not yet committed as of this writing — per explicit user instruction, nothing in this build phase is committed until the whole plan is reviewed.

## Objective

`docs/USER_ROLES.md` names an open gap explicitly: "the permission *primitive* is real and now enforced in one place; the permission *matrix* still isn't... Deciding which *other* routes should eventually require `OWNER` specifically (tenant settings? billing? removing a teammate?) remains explicitly deferred." Sprint 015 answers "removing a teammate": an Owner can now view their tenant's team and deactivate a Staff member's access.

`docs/ROADMAP.md`'s v1.0 table lists Sprint 015's literal line as "Staff management + RBAC; Supplier database + purchasing workflow." That line is stale — RBAC machinery (`UserRole`, `require_role()`) shipped in Sprint 010, and its first real attachment point (staff invitations) shipped in Sprint 011, both four sprint-numbers ahead of where the roadmap places them. Nothing in this sprint touches the roadmap's other Sprint 015 line item (supplier database + purchasing workflow) — that remains entirely unaddressed and unscheduled. `docs/ROADMAP.md` itself is **not touched** by this sprint, same precedent as Sprints 012–014: reconciling the stale Sprint 008–016 table stays a separate, out-of-scope documentation decision.

## Scope delivered

**Backend**
- Migration `dae9516f388b`: `users.is_active BOOLEAN NOT NULL DEFAULT true` (additive-only).
- `app/database/crud.py`: `list_users_by_tenant(db, tenant_id)`, `update_user_active(db, user_id, is_active)`.
- New module `app/users/` (`models.py`, `service.py`, `router.py`):
  - `service.py`: `list_users(db, tenant_id)`; `deactivate_user(db, tenant_id, user_id, acting_user_id)`, raising `CannotDeactivateSelfError` (409) before any lookup if `user_id == acting_user_id`, then `UserNotFoundError` (404) for an unknown or cross-tenant id — deliberately the same error for both, so a cross-tenant lookup can't confirm another tenant's user exists.
  - `router.py`: `GET /api/v1/users` (list team) and `POST /api/v1/users/{id}/deactivate`, both `require_role(UserRole.OWNER)`-gated, mounted in `app/api/v1/__init__.py`.
  - Deactivation logs an `ActivityEvent` (new `ActivityType.TEAM_MEMBER_DEACTIVATED`, `app/activity/models.py`), title "Team member deactivated", description = the deactivated teammate's name — matches the log-on-consequential-action convention every other module follows.
- Soft-deactivation, not row deletion: `Invitation.invited_by_user_id` and `PortalLink.created_by_user_id` are both `NOT NULL` FKs to `users.id`, so a hard delete would break those historical rows. See ADR-031.
- Self-deactivation blocked at the service layer (409) — a direct API call is equally blocked, not just the UI. No separate "last owner" guard: signup always creates exactly one Owner and invitations only ever create Staff, so no code path to a second Owner exists today.
- A deactivated teammate's portal links deliberately keep working — no cascade-revoke. Confirmed by a dedicated test and by the manual smoke test.
- `app/auth/dependencies.py`: `get_current_user` now also rejects a deactivated user's token (401, same generic "Could not validate credentials" message as an invalid token) — costs no extra query, since the user row is already fetched on every call.

**Frontend**
- `apps/web/app/settings/page.tsx` (already had real content since Sprint 011 — not a placeholder) gains a "Team" card, placed first, above the existing "Invite a teammate" card: lists teammates with name/email, a role `Badge`, an active/inactive status `Badge`, and a "Deactivate" button shown only on active rows other than the caller's own.
- `components/auth/AuthProvider.tsx` gains `userId` (the signed-in user's own id), set in the mount effect, `login()`, `signup()`, and `acceptInvite()`, and cleared on `logout()` — used to hide the self-deactivate action client-side; the server enforces the real rule (`CannotDeactivateSelfError`) regardless of what the UI shows.
- New `apps/web/types/user.ts` (`TeamMemberOut`, mirrors `app/users/models.py`). `apps/web/lib/api.ts` gains `getUsers()`/`deactivateUser(id)`.
- The team list's render condition deliberately does **not** gate on the error state (`{teamMembers && teamMembers.length > 0 && (...)}`, no `!teamError` in the guard) — a lesson carried forward from Sprint 014's final review, which caught the opposite bug there (a stale error hiding a subsequent successful load).

**Docs**
- `docs/DECISIONS.md` — new ADR-031: soft-deactivation over hard-delete (and why — the two `NOT NULL` FKs), the self-deactivation guard and why there's no separate last-owner case, the no-cascade-to-portal-links decision, and `get_current_user`'s new second rejection path.
- `docs/USER_ROLES.md` — the permission-matrix paragraph updated to note this sprint resolves the "removing a teammate?" example specifically; the other named examples (tenant settings, billing) remain open, unchanged framing.
- `docs/SYSTEM_ARCHITECTURE.md` — `app/users/` added to the backend module folder-tree listing and the module table; `/settings`'s new Team section noted in the frontend route table.
- `docs/API_SPEC.md` — new "User management routes" section and two new rows in the route summary table, matching the existing table's columns.
- `docs/ROADMAP.md` — **not touched**, same precedent as Sprints 012–014.

## Test-suite coverage

9 new tests in `tests/test_users.py`:
- `test_list_users_returns_owner_and_staff` — an Owner listing the team sees both the Owner and an accepted Staff user, each with `is_active: true`.
- `test_list_users_requires_owner_role` — a Staff user calling `GET /api/v1/users` gets 403.
- `test_deactivate_user_flips_is_active_and_logs_activity` — deactivating a Staff user returns `is_active: false`, and a `team_member_deactivated` activity event with the correct title/description appears.
- `test_deactivate_activity_not_visible_to_other_tenant` — that same activity event is invisible to a second tenant's activity feed (ADR-029 isolation convention).
- `test_deactivate_self_returns_409` — an Owner attempting to deactivate themselves gets 409.
- `test_deactivate_unknown_user_returns_404` — deactivating a random unknown user id returns 404.
- `test_deactivate_cross_tenant_user_returns_404` — deactivating a real user belonging to a different tenant returns 404, not 403 (ADR-028 precedent).
- `test_deactivated_users_portal_links_still_resolve` — a portal link created by a since-deactivated teammate still resolves publicly (confirms the no-cascade decision is actually implemented, not just documented).
- `test_deactivated_users_existing_token_is_rejected` — a deactivated user's already-issued, still-unexpired token gets 401 on its next authenticated request (`GET /api/v1/auth/me`).

## Audit results

| Check | Result |
|---|---|
| `pytest` (145 tests: 136 pre-existing + 9 new) | ✅ 145 passed, 190 warnings (pre-existing deprecation warnings, unrelated to this sprint) |
| `alembic check` | ✅ "No new upgrade operations detected." |
| `alembic downgrade -1` / `upgrade head` round-trip | ✅ Clean — `dae9516f388b` ↔ `880e12adf384` |
| `pnpm lint` | ✅ 2 successful, 0 errors/warnings |
| `pnpm build` (includes Next.js's own TypeScript check — `apps/web` has no standalone `check-types` script, matching Sprint 014's established repo setup) | ✅ Compiled clean, 15 routes (14 app routes + `/_not-found`), same count as Sprint 014's baseline — no new routes |
| `git diff --check` | ✅ exit 0, no whitespace/conflict-marker issues |
| Manual smoke test against the real running app (uvicorn + local Postgres, not the pytest TestClient) | ✅ Invited and accepted a real Staff user; `GET /api/v1/users` listed Owner+Staff correctly; Staff got 403 listing; created a customer+portal link as the Staff user; Owner deactivated them (200, `is_active` → false); the deactivated user's already-issued token got 401 on `GET /api/v1/auth/me`; exactly one `team_member_deactivated` activity event appeared with the correct title/description; the portal link they created still resolved publicly (200) — confirms no cascade; Owner's self-deactivation attempt → 409, and the Owner's own session kept working afterward |

## Follow-up items raised, not part of Sprint 015 scope

- No reactivation endpoint/UI — deliberately deferred (deactivate-only, matches invitations/portal-links precedent).
- The pre-existing `EmailAlreadyRegisteredError`/`is_active` interaction (re-inviting a deactivated user's email still fails, since `crud.get_user_by_email` doesn't filter by `is_active`) — flagged, not fixed.
- Documents/messaging for the client portal — still unstarted since Sprint 013, named again in Sprint 014's follow-ups.
- `docs/ROADMAP.md`'s stale Sprint 008–016 table remains unreconciled.
- The roadmap's Supplier/Purchasing Sprint 015 line remains entirely unaddressed and unscheduled.
- Sprint 016 is not started.
