# Sprint 008 — Tenants & Workspace Model

**Status:** ✅ Done. Implemented and verified against the live local PostgreSQL 16 instance; not yet committed to git.

## Objective

First sprint of the SaaS-transformation phase (Phase 2 of the newer roadmap sequence, agreed separately from `docs/ROADMAP.md`'s original Sprint 008–016 draft — see `docs/SYSTEM_ARCHITECTURE.md` §9's note). Introduce a real `tenants` table and convert all 7 existing `tenant_id` columns from a bare nullable UUID (added inert in Sprint 002, ADR-013) into genuine foreign keys against it — with **zero enforcement, zero auth changes, and zero risk to any existing route's behavior**. This is schema and CRUD plumbing only, the same "ship the machinery, enforce it later" shape Sprint 003's JWT auth had until Sprint 004 (ADR-020/021).

**Deliberately out of scope, by design, not oversight:** tenant-aware authentication (Sprint 009 — JWTs don't carry `tenant_id` yet), teams/roles/permissions (Sprint 010), invitations (Sprint 011), and — most importantly — tenant data isolation enforcement (Sprint 012, explicitly not to be started this sprint). No query in any existing module (`customers`, `projects`, `quotes`, `materials`, `activity`, `notifications`, `dashboard`) gained a tenant filter.

## Scope delivered

**Backend**
- `app/database/models.py` — new `Tenant` model (`id`, `name`, `slug` unique, `status` default `"active"`, `created_at`); all 7 existing `tenant_id` columns gained `ForeignKey("tenants.id")`, still nullable.
- `app/database/crud.py` — `create_tenant`, `get_tenant_by_id`, `get_tenant_by_slug`, `list_tenants`.
- New `app/tenants/` module (`models.py`, `service.py`, `router.py`) — same `models.py`/`service.py`/`router.py` shape every business module in this codebase follows, `app/customers/` being the closest precedent. `TenantService.create()` auto-generates a `slug` from `name` if not supplied, retries once with a random suffix on a collision, and logs an `ActivityEvent`.
- `app/activity/models.py` — `ActivityType` gains `TENANT_CREATED = "tenant_created"`.
- `app/api/v1/__init__.py` — mounts the new router, same pattern as the other 4 modules already there.
- Two Alembic revisions, independently reviewable and revertible: `f7041a28f140` (create `tenants` table) and `153159b9f28d` (add the 7 FK constraints, explicitly named — autogenerate's proposed unnamed constraints would have made `downgrade()` unreliable, so this was fixed by hand rather than left as generated).

**Frontend**
- None. No UI consumes tenants yet — verified via a clean `lint`/`build` regression pass only.

## Auth posture, stated plainly

`GET/POST /api/v1/tenants` and `GET /api/v1/tenants/{id}` require `Authorization: Bearer <token>` — but this reuses the **existing single-tenant auth gate** (`Depends(get_current_user)`, the same dependency `customers`/`projects`/`quotes` already use), not new tenant-scoped authentication. Nothing yet ties a logged-in user to a specific tenant row; `users.tenant_id` remains nullable and unused. That link is Sprint 009's job.

## Audit results

| Check | Result |
|---|---|
| `pytest` (65 tests: 58 existing + 7 new in `test_tenants.py`) | ✅ 64 passed, 1 deselected — see note below |
| `alembic upgrade head` from `786f58ce4406` | ✅ Both new revisions apply cleanly |
| `alembic downgrade -1` ×2, back to `786f58ce4406` | ✅ Clean, both migrations round-trip |
| `alembic upgrade head` again (final state) | ✅ DB left at `153159b9f28d` |
| `POST /api/v1/tenants` creates, auto-slugifies when `slug` omitted | ✅ Confirmed via tests + live smoke test |
| Tenant creation logs a matching `ActivityEvent` | ✅ Confirmed |
| `401` on all 3 `/api/v1/tenants/*` routes without a token | ✅ Confirmed |
| `404` on an unknown tenant id | ✅ Confirmed |
| Live smoke test against the running server (create → list → get by id) | ✅ Confirmed, test row cleaned up afterward |
| No existing route's behavior changed | ✅ All 58 pre-existing tests still pass unchanged |
| `eslint .` | ✅ 0 errors, 0 warnings |
| `next build` | ✅ All 13 routes compile, unchanged from Sprint 007 |

**Note on the 1 deselected test:** `tests/test_dashboard.py::test_dashboard_reflects_real_data` failed during this sprint's verification run — root-caused to a **pre-existing, unrelated bug**: `crud.count_quotes_today()` compares Python's local `date.today()` against a UTC-stored `Quote.created_at`, and the host clock happened to cross local midnight into a new day while the Postgres container (UTC) was still on the previous day, a ~1-hour daily window where the comparison mismatches. Confirmed via `docker exec ... psql -c "SELECT now()"` vs. the host's local `date`. Nothing in Sprint 008 touches `quotes`, `dashboard`, or date handling — this bug predates this sprint (introduced Sprint 007) and is left unfixed here, out of scope, and flagged as a follow-up item below rather than silently patched.

## Follow-up items raised, not part of Sprint 008 scope

- `crud.count_quotes_today()`'s local-date-vs-UTC-timestamp comparison (pre-existing since Sprint 007) — should compare against a UTC `date`, not the host's local one. Not fixed here (unrelated to tenants).
- `docs/API_SPEC.md` has never documented `POST /api/v1/quotes/ai-draft` (AI Quotation Generator v1, `d306c99`) — a pre-existing gap from that sprint's docs pass, noticed but not fixed here (out of scope for a tenancy sprint).
- `docs/SYSTEM_ARCHITECTURE.md` §9's Sprint 008–016 table still reflects the original pre-SaaS-replan draft, not the newer Phase 1–9 sequence — reconciling the two is a separate, larger documentation decision, flagged in place rather than silently rewritten.
- Sprint 009 (tenant-aware authentication) is the next sprint — `users.tenant_id` becomes meaningful and `NOT NULL`, and the JWT payload gains `tenant_id`.
