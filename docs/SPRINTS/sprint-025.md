# Sprint 025 — Business Command Centre

Baseline: `main` @ `36f27ee` (Sprint 024, merged). Branch:
`sprint-025-business-command-centre`.

## Objective

Give Owners/Staff one tenant-scoped, truthful operational summary of the
business — pipeline state, quote funnel, site visits, follow-up attention,
and quoted monetary value — computed entirely from real stored rows. No
fabricated trends, no estimated conversion rates, no placeholder values.

## 1. Current-state findings (verified against `main` @ `36f27ee`)

### The existing `/dashboard` endpoint is unguarded and loosely typed

`app/api/v1/core.py`'s `GET /dashboard` takes only `get_current_user` (no
`require_role`) and returns a raw `dict`:

```python
@router.get("/dashboard")
def dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tenant_id = current_user.tenant_id
    return {
        "quotes_today": crud.count_quotes_today(db, tenant_id),
        "revenue": crud.sum_quotes_revenue(db, tenant_id),
        "customers": crud.count_customers(db, tenant_id),
        "projects": crud.count_projects(db, tenant_id),
    }
```

Added Sprint 007, tenant-scoped since Sprint 012. Any authenticated user —
Owner, Staff, or a hypothetical `role=None` — can currently call it. This
sprint does not touch this endpoint or its frontend consumer (`StatGrid`) —
out of scope, unrelated to the new Command Centre.

### `sum_quotes_revenue` mislabels a quote total as "revenue"

```python
def sum_quotes_revenue(db: Session, tenant_id: uuid.UUID) -> float:
    total = db.query(func.sum(Quote.total)).filter(Quote.tenant_id == tenant_id).scalar()
    return float(total) if total is not None else 0.0
```

Sums `Quote.total` across **every** quote regardless of status (draft or
approved). This is exactly the kind of metric the brief warns against
calling "revenue" — a draft quote is not booked business. The Command
Centre reuses this computation (it is the correct all-quotes total) but
under an honest field name, `quoted_value`, alongside a second,
status-filtered `approved_quoted_value`. The old endpoint's "Revenue" label
is pre-existing tech debt, left untouched (unrelated scope).

### Money fields are plain `Float` everywhere — no `Decimal` anywhere in this schema

`Quote.price_per_slab`, `price_before_vat`, `vat`, `total` are all plain
SQLAlchemy `Float`. No table in this schema has ever used
`Numeric`/`Decimal`. This sprint does not introduce new precision semantics
that don't already exist — new money fields use the same `Float` +
`float()` coercion pattern as `sum_quotes_revenue`, documented as an
existing, honest limitation rather than a new promise.

### `Quote.status` is a closed two-value lifecycle; handoff doesn't change it

Confirmed via `app/quotes/service.py` and a grep across `app/quotes/`:
`Quote.status` only ever takes `"draft"` (default) or `"approved"`.
`QuoteService.approve()` transitions draft → approved. `QuoteService.handoff()`
requires `status == "approved"`, creates a `Project` at `BOOKED` with
`Project.quote_id = quote.id`, and does **not** change `Quote.status` — it
stays `"approved"` forever after handoff. `Project.quote_id` is a nullable,
**unique** FK (`app/database/models.py:120`), so "quote already handed off"
is exactly `Project.quote_id IS NOT NULL` — a single indexed count, no join
needed to compute a handed-off count.

### `Project.status` is a closed 7-value pipeline, not indexed

`app/projects/models.py::ProjectStatus`: `enquiry`, `quoted`, `booked`,
`templated`, `fabricated`, `installed`, `complete`. The `projects` table
indexes `tenant_id` and `assigned_user_id` only — `status` has no index.
Given this system's actual data volumes (a handful to low hundreds of rows
per tenant), a `GROUP BY status` aggregate query over an already
tenant_id-indexed set needs no additional index. No migration this sprint.

### `Appointment.status` is a closed 3-value set, also unindexed

`app/appointments/models.py::AppointmentStatus`: `scheduled`, `completed`,
`cancelled`. Same reasoning as Project — no new index needed.

### Notifications have no existing "unread count" crud function, and are recipient/tenant scoped

`app/database/crud.py::list_notifications(db, tenant_id, user_id, limit)`
returns rows where `tenant_id` matches AND (`recipient_user_id IS NULL` OR
`recipient_user_id == user_id`) — i.e. it is scoped to what one specific
user can see. `NotificationRecord.source_type`/`source_id` (Sprint 024) are
the only structured way to know a notification is an actionable, entity-
linked one — currently `source_type` is only ever `"project"` (the stale-
enquiry follow-up automation). There is no `count_unread` function yet.

**Decision needed**: should the Command Centre's follow-up count be
per-viewing-user (personal inbox count, matching `useNotifications`) or
tenant-wide (operational "how much is outstanding across the team")? The
Command Centre is framed as a business-wide operational view, not a
personal notification list — locked below as tenant-wide, unfiltered by
recipient, filtered only by `source_type = 'project'` (the actionable kind)
and `read = false`.

### Frontend dashboard: one root route, three components, all thin

- `apps/web/app/page.tsx` — the dashboard IS the `/` route. Renders
  `DashboardStatusBar`, `StatGrid`, `RecentActivityPanel`, `QuickActions`.
- `apps/web/components/dashboard/StatGrid.tsx` — 4 `StatCard`s (Today's
  Quotes, Revenue, Customers, Projects) fed by `useDashboardStats()`.
- `apps/web/hooks/useDashboardStats.ts` — thin wrapper over the existing
  `usePolling` hook (5s interval) calling `api.getDashboardStats` (→
  `GET /dashboard`).
- `apps/web/types/dashboard.ts` — `DashboardStats` interface matching the
  old endpoint's raw dict shape exactly.
- `apps/web/_legacy/components/dashboard/Dashboard.tsx` — confirmed dead:
  grepped for any reference outside `_legacy/` itself; none found. Ignored.

Per the brief's explicit preference, the Command Centre **extends**
`app/page.tsx` with new sections below `StatGrid`, rather than creating a
new route — routing does not require a dedicated page here.

### Actionability: `/projects` and `/quotes` list pages exist; neither supports a status filter query param today

Confirmed via `apps/web/app/projects/page.tsx` and `apps/web/app/quotes/page.tsx`
— both render an unfiltered list, no `searchParams`/status-filter support.
Per the brief's explicit "do not build unsupported filter routes just to
satisfy this sprint," Command Centre section links go to the existing
plain list routes (`/projects`, `/quotes`) with no invented filter param.
There is no dedicated appointments list page and no dedicated "my
follow-ups" page, so the Site Visits and Follow-up sections are
informational only this sprint (no link), rather than inventing a
destination.

### RBAC precedent: every other business-data endpoint gates with `require_role`

`app/appointments/router.py`, `app/projects/router.py`, `app/quotes/router.py`
all use `require_role(UserRole.OWNER, UserRole.STAFF)` on every route.
There is no existing precedent anywhere in the codebase for an
Owner-vs-Staff *reduced* view of the same data — every RBAC-gated endpoint
grants identical access to both roles. The pre-existing `/dashboard`
endpoint (no RBAC at all) is the one outlier, and is explicitly not being
extended or copied.

## 2. Metric groups: computability assessment

| Group | Metric | Status |
|---|---|---|
| A. Pipeline | Count of Projects per `ProjectStatus` (7 values) | **Directly computable** — `GROUP BY status`, tenant-scoped |
| B. Quote funnel | Draft count, approved count | **Directly computable** — `GROUP BY status` |
| B. Quote funnel | Handed-off count | **Directly computable** — `COUNT(Project) WHERE quote_id IS NOT NULL` |
| B. Quote funnel | Conversion rate (draft→approved, approved→handoff) | **Deferred** — brief explicitly treats this as optional/risky; no product-defined semantics exist yet, and this sprint's smallest-useful-vertical principle argues for shipping raw counts first |
| C. Follow-up attention | Unread project-sourced notification count | **Directly computable** — `COUNT(NotificationRecord) WHERE tenant_id=X AND source_type='project' AND read=false` |
| D. Site visits | Count of Appointments per `AppointmentStatus` (3 values) | **Directly computable** — `GROUP BY status` |
| E. Business value | Quoted value (sum of all `Quote.total`) | **Directly computable** — reuses `sum_quotes_revenue`'s query, relabeled |
| E. Business value | Approved quoted value (sum where `status='approved'`) | **Directly computable** — new status-filtered SUM |
| E. Business value | Booked value (sum of `Quote.total` for handed-off quotes only) | **Partially supported, deferred** — computable via a join but adds a third money figure with unclear product value beyond "approved quoted value" (approved and handed-off quotes are usually the same money); not locked this sprint to keep the value section to two clear numbers |
| — | Any historical trend / week-over-week delta / forecast | **Impossible without new data** — no time-series snapshot table exists; explicitly not invented (NO FAKE ANALYTICS) |
| — | Customers count | **Directly computable** — reuses existing `crud.count_customers` |

## 3. Locked contract

### Endpoint

New module `app/dashboard/{models.py, service.py, router.py}`, mounted in
`app/api/v1/__init__.py` (matches every other domain's module shape — a
distinct enough concern to warrant its own module rather than growing
`core.py`). `GET /api/v1/dashboard/command-centre`. The existing
`GET /api/v1/dashboard` (`core.py`) is untouched.

### RBAC

`require_role(UserRole.OWNER, UserRole.STAFF)` — identical access for both
roles, matching the codebase-wide precedent found in §1 (no existing
"reduced Staff view" pattern to follow). `role=None` → 403 (existing
`require_role` behavior, unchanged).

### Response shape (typed Pydantic, no raw dicts)

```python
class PipelineCounts(BaseModel):
    enquiry: int
    quoted: int
    booked: int
    templated: int
    fabricated: int
    installed: int
    complete: int

class QuoteFunnel(BaseModel):
    draft: int
    approved: int
    handed_off: int

class QuotedValue(BaseModel):
    quoted_value: float
    approved_quoted_value: float

class SiteVisitCounts(BaseModel):
    scheduled: int
    completed: int
    cancelled: int

class FollowUpAttention(BaseModel):
    unread_follow_ups: int

class CommandCentreResponse(BaseModel):
    customers: int
    pipeline: PipelineCounts
    quotes: QuoteFunnel
    value: QuotedValue
    site_visits: SiteVisitCounts
    follow_up: FollowUpAttention
```

### Metric semantics (exact)

- `pipeline.*` — count of tenant's Projects currently in that status.
  All 7 keys always present, 0 if none.
- `quotes.draft` / `quotes.approved` — count of tenant's Quotes by status.
- `quotes.handed_off` — count of tenant's Projects where `quote_id IS NOT NULL`
  (i.e. quotes that have produced a booked Project). Not a subset
  arithmetic of draft/approved shown in the UI as a running total — it's
  its own independently-queried count, documented as such so it's never
  mistaken for `quotes.approved - <something>`.
- `value.quoted_value` — `SUM(Quote.total)` across every quote regardless
  of status (drafts included). Never labeled "revenue" anywhere in the
  API or UI.
- `value.approved_quoted_value` — `SUM(Quote.total)` where `status = 'approved'`.
  Still not "revenue" — an approved quote is a committed price, not
  recognized income; UI labels it "Approved quote value."
- `site_visits.*` — count of tenant's Appointments by status.
- `follow_up.unread_follow_ups` — count of tenant's `NotificationRecord`
  rows where `source_type = 'project'` and `read = false`. Tenant-wide
  (not scoped to the viewing user) — an operational "how much is
  outstanding" figure, not a personal inbox count.
- `customers` — reuses `crud.count_customers` verbatim.

### Time window

All-time totals only. No 30-day (or other) recent window this sprint.
Reasoning: every relevant entity already has a trustworthy `created_at`
(or `scheduled_at`/`timestamp`), so a window is technically easy to add,
but it would double the metric surface (every group needs an "all-time"
and a "recent" figure) for a recency concept the user has not asked for.
Deferred as a follow-up rather than default-bundled into the first
Command Centre pass.

### Query / index strategy

Six aggregate queries total, all tenant-scoped, all using existing indexes
on `tenant_id`:

1. `SELECT status, COUNT(*) FROM projects WHERE tenant_id=:t GROUP BY status`
2. `SELECT status, COUNT(*) FROM quotes WHERE tenant_id=:t GROUP BY status`
3. `SELECT COUNT(*) FROM projects WHERE tenant_id=:t AND quote_id IS NOT NULL`
4. `SELECT status, COUNT(*) FROM appointments WHERE tenant_id=:t GROUP BY status`
5. `SELECT SUM(total) FROM quotes WHERE tenant_id=:t` +
   `SELECT SUM(total) FROM quotes WHERE tenant_id=:t AND status='approved'`
6. `SELECT COUNT(*) FROM notifications WHERE tenant_id=:t AND source_type='project' AND read=false`
   + `crud.count_customers` (existing)

No per-row Python loops, no N+1 pattern — every count/sum is one SQL
aggregate. No new indexes, no migration.

### Tenant isolation

Every query above filters by `tenant_id` explicitly (from
`current_user.tenant_id`, never a request parameter). Cross-tenant
regression test asserts Tenant A's response contains none of Tenant B's
counts, using isolated per-test tenant fixtures (not the shared seeded
tenant — Sprint 024's lesson).

### Empty-state contract

A brand-new tenant with zero rows in every table gets `200` with every
count `0` and every value `0.0` — falls out naturally from `COUNT`/`SUM`
over an empty set (`SUM` coalesced to `0.0`, same pattern as the existing
`sum_quotes_revenue`). No division anywhere in this design (conversion
rates deferred), so no div-by-zero risk exists.

### Frontend contract

Extends `apps/web/app/page.tsx` (no new route) with a new section below
the existing `StatGrid`, built from new components under
`apps/web/components/dashboard/command-centre/`: a pipeline summary (7
counts, small bar or count list), a quote funnel summary (draft/approved/
handed-off + the two value figures), a site-visits summary (3 counts), and
a follow-up attention card. Reuses `Card`/`Badge`/existing Tailwind
conventions — no charting library. New hook `useCommandCentre()` mirrors
`useDashboardStats()`'s `usePolling` pattern. Pipeline and Quote Funnel
section headers link to `/projects` and `/quotes` respectively (plain
routes, no filter param — see §1); Site Visits and Follow-up sections are
informational only (no destination page exists yet).

Loading/error/empty states: loading → skeleton (matches `StatCardSkeleton`
convention); error → real error state via the existing
`DashboardStatusBar`-style treatment, never a silently-zeroed card;
empty (valid 200, all zeros) → renders the real zeros, visually
indistinguishable from "healthy but quiet," which is correct — it is not
a failure state.

### Explicitly out of scope this sprint

- Conversion-rate percentages (draft→approved, approved→handoff).
- Booked value as a third money figure.
- Any 30-day/recent time window.
- Per-user (as opposed to tenant-wide) follow-up count.
- Any chart/trend/history — no time-series data exists to back one.
- Modifying the pre-existing `/dashboard` endpoint or its "Revenue" label.

## 4. Locked TDD sequence

1. Backend RED — tenant-scoped pipeline counts, multi-tenant fixture
   proving cross-tenant exclusion.
2. Backend GREEN — response models, `app/dashboard/service.py`, router,
   the 6 aggregate queries.
3. Metric-by-metric TDD — one focused test per locked field (quotes
   funnel, value figures, site visits, follow-up, customers).
4. RBAC tests — Owner and Staff both 200; `role=None` 403 (or no-token 401
   per existing convention).
5. Empty-state test — fresh tenant, all zeros, 200.
6. Frontend RED/GREEN — command-centre sections render real API data;
   loading/error/empty states.
7. True Playwright E2E — controlled dataset (known Project statuses,
   known Quote states, one Appointment, one unread project-sourced
   notification), exact assertions, cross-tenant absence, reload
   persistence, live API cross-check.

## 5. End-to-end delivery closeout

### Git history

- Baseline: `main` @ `36f27ee` (Sprint 024, merged).
- Branch: `sprint-025-business-command-centre`.
- Discovery commit: `e255989` — `docs: define Sprint 025 business command centre`.
- Contract-lock commit: `c0fa0f7` — `docs: lock Sprint 025 command centre contract`.
- Backend RED: `b34fb5a`. Backend GREEN: `2ca0cdb`. Remaining backend
  metric/RBAC/empty-state tests: `ac5faf1`.
- Frontend GREEN: `f65144f`.
- Pre-existing bug fix found by this sprint's E2E: `a0722d4` — `fix: cover
  the full ActivityType enum in dashboard icon/tone maps`.
- True E2E: `5a0ff8b`.
- Final feature HEAD before this closeout commit: `5a0ff8b`.
- PR: sprint-025-business-command-centre → main (opened after this commit).
- Merge SHA: recorded below once merged.
- `origin/main` post-merge: recorded below once merged.

### Command Centre

- Endpoint: `GET /api/v1/dashboard/command-centre`, new module
  `app/dashboard/{models,service,router}.py`, mounted in
  `app/api/v1/__init__.py`. The pre-existing `GET /api/v1/dashboard`
  (`app/api/v1/core.py`) is untouched.
- Metric groups delivered: pipeline (7-value Project status counts),
  quote funnel (draft/approved/handed-off counts), business value
  (quoted value, approved quoted value), site visits (3-value Appointment
  status counts), follow-up attention (tenant-wide unread project-sourced
  notification count), customers (reused existing `crud.count_customers`).
- Time window: all-time totals only, as locked in §3 — no recent-window
  metric was built.

### Metric semantics

- Definitions match §3's locked contract exactly (`quotes.handed_off` is
  an independent count of `Project.quote_id IS NOT NULL`, not derived
  arithmetic; `value.quoted_value`/`value.approved_quoted_value` are
  never labeled "revenue").
- Deferred/unsupported this sprint (documented in §2/§3, not built):
  conversion-rate percentages, a third "booked value" money figure, any
  30-day/recent window, per-user (as opposed to tenant-wide) follow-up
  scoping, any chart/trend/history.
- Money handling: reuses the existing plain-`Float` + `float()` coercion
  pattern from `sum_quotes_revenue` — no new Decimal precision semantic
  introduced; documented as an existing, honest limitation.
- Conversion calculations: none built this sprint (see deferred list
  above).

### Security

- Tenant isolation: every crud aggregate filters by `tenant_id` from
  `current_user.tenant_id`. Backend regression
  (`test_pipeline_counts_are_exact_and_tenant_scoped`) and staging
  verification (a second synthetic tenant) both confirm Tenant A's
  counts never appear in Tenant B's response.
- RBAC: `require_role(OWNER, STAFF)` — confirmed identical 200 access for
  both roles (`test_owner_and_staff_can_both_access_command_centre`),
  `role=None` → 403 (`test_role_none_is_forbidden`). On staging,
  no-token/invalid-token access confirmed 401 (existing `get_current_user`
  behavior); a true `role=None` re-test was not performed directly on
  staging (would require a direct DB row edit via SSH for a state the
  invitation flow doesn't produce) — this is the same code path already
  covered by the backend test and full local regression, so it was not
  re-verified independently on staging.

### Backend

- Query strategy: 6 aggregate SQL queries per request (2 `GROUP BY status`
  counts for Projects and Quotes, 1 count for Appointments, 1 indexed
  count for handed-off Projects, 2 `SUM` queries for the two value
  figures, 1 count for unread follow-ups, plus the existing
  `count_customers`) — no per-row Python loops, no N+1 pattern. Staging
  server-side timing for `GET /dashboard/command-centre` across 3 real
  requests: 11.7ms, 13.8ms, 15.8ms.
- Indexes/migration: none added. `tenant_id` was already indexed on every
  table involved; `status` columns are unindexed but the query is a
  single `GROUP BY` over an already tenant-scoped set, and this system's
  real data volumes give no evidence a new index is needed (documented
  reasoning in §1/§3, per the brief's "do not add indexes without
  evidence" instruction).
- Empty-state: verified both in the backend test suite
  (`test_empty_tenant_gets_all_zeros_not_nulls_or_500`) and implicitly on
  staging (Tenant B's fresh signup returned real zeros for every
  metric it hadn't populated, e.g. `quotes`/`value`/`site_visits`).

### Frontend

- Route: extends the existing dashboard (`apps/web/app/page.tsx`, the
  `/` route) — no new route created, per the locked contract.
- Cards/sections: `CommandCentrePanel` renders Pipeline, Quote Funnel
  (+ value figures), Site Visits, and Follow-up Attention as four cards
  below the existing `StatGrid`. Pipeline/Quote Funnel headers link to
  the existing `/projects`/`/quotes` list pages (no invented filter
  routes); Site Visits/Follow-up have no destination link since no
  dedicated page exists yet for either.
- Loading state: 4 skeleton cards, matching `StatCardSkeleton`'s visual
  convention.
- Error state: a real error banner ("Couldn't load the Business Command
  Centre") when the API call fails and no prior data exists — never a
  silently-zeroed card.
- Empty state: renders real zeros (visually normal, not an error) —
  confirmed both by a dedicated Vitest test and by Tenant B's staging
  render.
- Navigation/actionability: verified in the true E2E and in the manual
  staging browser session — "View projects"/"View quotes" links render
  and the Follow-up Attention badge shows the exact unread count.

### Tests

- Backend: 7 new tests in `tests/test_command_centre.py`, all passing.
  Full local backend regression (all 30 test files, batched into 3
  groups per this session's established resource-contention workaround):
  82 + 118 + 214 = 414 passed, 1 skipped. One isolated intermittent
  failure was observed once in `test_follow_up_automation.py` during
  batch reruns and did not reproduce on two subsequent identical
  reruns of the same batch (including with `test_command_centre.py`
  present) — treated as a pre-existing local flake consistent with this
  session's documented resource-contention pattern, not a Sprint 025
  regression.
- Frontend: 3 new tests in `CommandCentrePanel.test.tsx`, plus 18 new
  tests in `lib/activity.test.ts` (the ActivityType coverage fix). Full
  local Vitest regression: 49/49 passed. `tsc --noEmit` clean. `eslint`
  clean. `test:runtime-config` (7/7) and `test:docker-contract` (5/5)
  node tests clean. Production build (`next build`) clean.
- Playwright: 1 new true E2E spec
  (`e2e/business-command-centre.spec.ts`), run twice locally to confirm
  determinism (both passed). Full local Playwright regression (all 6
  specs): 6/6 passed.
- Alembic: `alembic heads` = `2243d66f83da (head)` (unchanged from
  Sprint 024 — no migration this sprint). `alembic check`: "No new
  upgrade operations detected." `git diff --check origin/main...HEAD`:
  clean.
- Feature CI (GitHub Actions, commit `5a0ff8b`): backend, frontend, and
  e2e checks all green.

### Staging

- Deployed SHA: `5a0ff8b` (clean `git archive` export, deployed
  separately to `simo-api-staging` and `simo-web-staging` per the
  established clean-commit technique).
- `/health` = 200, `/ready` = 200, web root = 200.
- Alembic hard schema gate: staging `alembic current` =
  `2243d66f83da (head)`, exactly matching the local `alembic heads` value
  for the deployed commit — no drift, verified via
  `railway ssh -- alembic current` per the mandatory gate.
- Controlled dataset: a fresh synthetic tenant/Owner with 4 Projects (2
  enquiry — one of which was pushed 8 days stale to trigger the real
  follow-up automation via `railway ssh -- python -m app.jobs.follow_up
  --now ...`, 1 quoted, 1 booked via a real quote handoff), 4 Quotes (2
  draft, 2 approved, 1 of the approved ones handed off), 3 Appointments
  (1 scheduled, 1 completed, 1 cancelled), 1 Customer, recorded via the
  live API before opening the browser: `{"customers":2,"pipeline":
  {"enquiry":2,"quoted":1,"booked":1,...0},"quotes":{"draft":2,
  "approved":2,"handed_off":1},"value":{"quoted_value":4800.0,
  "approved_quoted_value":2400.0},"site_visits":{"scheduled":1,
  "completed":1,"cancelled":1},"follow_up":{"unread_follow_ups":2}}`.
- Real browser (isolated tab, `localStorage` checked clean before login
  and cleared after): logged in as the synthetic Owner through the real
  `/login` UI, the Business Command Centre rendered every figure above
  exactly (Pipeline, Quote Funnel + £4,800/£2,400 value figures, Site
  Visits, "2 unread" Follow-up Attention). Reload confirmed the same
  values persisted (real server data, not client state).
- Tenant isolation: a second synthetic Tenant B, checked via the live
  API, showed only its own 1 Project and zero of Tenant A's
  customers/quotes/site-visits/value — confirmed on staging, not just
  locally.
- Staging security: role=None re-verification not performed directly on
  staging (see Security section above); unauthenticated/invalid-token
  access confirmed 401.
- Smoke suite (`scripts/staging/smoke.py`): 16 passed, 0 failed, 6
  blocked — identical pattern to the Sprint 020 baseline; all 6 blocked
  gates are the same pre-existing, operator-authorization-gated items
  (migration-evidence cross-check, seed-inventory comparison, restart
  persistence, log request-ID mechanism, local-only secret scan, backup
  restore drill) — no new blocks or failures introduced by Sprint 025.
- Performance sanity: 3 real `GET /dashboard/command-centre` requests
  logged server-side at 11.7ms/13.8ms/15.8ms — consistent with the
  6-fixed-aggregate-query design; no evidence of N+1 behavior.

### Limitations / technical debt (not blocking this sprint)

- The pre-existing `GET /dashboard` endpoint (`app/api/v1/core.py`) still
  has no RBAC gate and still labels an all-quotes sum "revenue" — left
  untouched as explicitly out of scope; the new Command Centre uses
  honest labels instead.
- Conversion-rate metrics, a "booked value" figure, and a recent-window
  metric are deferred (see §2/§3) — no product-defined semantics existed
  for them yet, and building them would have doubled the metric surface
  without a stated need.
- `role=None` was not independently re-verified against the deployed
  staging commit (only against local/CI); the code path is identical and
  already covered there.

### Production safety

- Production deployed: no (0 services, confirmed via
  `mcp__railway__get-status` both before and after this sprint's work).
- Production DB touched: no.
- Production config changed: no.
- Unrelated files included: no (diff reviewed — only files listed above).
- Force push used: no.

### Status

Sprint 025 backend/frontend/tests/staging work is complete pending: PR
open + merge, post-merge main CI verification, and this section's final
Git/Status fields. Sprint 025 is CLOSED once those are recorded below.

**Do NOT deploy production. Do NOT start Sprint 026 until Sprint 025 is
CLOSED.**
