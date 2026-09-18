# Sprint 043 — GeoCore Premium OS Plan 04: Job Financials + Variations

**Branch:** `sprint-043-job-financials-variations`
**Base:** `origin/main` @ `25857e704aa6b4bd096e31bb078d41a04d629d1f` (Plan 03 merge, PR #44)
**Alembic head at branch point (verified, not assumed):** `709c9ed313cc`
**Alembic head after this sprint:** `1a2b3c4d5e6f`
**Status:** CODE-COMPLETE — not deployed, not merged

---

## 1. Mission

Build GeoCore's first real project commercial-control layer — the chain
`Original Quote / Base Contract → Approved Contract → Internal Costs →
Variations → Current Contract Value → Forecast Cost → Margin / Profitability`
— trade-neutral across every supported trade, never mixing customer selling
price with internal cost, never fabricating a figure GeoCore cannot honestly
compute, and never double-counting a variation's commercial impact.

Authoritative sources, in priority order: the Master Spec
(`2026-09-17-geocore-premium-os-design-v3.md`), the Implementation Roadmap
(`2026-09-17-geocore-premium-os-implementation-roadmap.md`), then existing repo
contracts/tests as the compatibility authority. Plan 05 and every later roadmap
phase are explicitly out of scope for this sprint.

---

## 2. What was built, commit by commit

1. **`feat(financials): add tenant-scoped project cost ledger + contract/profitability summary`
   (includes the variations domain — implemented together)** — migration
   `1a2b3c4d5e6f` (parent `709c9ed313cc`): `project_cost_entries`, `variations`,
   `variation_items` (all purely additive, no existing table touched).
   `app/financials/` (models/service/router): `budgeted_cost`/`committed_cost`/
   `actual_cost`/`forecast_cost`, `base_contract_value`/`base_contract_source`/
   `approved_variations_total`/`current_contract_value`, `forecast_gross_profit`/
   `forecast_gross_margin_percent`/`actual_gross_profit`/
   `actual_gross_margin_percent`/`margin_risk` — every guard from Task 11-12
   implemented and unit tested as pure functions. `app/variations/`
   (models/service/router/pdf): sequential per-project reference numbering
   (`V-001`, `V-002`, …), totals/VAT computed by directly reusing
   `app/quotes/general.py::price()`, a `draft → sent → approved/rejected/void`
   state machine with idempotent approval (ADR-048), and a tenant-branded PDF
   reusing `app/tenants/identity.py` and `app/quotes/pdf.py`'s helpers.
   Extends `ActivityType`, the automation trigger registry, `subjects.py` and
   `dispatcher.py` with `variation.created/sent/approved/rejected`,
   `cost.added`, `margin_risk.detected` — commercial writes commit first,
   automation dispatch (which can never raise) happens after.
2. **`feat(dashboard): surface contract and margin signals on Command Centre`**
   — `FinancialSignals` on `CommandCentreResponse`: approved contract value,
   approved variations value, and counts of projects with a contract, margin
   risk or missing cost data — scoped to projects with a real base contract
   only, computed via a documented, deliberate exception to the dashboard's
   usual one-query-per-figure convention.
3. **`feat(dashboard): surface contract and margin signals`** (frontend) — a
   "Contract & Margin" Command Centre card using the new `FinancialSignals`
   type, with precise labelling (never a company-wide margin percentage).
4. **`feat(projects): add Financials and Variations to Project 360`** —
   `ProjectFinancialsPanel`/`ProjectVariationsPanel`, gated behind the same
   Owner/Staff RBAC as Schedule/Team; Contract Summary, Cost Summary
   (`cost_data_status` badge), Profitability (forecast vs. actual kept
   visually distinct, margin-risk badge, "Forecast based on recorded costs"
   note on incomplete data), Cost Breakdown with add/delete, and a Variations
   workspace (create draft → add items → send → approve/reject/void →
   download PDF, only the actions valid for the current status ever shown).
   10 new component tests.
5. **`test(dashboard): update pre-existing regression tests for new financial
   signals`** — `test_meta_lists_every_trigger_with_its_kind` and
   `test_empty_tenant_gets_all_zeros_not_nulls_or_500` hard-coded the exact
   pre-Plan-04 trigger count and `CommandCentreResponse` shape; updated to the
   new counts/shape, same never-null empty-state contract.
6. **`test(financials): verify project commercial journeys end-to-end`** — 5
   Playwright E2E journeys (A-F, with B+C combined into one test since C
   directly extends B's variation) through the real browser, Next.js app and
   FastAPI server.

---

## 3. Core financial rules, as implemented

- **Cost states** (`app/financials/models.py`): `budgeted` (planned, not yet
  committed), `committed` (contractually ordered, not necessarily paid),
  `actual` (incurred/recognised). A cost item is one row, edited in place as
  it graduates between states — never duplicated per stage. `forecast_cost =
  budgeted_cost + committed_cost + actual_cost`, safe from double-counting
  because of that one-row design, documented as a deliberately simple rule
  rather than a lineage-aware reconciliation engine (ADR-049).
- **Cost categories**: `material`, `labour`, `subcontractor`, `plant`,
  `transport`, `other` — a closed vocabulary validated at the Pydantic
  boundary.
- **Base contract value** (ADR-047): the project's linked, handed-off
  (therefore already-approved) quote's `total`, and nothing else — never the
  mutable `Project.estimated_value`, never a guessed zero. `None` when no
  quote is linked.
- **Current contract value** (ADR-048): always *derived* —
  `base_contract_value + SUM(total) over approved variations` — never
  maintained by incrementing a counter. This is what makes variation
  approval idempotent by construction.
- **Variation lifecycle**: `draft` (fully editable) → `sent` (items/title
  locked) → `approved`/`rejected`/`void` (all terminal). A correction is a
  new, separate variation, never a rewrite of an approved one.
- **Profitability** (ADR-049): `Gross Profit = Current Contract Value −
  Forecast Cost`; `Gross Margin % = Gross Profit / Current Contract Value ×
  100`. `None` on any missing contract, zero/negative contract, or zero cost
  entries — never a fabricated figure. `forecast_*` and `actual_*` are kept
  visually and semantically distinct throughout.
- **`cost_data_status`** (`none`/`partial`/`complete`): `none` with zero cost
  entries, `complete` only once the project's own workflow reaches its
  `completed` role (the one honest "no more costs are coming" signal GeoCore
  has), `partial` otherwise — surfaced alongside every forecast figure.
- **Margin risk**: `margin_risk = true` only when current contract value,
  forecast cost data, and a known forecast margin all exist, and that margin
  is below the documented conservative default `MARGIN_RISK_THRESHOLD_PERCENT
  = 15.0` (ADR-049) — never inferred from partial or missing data, and never
  a tenant-configurable policy this sprint invented.

---

## 4. Workflow, RBAC and tenant isolation

- **Workflow integration**: the workflow engine remains the sole authority
  for a project's operational stage. Nothing in `app/financials/` or
  `app/variations/` writes `Project.status`, `workflow_stage_id` or any
  workflow column — verified by direct search, not assumption. A variation
  may be created, sent, approved, rejected or voided at any workflow stage
  without forcing a stage transition.
- **RBAC**: every financials/variations read and write is gated
  `require_role(UserRole.OWNER, UserRole.STAFF)`, the same gate quotes,
  projects and appointments already use — `UserRole` has only `OWNER`/
  `STAFF`, so there is no third role to test a boundary against. Internal
  cost/margin data is hidden from the frontend behind the same gate the
  Schedule/Team tabs already use.
- **Activity visibility**: `PROJECT_COST_ADDED/EDITED/DELETED` and
  `VARIATION_CREATED/SENT/APPROVED/REJECTED/VOIDED` are recorded to the
  internal `ActivityLog` only — verified that `app/portal/` never reads
  `ActivityLog` at all, only ever writing its own specific portal-view event
  types, so no cost or variation detail can leak to a customer-facing portal
  view.
- **Tenant isolation**: every cost/variation lookup is scoped by
  `tenant_id`, returning a clean 404 (never a leak of existence) for a
  cross-tenant id — proven by `tests/test_job_financials.py`'s tenant
  isolation tests (cost CRUD + summary, variation read/approve) and
  `e2e/job-financials-variations.spec.ts`'s Journey E through both the API
  and the real Project 360 page.

---

## 5. Verification

### Backend

```
1213 passed, 3 skipped
```
Full `pytest -q` run, including the new `tests/test_job_financials.py` (26
tests: pure calculation coverage, cost CRUD + state aggregation, tenant
isolation, sequential variation numbering, VAT rounding parity with general
quotes, the approval-idempotency regression proven three ways, approved-
variation immutability, and a general-quoting regression check) and the two
updated pre-existing regression tests (`test_automations.py`,
`test_command_centre.py`). The 3 skips match the pre-existing baseline.

### Frontend

```
Test Files  35 passed (35)
     Tests  220 passed (220)
```
`pnpm test -- --run`, `pnpm exec tsc --noEmit`, `pnpm exec eslint .`, and
`pnpm build` all clean. 10 new component tests
(`ProjectFinancialsPanel.test.tsx`, `ProjectVariationsPanel.test.tsx`) plus
the extended `CommandCentrePanel.test.tsx`.

### E2E

```
55 passed (50 pre-existing + 5 new)
```
`e2e/job-financials-variations.spec.ts` — Journeys A (cost roll-up), B+C
(variation approval + idempotent retry), D (margin recalculation), E (tenant
isolation), F (stone regression) — run against the real browser, real
Next.js dev server and real FastAPI server, no mocking.

### Alembic

- `alembic heads` / `alembic current`: single head, `1a2b3c4d5e6f`.
- `alembic check`: reports drift, but **every flagged item is pre-existing
  and unrelated to this sprint** — `email_verification_tokens`,
  `password_reset_tokens`, `processed_stripe_events`,
  `project_workflow_history`, `projects.workflow_template_id/
  workflow_stage_id`, `quote_items.created_at`, `subscriptions`,
  `workflow_templates` — none of which this sprint's migration touches (it
  only creates `project_cost_entries`, `variations`, `variation_items`).
  This drift exists on `origin/main` before this branch and is out of this
  sprint's scope to fix.

### Migration safety

Purely additive: three new tables, zero `ALTER` statements on any existing
table, zero rewritten rows. A pre-Plan-04 project has zero cost entries and
zero variations, and its Financials tab shows "No costs recorded yet" rather
than a fabricated zero.

---

## 6. Known limitations

- **Customer-facing variation visibility (Task 15's optional stretch)**:
  deferred. GeoCore's portal architecture (`app/portal/`) is read-only in a
  specific, narrow shape (documents, messages, quote status) and extending
  it to surface variation status would be a materially larger, separate
  piece of work rather than a safe reuse of the existing pattern — noted here
  as later work, not attempted in this sprint.
- **Cost lineage**: `project_cost_entries` has no explicit link between a
  budgeted row and the committed/actual row it becomes if a fabricator
  chooses to add a new row per stage instead of editing one in place — the
  forecast-cost sum assumes the one-row-per-cost-item convention the UI
  guides toward, but does not enforce it at the database level (ADR-049).
- **Margin-risk threshold is fixed, not tenant-configurable** — a
  documented, conservative internal default (15%), not a business policy a
  tenant can adjust. Natural next step, not built here.

---

## 7. What was explicitly not done

Per the governing instructions: production was never deployed to, Plan 05
was never started, no pricing/Stripe/trial model was touched, no historical
commercial record was rewritten, and no second VAT/tax engine was built —
variation pricing reuses `app/quotes/general.py::price()` directly.
