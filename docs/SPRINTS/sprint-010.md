# Sprint 010 — Roles & Permissions Machinery

**Status:** ✅ Done. Implemented and verified against the live local PostgreSQL 16 instance; not yet committed to git.

## Objective

Third sprint of the SaaS-transformation phase (Phase 2). Per `docs/USER_ROLES.md` §2, Sprint 010 is where "real roles/permissions beyond Owner vs. nothing" land — but that document also states plainly that this sprint's role table was "anticipated, not fully designed... an input to that sprint's design work, not a specification." Before writing any code, the actual scope was narrowed with the person building this: Sprint 011 (invitations) hasn't happened yet, so there is still no way to create a `Staff` user — every account in the system today, seeded owner included, is an `Owner`. A permission system with only one role in practice can't meaningfully restrict anything. So this sprint ships the **machinery only** — a real role enum and a reusable permission-checking dependency — attached to zero routes, the same "ship it, prove it's inert, enforce later" shape Sprint 003's JWT auth had until Sprint 004, and Sprint 008's tenant FK still has until Sprint 012.

**Deliberately out of scope, by design, not oversight:** attaching `require_role()` to any existing route (there is nothing to meaningfully restrict yet — every current user passes any `OWNER`-only check), invitations / creating a second user in a tenant (Sprint 011), a permission matrix beyond "does this role match" (no such matrix has real routes to apply to yet), and — as with every SaaS-phase sprint so far — tenant data isolation (Sprint 012, still unstarted).

## Scope delivered

**Backend**
- `app/auth/models.py` — new `UserRole(str, Enum)` (`OWNER = "Owner"`, `STAFF = "Staff"`), stored as a plain `String` column on `users` (no DB-level enum or `CHECK` constraint — same convention `ProjectStatus` already established for `Project.status`, validated only at the Pydantic/API boundary). `UserOut.role` is now typed `UserRole | None` instead of `str | None`; the JSON wire shape is unchanged.
- `app/auth/service.py` — `AuthService.signup()` now assigns `UserRole.OWNER.value` instead of the string literal `"Owner"`.
- `app/auth/dependencies.py` — new `require_role(*allowed_roles: UserRole)`, a dependency factory mirroring `get_current_user`'s shape: builds a FastAPI dependency that 403s any authenticated user whose `role` isn't in the allowed set. **Not attached to any route.**
- `app/database/models.py` — `User.role`'s column comment updated to point at `UserRole`; the column itself (`Mapped[str | None]`, nullable, plain `String`) is unchanged — no migration needed.
- No Alembic revision this sprint — nothing about the database schema changed, only what values are considered valid at the API layer.

**Frontend**
- None. No UI reads or displays roles yet, and none was needed for machinery with no route attached to it — verified via a clean `lint`/`build`/`check-types` regression pass only, same posture as Sprint 008's frontend section.

## Why nothing was enforced, stated plainly

`require_role()` works and is unit-tested (`tests/test_permissions.py`), but wiring it into any route today would be enforcement theatre: every real user — the seeded owner and every signup's first user — is a `UserRole.OWNER`, so an `OWNER`-only gate on any route would restrict nobody while giving the false impression that permissions are meaningfully checked. The actual value of this sprint is that the next sprint with a real second role to protect against (Sprint 011's invitations, most likely) can attach `require_role(UserRole.OWNER)` to a route as a one-line `Depends(...)` change, instead of designing and building the mechanism at the same time it's first needed.

## Audit results

| Check | Result |
|---|---|
| `pytest` (73 tests: 69 from Sprint 009 + 4 new in `test_permissions.py`) | ✅ 73 passed |
| `require_role()` allows a matching role through unchanged | ✅ Confirmed (`test_require_role_allows_matching_role`) |
| `require_role()` allows any of several roles | ✅ Confirmed (`test_require_role_allows_any_of_multiple_roles`) |
| `require_role()` rejects a non-matching role with `403` | ✅ Confirmed (`test_require_role_rejects_non_matching_role`) |
| `require_role()` rejects a `None` role with `403` | ✅ Confirmed (`test_require_role_rejects_missing_role`) |
| No existing route's behavior changed | ✅ All 69 pre-existing tests still pass unchanged |
| `UserOut.role` still round-trips `"Owner"` over the wire unchanged | ✅ Confirmed via the existing `test_login_success`/`test_signup_creates_tenant_and_user` assertions |
| `eslint .` | ✅ 0 errors, 0 warnings |
| `next build` | ✅ All 14 routes compile, unchanged from Sprint 009 (no frontend files touched) |

## Follow-up items raised, not part of Sprint 010 scope

- Sprint 011 (invitations) is next — the first sprint that can actually create a `UserRole.STAFF` user, at which point `require_role()` has something real to test enforcement against.
- Deciding *which* routes should eventually require `OWNER` specifically (tenant settings, billing, removing a teammate) is explicitly deferred — `docs/USER_ROLES.md` §2 calls this out as design work for whichever sprint first has a second role's user to reason about, not decided speculatively here.
- Sprint 012 (tenant isolation enforcement) remains the big unstarted item, unaffected by this sprint.
- The pre-existing, unrelated follow-up items noted in `sprint-008.md`/`sprint-009.md` (missing AI-draft API docs, `count_quotes_today`'s timezone comparison, the `docs/SYSTEM_ARCHITECTURE.md` §9 roadmap-reconciliation gap) remain unfixed — still out of scope for this sprint.
