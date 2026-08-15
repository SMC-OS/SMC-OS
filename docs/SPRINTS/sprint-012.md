# Sprint 012 — Tenant Data Isolation Enforcement

**Status:** ✅ Done. Implemented and verified against the live local PostgreSQL 16 instance; not yet committed to git.

## Objective

Fifth sprint of the SaaS-transformation phase (Phase 2), and the one every sprint since Sprint 008 explicitly deferred: enforce that an authenticated user can only read, create, or mutate records belonging to their own tenant. Per `docs/USER_ROLES.md` §1 (pre-Sprint-012 wording): "anyone with network access can call `POST /api/v1/quote`, `POST /api/v1/estimate`, `/api/v1/activity`, `/api/v1/notifications`, `/api/v1/process`, `/api/v1/dashboard`, etc. without a token... a valid token now always carries a real `tenant_id` (ADR-026), but no protected route filters anything by it yet." This sprint closes that gap.

**Deliberately out of scope, by design, not oversight:** billing, subscriptions, Stripe, email delivery, a teams-management UI, or analytics; any change to `role`/`require_role()`'s permission *matrix* (Owner vs. Staff scoping remains exactly ADR-027/028's — this sprint enforces the *tenant* boundary, not a role-based one within it); redesigning `materials` into a per-tenant catalogue (stays shared/global, see below); redesigning the tenant lifecycle (`POST /api/v1/tenants` was audited, not redesigned — see below).

## Scope delivered

**Backend — data layer**
- `app/database/crud.py` — every `customers`/`projects`/`quotes`/`activity_log`/`notifications` function now takes a required `tenant_id` and filters or checks ownership by it. `list_*`/`count_*` add `WHERE tenant_id = :tenant_id`; `get_*_by_id`/`update_project_status`/`mark_notification_read` fold it into the lookup predicate, so a cross-tenant id behaves identically to an unknown one. `create_quote`/`create_activity_log`/`create_notification` keep `tenant_id` optional (`None` allowed) — an anonymous `/quote`/`/estimate` call and seed data have no tenant.
- `app/database/models.py` — `tenant_id` gains a plain non-unique index on `Customer`, `Quote`, `Project`, `ActivityLog`, `NotificationRecord` (migration `a8d91098a01e`, additive-only). Columns stay nullable — `NULL` still means "belongs to no tenant" for the anonymous-quote/seed-row case.

**Backend — services and routers**
- `app/customers/`, `app/projects/`, `app/quotes/` — `service.py`/`router.py` thread `tenant_id` (from `current_user.tenant_id`) through every method. `app/projects/service.py::update_status` now fetch-checks ownership before mutating — previously any authenticated user of any tenant could advance any other tenant's project by guessing its id, a write-path leak, not just a read one.
- **Relationship-linkage bypass closed:** `app/projects/service.py` and `app/quotes/service.py` each gained a `CustomerNotFoundError`, raised when a supplied `customer_id` doesn't resolve under the caller's own tenant, caught by the router as `404`. Id-scoping alone doesn't stop a project or quote from being *created* pointing at another tenant's customer — this closes that separate bypass.
- `app/activity/` and `app/notifications/` — **both routers had no authentication at all before this sprint.** Both gained `Depends(get_current_user)`; `ActivityService`/`NotificationService` and their repository implementations now require `tenant_id` on every read and tag every write with it. `NotificationService.mark_read` is now an ownership-checked write, matching the project-status precedent.
- `app/auth/dependencies.py` — new `get_current_user_optional`: returns `User | None` instead of raising `401` on a missing/invalid token. Used only by `POST /api/v1/quote` and `/estimate` (`app/api/v1/core.py`), which stay deliberately public (ADR-023) — a valid token opportunistically tags the created quote with that tenant; no token means the quote is still created, just tenant-less and invisible to every tenant's browsing routes.
- `GET /api/v1/dashboard` (`app/api/v1/core.py`) — now requires auth (previously fully public) and returns only the caller's tenant's counts.
- `app/tenants/router.py` — **audited and fixed a pre-existing leak**, not newly introduced this sprint: `GET /tenants` and `GET /tenants/{id}` returned *every* tenant's name/slug/status to any authenticated caller. Both now return only the caller's own tenant; a cross-tenant id `404`s. `POST /tenants` was audited and left unchanged — it creates a new, unlinked tenant, which doesn't read or expose any other tenant's existing data, so it isn't an isolation leak (whether the route should still exist at all, now that `/auth/signup` is the real workspace-creation path, is a separate, explicitly deferred question).
- `app/activity/seed.py`, `app/notifications/seed.py` — the "already seeded" guard could no longer call `activity_service.list_recent()`/`notification_service.list_all()` (now require a real `tenant_id`, and there's no tenant yet at startup) — switched to an unfiltered `crud.count_activity_log()`/`count_notifications()` check instead.
- `app/tenants/service.py::create()` — the `TENANT_CREATED` activity event is now logged against the *new* tenant's own id (previously always `None`), so it's visible in that tenant's own future activity feed instead of orphaned.

**Backend — deliberately unfiltered**
- `materials` stays a shared, unfiltered reference catalogue — ~30 seeded rows, identical for every tenant, no dedicated route (`app/materials/`, consumed by `app/quotes/calculator.py` and the sales/search assistants). It has a nullable `tenant_id` column (part of the original Sprint 002 set of 7) but nothing populates or reads it; filtering it would require per-tenant seeding that doesn't exist and would break pricing lookups for every tenant but whichever one the seed happened to run under.
- `users` and `invitations` were already correctly tenant-scoped since Sprint 009/011 respectively and are unchanged. `tenants` is the tenant, not owned by one.
- `POST /api/v1/process` reads only the shared materials catalogue (via `SalesAssistant`/`SearchAssistant`) — no tenant business data involved, no change needed.

**Migration**
- `alembic/versions/a8d91098a01e_add_tenant_id_indexes_for_isolation.py` — one additive migration, 5 explicitly-named indexes (`ix_customers_tenant_id`, `ix_projects_tenant_id`, `ix_quotes_tenant_id`, `ix_activity_log_tenant_id`, `ix_notifications_tenant_id`), no column or nullability changes, symmetric `upgrade()`/`downgrade()`. Generated via `alembic revision --autogenerate` against the already-updated models — autogenerate detected exactly these 5 indexes and nothing else, confirming no other model/migration drift existed.

**Docs**
- `docs/DECISIONS.md` — ADR-029 (the full mechanism: id-scoping, the anonymous-quote/optional-auth design, the activity/notifications auth cutover, the tenants-router leak fix, the relationship-bypass check, the materials exception, and the test-suite fallout below).
- `docs/API_SPEC.md`, `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md` — updated route-by-route: which routes gained auth, which gained tenant scoping, new `404` semantics for cross-tenant access, the route summary table's "Auth required?" column.
- `docs/ROADMAP.md` was **not** touched — its Sprint 008–016 table is a stale, pre-SaaS-replan draft (flagged as a known, unreconciled gap since `sprint-008.md`); reconciling it remains explicitly out of scope for this sprint, per instruction.

**Frontend**
- None. Zero files under `apps/web/` touched. Cross-tenant records simply don't appear in list views, and a direct fetch of another tenant's record `404`s exactly like an unknown id already did — `lib/api.ts`'s existing `ApiError`/401-clears-token handling needed no change. `GET /api/v1/dashboard`, `/activity`, `/notifications` now requiring a token is transparent since `request()` already attaches a stored token automatically and these are only ever called from already-authenticated pages — verified via a clean `lint`/`check-types`/`build` regression pass.

## A note on how this sprint's changes landed

Two authorship threads: the isolation mechanism, migration, tenant-router leak fix, activity/notifications auth cutover, and the bulk of the test suite (including the second-tenant fixture and most cross-tenant read/mutation tests) were built directly. Concurrently, the relationship-linkage bypass fix (`CustomerNotFoundError` on `projects`/`quotes`, closing the "create a record pointing at another tenant's customer" gap that id-scoping alone doesn't cover), its accompanying tests, and the bulk of `docs/DECISIONS.md`/`docs/API_SPEC.md`/`docs/SYSTEM_ARCHITECTURE.md`/`docs/USER_ROLES.md`'s prose were completed by a second pass over the same working tree before final verification — reviewed, reconciled, and folded into this sprint's own report rather than treated as separate. One resulting edit was reverted: `docs/ROADMAP.md`'s Sprint 012 status row was marked "✅ Done" by that second pass; reverted to its committed state because the sprint's own instructions explicitly said not to touch the roadmap, regardless of source.

## Test-suite fallout, not an app bug

Several existing test cleanup helpers (`tests/conftest.py`, `tests/test_tenants.py`, `tests/test_auth.py`, `tests/test_invitations.py`) deleted a `Tenant` row without first deleting the `ActivityLog` rows that now correctly FK-reference it under the *new* tenant's own id (previously always `None`, so the FK constraint added in Sprint 008/ADR-025 was never actually exercised by a delete). This surfaced as `ForeignKeyViolation` errors during test teardown, not a production code path — nothing in the running application ever deletes a tenant. Fixed by deleting each tenant's `ActivityLog` rows before the `Tenant` row in every affected fixture/cleanup helper.

## Audit results

| Check | Result |
|---|---|
| `pytest` (115 tests: 90 from Sprint 011 + 25 new: `test_activity.py`, `test_notifications.py` new files, plus cross-tenant cases added to `test_customers.py`/`test_projects.py`/`test_quotes_api.py`/`test_tenants.py`/`test_dashboard.py`) | ✅ 115 passed |
| Customer/project/quote list, get, and create all tenant-scoped; cross-tenant `get` → `404` | ✅ Confirmed |
| Project status update (write path) cross-tenant → `404`, confirmed not mutated | ✅ Confirmed (`test_update_status_cross_tenant_returns_404_and_does_not_mutate`) |
| Notification mark-as-read (write path) cross-tenant → `404`, confirmed not mutated | ✅ Confirmed (`test_mark_read_cross_tenant_returns_404_and_does_not_mutate`) |
| Creating a project/quote with another tenant's `customer_id` → `404`, nothing persisted | ✅ Confirmed (relationship-bypass tests in `test_projects.py`/`test_quotes_api.py`) |
| `activity`/`notifications` now require auth (previously fully public) | ✅ Confirmed (`test_activity_routes_require_auth`, `test_notifications_routes_require_auth`, `test_health.py`'s mount-smoke-tests updated to expect `401`) |
| `activity`/`notifications` list/create tenant-scoped | ✅ Confirmed |
| `dashboard` requires auth and returns only the caller's tenant's counts | ✅ Confirmed (`test_dashboard_requires_auth`, `test_dashboard_counts_are_tenant_scoped`) |
| Anonymous `POST /quote` still succeeds with no token; resulting quote invisible to every tenant | ✅ Confirmed (`test_create_quote_without_token_is_not_visible_to_any_tenant`) |
| `GET /tenants`/`GET /tenants/{id}` return only the caller's own tenant; cross-tenant id `404`s | ✅ Confirmed (`test_list_tenants_returns_only_callers_own_tenant`, `test_tenant_detail_cross_tenant_returns_404`, `test_newly_created_tenant_not_visible_to_its_creator`) |
| `POST /tenants` audited — confirmed no isolation leak, left unchanged | ✅ Confirmed by inspection, documented in ADR-029 |
| No same-tenant behavior regressed | ✅ All pre-existing tests pass (with cleanup-helper and public-route-assumption fixes noted above — no assertion on *correct* same-tenant behavior needed to change) |
| `alembic upgrade head` → `downgrade -1` → `upgrade head` | ✅ Clean round-trip against the live DB |
| `alembic check` | ✅ No new upgrade operations detected (model matches migration) |
| `git diff --check` | ✅ No whitespace errors |
| `eslint .` | ✅ 0 errors, 0 warnings (no frontend files touched) |
| `tsc --noEmit` | ✅ Clean |
| `next build` | ✅ All 15 routes compile, unchanged from Sprint 011 |

## Follow-up items raised, not part of Sprint 012 scope

- Whether `POST /api/v1/tenants` should still be reachable at all, now that `POST /api/v1/auth/signup` is the real workspace-creation path — audited for isolation risk (none found), not redesigned, per this sprint's explicit instructions.
- The permission *matrix* beyond Owner-vs-Staff-within-a-tenant (tenant settings? billing? removing a teammate as Owner-only?) remains exactly where ADR-027/028 left it — untouched by this sprint, which enforced the tenant boundary, not a role-based one within it.
- `docs/ROADMAP.md`'s Sprint 008–016 table remains the stale, pre-SaaS-replan draft flagged since `sprint-008.md` — reconciling it is still a separate, larger documentation decision, explicitly not done here.
- The pre-existing, unrelated follow-up items noted in `sprint-008.md` through `sprint-011.md` (missing AI-draft API docs, `count_quotes_today`'s timezone comparison) remain unfixed — still out of scope for this sprint.
- Sprint 013 is not started.
