# Sprint 011 — Staff Invitations

**Status:** ✅ Done. Implemented and verified against the live local PostgreSQL 16 instance; not yet committed to git.

## Objective

Fourth sprint of the SaaS-transformation phase (Phase 2). Per `docs/USER_ROLES.md` §2, Sprint 010 shipped `UserRole`/`require_role()` as inert machinery — deliberately attached to zero routes — because there was no way for a tenant to have more than one user, which meant no way to ever create a `UserRole.STAFF` account to test enforcement against. Sprint 011 closes that gap: an Owner can invite a teammate by email, the invitee accepts via a one-time link (no account required to view or accept it), and a real `Staff` user is created in the same tenant. This also makes Sprint 011 the first sprint anywhere in the codebase where `require_role()` is attached to a real route — `POST`/`GET`/`DELETE /api/v1/invitations*` are Owner-only, and rejecting a Staff caller is now meaningfully restrictive rather than enforcement theatre.

**Deliberately out of scope, by design, not oversight:** inviting anyone as anything other than `Staff` (`InvitationCreate` has no `role` field — minting a second Owner is a materially bigger decision, left to a future sprint if it's ever actually needed); actual email delivery (the raw token is returned directly in the `POST /invitations` response body, the same "ship the mechanism, wire up delivery separately" shape Sprint 007's invoice PDF had before any email-sending existed); any frontend UI (no invite-management screen, no accept-invite page — same backend-only posture as Sprint 008 and Sprint 010, since a second role existing in the API is a precondition for a useful invite UI, not the reverse); deciding which *other* routes should become `OWNER`-only (tenant settings, billing, removing a teammate — still explicitly deferred per ADR-027/ADR-028); and — as with every SaaS-phase sprint so far — tenant data isolation on the business-data modules (Sprint 012, still unstarted).

## Scope delivered

**Backend**
- `app/database/models.py` — new `Invitation` table: `id`, `tenant_id` (FK), `invited_by_user_id` (FK), `email`, `role`, `token_hash` (unique), `status` (`"pending" | "accepted" | "revoked"`, `"expired"` deliberately never stored — derived at read time), `expires_at`, `created_at`.
- `alembic/versions/7aedf0956cff_add_invitations_table.py` — one migration, explicitly-named constraints, exact downgrade. Verified both directions (`downgrade -1` → `upgrade head`) against the live database; `alembic check` reports no model/migration drift.
- `app/database/crud.py` — `create_invitation`, `get_invitation_by_id`, `get_invitation_by_token_hash`, `list_invitations`, `get_pending_invitation`, `update_invitation_status`.
- `app/invitations/` (new module) — `models.py` (`InvitationCreate`, `InvitationOut`, `InvitationCreateOut`, `InvitationPublicOut`, `AcceptInvitationRequest`), `service.py` (`InvitationService` — token generation/hashing, create/list/revoke/accept, `derive_status()`), `router.py` (`POST`/`GET /invitations`, `DELETE /invitations/{id}` gated by `require_role(UserRole.OWNER)`; `GET /invitations/token/{token}` and `POST /invitations/token/{token}/accept` public).
- `app/core/config.py` — `invitation_expire_days` (default `7`), computed Python-side at creation, same style as the JWT `exp` claim.
- `app/api/v1/__init__.py` — mounts `invitations_router`.
- Token design: `secrets.token_urlsafe(32)`, SHA-256-hashed before persisting (`token_hash`) — the raw value exists only in the create-response and is never recoverable again, same convention `password_hash` already established. See ADR-028 for the full JWT-vs-opaque-token reasoning.
- `accept_invitation()` reuses `app.auth.service.auth_service.create_user()` to actually create the `Staff` user — the same cross-module reuse precedent `AuthService.signup()` set with `tenant_service.create()`.
- Cross-tenant invitation lookups (`revoke_invitation`) 404, not 403 — identical to "doesn't exist," so a cross-tenant call can't confirm another tenant's invitation exists.
- **Bug fixed during this sprint's own work:** the public `GET /invitations/token/{token}` route initially echoed the stored `status` column verbatim, which meant a `"pending"` row whose `expires_at` had already passed still read as `"pending"` to the invitee (only failing, confusingly, once they actually tried to accept). Fixed by adding `InvitationService.derive_status()` and using it everywhere a row's status is surfaced (`GET /invitations`, `GET /invitations/token/{token}`) — matches the design the `Invitation` model's own docstring already committed to ("`'expired'` is derived at read time from `expires_at`, not stored").

**Docs**
- `docs/DECISIONS.md` — ADR-028 (opaque hashed token vs. JWT, Staff-only scope, derived-not-stored `"expired"`, cross-tenant-404 reasoning, what's explicitly not included).
- `docs/USER_ROLES.md`, `docs/API_SPEC.md`, `docs/SYSTEM_ARCHITECTURE.md` — updated to Sprint 011: route table, folder tree, module table, and the "Staff" row in §2's anticipated-roles table (now "can exist," not just "a valid enum value").

**Frontend**
- None. No invite-management or accept-invite page exists yet — verified via a clean `lint`/`check-types`/`build` regression pass only, same posture as Sprint 008's and Sprint 010's frontend sections. A second real role existing in the API is a precondition for designing a useful invite UI (who can see it, what a Staff user's nav looks like), not something this sprint needed to build ahead of that design work.

## Why Staff-only, and why no email delivery

Letting an Owner mint a second Owner via this same flow is a materially different, higher-stakes action than "invite a teammate" — it wasn't part of what was scoped for this sprint, so `InvitationCreate` has no `role` field and `create_invitation()` always writes `UserRole.STAFF`; the `role` column exists on the table so a future sprint can widen this without a migration. Email delivery is a separate concern from the invitation mechanism itself — the raw token is returned directly in the API response, callable from Swagger/curl/a future frontend today, the same way Sprint 007 shipped a real downloadable invoice PDF before any email-sending capability existed anywhere in the codebase.

## Audit results

| Check | Result |
|---|---|
| `pytest` (90 tests: 73 from Sprint 010 + 17 new in `test_invitations.py`) | ✅ 90 passed |
| Owner can create/list/revoke an invitation | ✅ Confirmed |
| A Staff (non-Owner) caller gets `403` on create/list/revoke | ✅ Confirmed (`test_create_invitation_requires_owner_role`) — first real enforcement by `require_role()` anywhere |
| All three Owner-only routes `401` without a token | ✅ Confirmed |
| Duplicate-email and already-pending-invite both `409` | ✅ Confirmed |
| Cross-tenant revoke returns `404`, not `403` | ✅ Confirmed |
| Public token-view route requires no auth, hides internal IDs | ✅ Confirmed |
| Unknown token `404` on both the view and accept routes | ✅ Confirmed |
| Accepting creates a real `Staff` user who can then log in normally | ✅ Confirmed |
| Re-accepting an already-accepted token, a revoked token, and an expired token all `409` with a distinct message | ✅ Confirmed |
| Email registered via a separate path between invite and accept still `409`s at accept time | ✅ Confirmed |
| A still-`"pending"` row past `expires_at` reads as `"expired"` on both the public token view and the Owner's list, without writing anything back | ✅ Confirmed (`test_expired_invitation_reads_as_expired_and_cannot_be_accepted`) |
| No existing route's behavior changed | ✅ All 73 pre-existing tests still pass unchanged |
| `alembic upgrade head` / `downgrade -1` / `upgrade head` | ✅ Clean both directions against the live DB |
| `alembic check` | ✅ No new upgrade operations detected (model matches migration) |
| `git diff --check` | ✅ No whitespace errors |
| `pnpm lint` | ✅ 0 errors, 0 warnings (cache hit — no frontend files touched) |
| `pnpm check-types` | ✅ Clean (no frontend files touched) |
| `pnpm build` | ✅ All 14 routes compile, unchanged from Sprint 010 |

## Follow-up items raised, not part of Sprint 011 scope

- Deciding which *other* routes should become `OWNER`-only (tenant settings, billing, removing a teammate) remains explicitly deferred — a real `Staff` user existing now makes that design work *possible*, not done (ADR-027/ADR-028).
- No frontend invite-management or accept-invite page exists yet — needed before this feature is usable by anyone who isn't calling the API directly.
- No email delivery — the raw token must currently be copied out of the API response by hand.
- Sprint 012 (tenant isolation enforcement) remains the big unstarted item, unaffected by this sprint.
- The pre-existing, unrelated follow-up items noted in `sprint-008.md`/`sprint-009.md`/`sprint-010.md` (missing AI-draft API docs, `count_quotes_today`'s timezone comparison, the `docs/SYSTEM_ARCHITECTURE.md` §9 roadmap-reconciliation gap) remain unfixed — still out of scope for this sprint.
