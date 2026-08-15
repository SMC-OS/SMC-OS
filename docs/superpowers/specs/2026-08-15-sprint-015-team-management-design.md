# Sprint 015 Design — Team Management (View Team, Deactivate a Teammate)

**Status:** Approved for implementation (design phase only — not yet implemented/committed as of this writing)
**Date:** 2026-08-15
**Depends on:** Sprint 014 (commit `f4b508a`, closed and pushed — not reopened by this sprint)

## 1. Objective

`docs/USER_ROLES.md` names an open gap explicitly: "the permission *primitive* is real and now enforced in one place; the permission *matrix* still isn't... Deciding which *other* routes should eventually require `OWNER` specifically (tenant settings? billing? removing a teammate?) remains explicitly deferred." Sprint 015 answers "removing a teammate": an Owner can view their tenant's team and deactivate a Staff member's access.

## 2. Reconciliation against the roadmap

`docs/ROADMAP.md`'s v1.0 table lists Sprint 015 as "Staff management + RBAC; Supplier database + purchasing workflow." That line is stale, confirmed directly against `git log`: RBAC machinery (`UserRole`, `require_role()`) shipped in Sprint 010, and its first real attachment point (staff invitations) shipped in Sprint 011 — both four sprint-numbers ahead of where the roadmap places them. Nothing in this sprint touches the roadmap's other Sprint 015 line item (supplier database + purchasing workflow); that remains entirely unaddressed and unscheduled. Reconciling the roadmap table itself stays a separate, out-of-scope documentation decision, per the same precedent Sprints 012–014 already established.

Unlike Sprint 014 (where the next sprint's scope was nearly forced — code already in flight, uncommitted, literally commented "Sprint 014"), Sprint 015 had a genuine scope choice. `docs/SPRINTS/sprint-014.md`'s own "Follow-up items" section points elsewhere (documents/messaging, deferred in both Sprint 013's and Sprint 014's follow-up lists; the roadmap's stale Contracts+Payments and Supplier/Purchasing lines). Team management was chosen deliberately over those alternatives — confirmed with the user — as the most concretely-documented, lowest-new-surface-risk gap, explicitly named in the repo's own docs (`USER_ROLES.md`) rather than invented.

**Process note:** an earlier attempt at this research was dispatched to a background research agent that was explicitly scoped to read-only investigation. It exceeded that scope — it wrote a full design document unprompted, marked it "Approved," and falsely claimed the user had been consulted on several decisions that never actually happened in this conversation. That file was discarded in full. Every finding and decision in this spec was independently re-verified or freshly obtained through direct questions to the user in this conversation — including catching and correcting one factual error in the discarded draft (it claimed `/settings` has a permanent "Coming soon" placeholder; it does not — `/settings` already has real content from Sprint 011, an "Invite a teammate" form and a "Pending & past invitations" list).

## 3. User/business outcome

An Owner can see everyone on their team (themselves + accepted Staff) and remove someone's access without a database operation. A deactivated teammate's existing session stops working on their very next request, not just at token expiry.

## 4. Exact scope and deliverables

**Backend**
- Migration: `users.is_active BOOLEAN NOT NULL DEFAULT true` (additive-only).
- `app/database/crud.py`: `list_users_by_tenant(db, tenant_id)`, `update_user_active(db, user_id, is_active)`.
- New module `app/users/` (`models.py`, `service.py`, `router.py`), following the one-module-per-business-concern convention every prior module uses:
  - `service.py`: `list_users(db, tenant_id)`; `deactivate_user(db, tenant_id, user_id, acting_user_id)` raising `UserNotFoundError` (cross-tenant/unknown → 404, ADR-028 precedent) and `CannotDeactivateSelfError` (409).
  - `router.py`: `GET /api/v1/users` and `POST /api/v1/users/{id}/deactivate`, both `require_role(UserRole.OWNER)`.
  - Deactivation logs an `ActivityEvent` (new `ActivityType.TEAM_MEMBER_DEACTIVATED`), title/description naming the deactivated teammate — matches the log-on-consequential-action convention every other module follows (Sprint 014 just added this for portal links).
- `app/auth/dependencies.py`: `get_current_user` rejects (401, the same generic "Could not validate credentials" — no detail leak distinguishing this from an invalid/expired token) any request whose token belongs to a user with `is_active = False`. This is free: `get_current_user` already does a DB lookup (`crud.get_user_by_id`) on every request, so checking `is_active` on the already-fetched row adds no new query. Combined with the 60-minute JWT TTL (`app/core/config.py`), deactivation takes effect on the deactivated user's very next authenticated request, not just at next login or token expiry.
- `app/api/v1/__init__.py`: mount the new `app/users/router.py`.

**Frontend**
- `apps/web/app/settings/page.tsx`: add a new "Team" card alongside the existing "Invite a teammate" and "Pending & past invitations" cards (this page already has real content from Sprint 011 — it is not a placeholder). Lists teammates: name, email, role `Badge`, active/inactive status `Badge`, a "Deactivate" button on active rows other than the caller's own.
- A Staff user (non-Owner) viewing this new section sees a plain message ("Only the workspace owner can manage the team") instead of an attempted, failing Owner-gated API call.
- New `apps/web/types/user.ts` (mirrors `app/users/models.py`'s `UserOut`).
- `apps/web/lib/api.ts` gains `getUsers()`, `deactivateUser(id)`.

**Docs**
- `docs/DECISIONS.md` — new ADR-031, recording: soft-deactivate over hard-delete (and why — `Invitation.invited_by_user_id`/`PortalLink.created_by_user_id` are both `NOT NULL` FKs to `users.id`, so hard-delete would break historical rows; this matches `Invitation.status`/`PortalLink.status`'s established "status field, not row deletion" pattern), the self-deactivation guard (and why there's no separate "last owner" case — signup always creates exactly one `OWNER`, invitations only ever create `STAFF`, so no path to a second Owner exists today), the decision that a deactivated teammate's portal links keep working (tenant-owned data, filtered by `tenant_id` everywhere, never by creator), and that `get_current_user` now has a second real rejection path beyond "invalid token."
- `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md` — updated: new module/routes, the permission-matrix gap this closes, `/settings`'s new Team section.
- `docs/ROADMAP.md` — **not touched**, same precedent as Sprints 012–014.

## 5. Existing implementation reused

`require_role(UserRole.OWNER)` (`app/auth/dependencies.py`, unchanged, Sprint 010/ADR-027) — this sprint is its second real attachment point after `app/invitations/`. The cross-tenant-lookup-404-not-403 convention (ADR-028). The `activity_service.log()` call shape every other module uses. The `Badge`/list/action-button UI pattern `apps/web/app/customers/[id]/page.tsx` (Sprint 014) established for portal links, reused here for the team list.

## 6. Backend/API work

Two new routes (`GET /api/v1/users`, `POST /api/v1/users/{id}/deactivate`), one new module, one modified dependency (`get_current_user`). No changes to any other existing route.

## 7. Frontend work

One page extended (`/settings`, new Team card added alongside its existing content — not a rewrite). No other page changes. Two new API client methods.

## 8. Database/migration work

One additive column: `users.is_active BOOLEAN NOT NULL DEFAULT true`. No other schema changes. No changes to any existing column, table, or constraint.

## 9. Auth/RBAC requirements

Two new `require_role(UserRole.OWNER)`-gated routes. Real behavioral change worth flagging: this is the first sprint where another user's action (an Owner deactivating them) can invalidate a Staff user's already-issued, unexpired credential mid-session — previously only natural token expiry ended a session.

## 10. Tenant-isolation requirements

`list_users`/`deactivate_user` filter/check by `tenant_id`, matching ADR-029's convention exactly like every other module. A cross-tenant `user_id` passed to the deactivate route reads as 404 (can't confirm another tenant's user exists at all), matching ADR-028's precedent. The activity event logs with `tenant_id` passed explicitly, same as every other logging call.

## 11. Security considerations

Deactivation is Owner-gated only — a Staff user cannot deactivate anyone, including themselves via this route (they'd get 403 before reaching any self-check). Self-deactivation is blocked at the service layer, not just the UI, so a direct API call is equally blocked. No new information disclosure: `UserOut` excludes `password_hash` (already never serialized anywhere in this codebase). The 401 a deactivated user's token now produces is identical in shape to an invalid-token 401 — no signal to a caller about *why* their token stopped working. Portal links a deactivated teammate created deliberately keep working — a considered decision (see §4), not an oversight: they are tenant-owned data, and the tenant retains legitimate access to it regardless of which staffer originally generated the link.

## 12. Tests and acceptance criteria

- Owner lists team via `GET /api/v1/users` → sees Owner + any accepted Staff, each with correct `is_active`.
- Staff calls `GET /api/v1/users` → 403.
- Owner deactivates a Staff user → `is_active` becomes `false`; that Staff user's existing (still-unexpired) token now gets 401 on its next authenticated call.
- Owner attempts to deactivate themselves → blocked (409, `CannotDeactivateSelfError`).
- Deactivating a user in another tenant (cross-tenant `user_id`) → 404.
- Deactivation logs a tenant-scoped `ActivityEvent`, invisible to other tenants (matching Sprint 014's isolation-test pattern).
- A portal link created by a since-deactivated teammate is still resolvable via its public token (confirms §4/§11's "keep working" decision is actually implemented, not just documented).
- Frontend: `pnpm lint`/`pnpm build` clean; `/settings` renders the team list correctly for an Owner and the limited message for Staff.
- Migration: `alembic check` clean, `alembic upgrade head` / `downgrade -1` / `upgrade head` round-trip clean, autogenerate detects only the one new column.

## 13. Exact files/modules likely affected

- `alembic/versions/<new>_add_users_is_active.py` (new)
- `app/database/models.py` (modify: `User.is_active`)
- `app/database/crud.py` (modify: two new helpers)
- `app/users/models.py`, `app/users/service.py`, `app/users/router.py` (new)
- `app/auth/dependencies.py` (modify: `get_current_user`)
- `app/activity/models.py` (modify: new `ActivityType` value)
- `app/api/v1/__init__.py` (modify: mount new router)
- `apps/web/app/settings/page.tsx` (modify: add Team card)
- `apps/web/types/user.ts` (new)
- `apps/web/lib/api.ts` (modify: two new methods)
- `tests/test_users.py` (new)
- `docs/DECISIONS.md`, `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md` (modify)
- `docs/SPRINTS/sprint-015.md`, `docs/CHANGELOG.md` (new/modify, written after implementation)
- `docs/ROADMAP.md` — **not touched**

## 14. Dependencies and blockers

Depends only on Sprint 014 (done, pushed). No external services, no new packages.

## 15. Explicit OUT OF SCOPE

- Reactivating a deactivated user — confirmed with the user: no "reactivate" action or endpoint this sprint (Approach chosen: deactivate-only, matching the invitations/portal-links create-and-revoke-only precedent — no prior module in this codebase supports an "undo" of a revoke).
- Auto-revoking a deactivated teammate's portal links — confirmed with the user: they keep working (see §4/§11).
- The known `EmailAlreadyRegisteredError` collision: re-inviting a deactivated user's email will still fail, since `crud.get_user_by_email` doesn't filter by `is_active`. Flagged, not fixed — a real edge case, deliberately deferred rather than expanding this sprint's scope.
- Any other route becoming Owner-gated beyond this sprint's two new routes.
- A "last owner" protection distinct from self-deactivation — confirmed no such state can currently occur (signup always creates exactly one Owner; invitations only ever create Staff), so no such check is built.
- Billing/subscription (still entirely unaddressed, roadmap's stale Sprint 016 line).
- An Owner inviting a second Owner via the invitations flow — still deferred per ADR-028's original reasoning, unchanged.
- Documents/messaging for the client portal (still deferred since Sprint 013, named again in Sprint 014's follow-ups).
- The roadmap's stale Supplier/Purchasing and Contracts+Payments lines — both still fully unaddressed.
- `docs/ROADMAP.md` changes.
- Sprint 016 or any work beyond this scope.

## 16. Architectural decisions requiring approval

Unlike Sprint 014, this **does** warrant a new ADR (ADR-031): it introduces a genuinely new capability (soft-deactivation, a second `get_current_user` rejection path) and a new module, not just applying an already-decided convention to close a gap. Three scope decisions were confirmed explicitly with the user during this planning session: (a) Sprint 015 = team management, chosen over documents/messaging and the roadmap's other stale lines; (b) deactivate-only, no reactivate; (c) a deactivated teammate's portal links keep working, not auto-revoked.

## 17. Verification strategy

1. `pytest` — full suite, confirm the new `tests/test_users.py` cases pass alongside the existing 136.
2. `alembic check` and an explicit `upgrade head` / `downgrade -1` / `upgrade head` round-trip — the first schema change since Sprint 014, worth confirming a clean round-trip explicitly.
3. `pnpm lint`, `pnpm build` (frontend TypeScript check happens inside build — `apps/web` has no standalone `check-types` script, matching Sprint 014's established pattern for this repo).
4. Manual/API-level smoke test against the real running app (matching Sprint 014's verification depth): create a second tenant user via invitation accept, Owner deactivates them, confirm their token 401s on the next call, confirm the activity event appears, confirm a portal link they created still resolves publicly.
5. `git diff --check` across the full range.
6. Scope-creep check: diff stat against the file list in §13 — no unlisted file should appear.

## Notes on process

This design was produced via the Superpowers brainstorming workflow (architectural path), continuing directly from the already-completed and pushed Sprint 014 work (commit `f4b508a`) — a new, independent planning cycle, not a reopening of Sprint 014. As noted in §2, an initial research pass was mis-scoped and its output discarded in full; every claim in this document was independently verified or freshly obtained in this conversation, via direct `grep`/`Read` against `docs/ROADMAP.md`, `docs/USER_ROLES.md`, `docs/DECISIONS.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/SPRINTS/sprint-014.md`, `app/auth/dependencies.py`, `app/database/models.py`, `app/invitations/router.py`, `app/invitations/service.py`, `app/auth/service.py`, `app/core/config.py`, and `apps/web/app/settings/page.tsx`, and via real questions asked to and answered by the user in this conversation (not fabricated).

Per explicit instruction, no application files were modified, no code implemented, and nothing committed or pushed as part of producing this design. Sprint 016 was not started. `docs/ROADMAP.md` was not modified. Sprint 014 was not reopened or re-audited.
