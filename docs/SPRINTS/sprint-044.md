# Sprint 044 — GeoCore Premium OS Plan 05: Procurement + Materials Operations

**Branch:** `sprint-044-procurement-materials-operations`
**Base:** `origin/main` @ `18766af2802be17b60a47616cd178832a72ec45e` (Plan 04 merge, PR #45)
**Alembic head at branch point (verified, not assumed):** `1a2b3c4d5e6f`
**Alembic head after this sprint:** `3c4d5e6f7a8b`
**Status:** CODE-COMPLETE — not deployed, not merged

---

## 1. Mission

Build GeoCore's operational Procurement + Materials layer — the chain
`Project → Material Requirement → Supplier / Source → Purchase Order →
Ordered → Part Received → Fully Received → Allocated to Project → Used /
Closed` — trade-neutral across Stone and general Construction, integrating
with (never duplicating) Plan 03's Master Catalogue and Plan 04's Project
Cost Ledger, and deliberately never becoming a full warehouse ERP.

Authoritative sources, in priority order: the Master Spec
(`2026-09-17-geocore-premium-os-design-v3.md`), the Implementation Roadmap
(`2026-09-17-geocore-premium-os-implementation-roadmap.md`), then existing
repo contracts/tests. Plan 06 and every later roadmap phase are explicitly
out of scope for this sprint.

---

## 2. What was built, commit by commit

1. **`feat(procurement): add project material requirements + purchase order
   lifecycle`** — migration `2b3c4d5e6f7a` (parent `1a2b3c4d5e6f`): seven new
   tables (`project_material_requirements`, `tenant_supplier_accounts`,
   `purchase_orders`, `purchase_order_items`, `purchase_receipts`,
   `purchase_receipt_items`, `project_material_allocations`), plus nullable
   `purchase_order_id`/`purchase_order_item_id` columns on the existing
   `project_cost_entries`. `app/procurement/` (models/service/router/pdf):
   pure-function status derivation (`derive_po_status`, `is_po_late`,
   `next_requirement_status`), a `draft → approved → ordered →
   partially_received → received / cancelled` PO lifecycle, over-receipt
   rejection validated for every line before any row is written, committed
   cost creation on approval and its idempotent-by-construction guard,
   full-receipt-flips-committed-to-actual-in-place, sequential per-tenant
   PO numbering, VAT totals reusing `app/quotes/general.py::price()`, and a
   tenant-branded PDF. 28 backend tests.
2. **`feat(workflows): enforce real procurement gate on stone fabrication`**
   — migration `3c4d5e6f7a8b` (data-only): seeds the system `stone_v1`
   template's `fabrication` stage with a real `materials_ready` gate.
   `MaterialsReadyGate` (`app/workflows/gates.py`) blocks only when the
   project has an outstanding requirement — never when it has zero.
3. **`feat(dashboard): surface procurement attention signals on Command
   Centre`** (backend) — `ProcurementSignals`: materials required, POs
   awaiting approval/ordered, late deliveries, materials due this week, and
   projects genuinely blocked by an unmet gate (a real per-project
   `evaluate_stage_gates()` call, the same documented exception to the
   dashboard's O(1)-queries convention Plan 04's margin-risk signal uses).
4. **`feat(dashboard): surface procurement attention signals`** (frontend)
   — a "Procurement" Command Centre card using the new signals.
5. **`feat(projects): add Materials tab to Project 360`** —
   `ProjectMaterialsPanel`: requirement create/cancel, PO create/approve/
   mark-as-ordered/cancel/download PDF, and recording deliveries against an
   ordered PO — every status always the backend's own derived state. 7
   component tests.
6. **`docs: document Plan 05 procurement schema and architecture
   decisions`** — the Sprint 044 section of `DATABASE_SCHEMA.md`, and
   ADR-050 (per-tenant PO numbering), ADR-051 (the committed/actual V1
   partial-receipt rule) and ADR-052 (the gate/signal honesty rule).
7. **`feat(catalogue): add "Add to project requirement" action`** — a
   catalogue surface (with its selected variant) can be sent straight to a
   project's material requirements from the Master Catalogue page.
8. **`feat(procurement): suggest material requirements from quotes and
   variations`** — a project's handed-off quote and its approved variations
   each surface a "Suggested from quote & variations" list on the Materials
   tab; nothing is created until the user presses the button for that
   specific line — never automatically (Task 35's "never auto-purchase"
   rule).
9. **`fix(procurement): show a real message on an over-receipt
   rejection`** — the record-delivery 409 was falling through to a generic
   message; matched the existing friendly-message-on-409 pattern.
10. **`test(e2e): allow a local Chromium executable override for
    Playwright`** — an opt-in, env-var-gated addition with no effect unless
    a developer's own environment sets it.
11. **`test(procurement): verify purchasing and delivery journeys
    end-to-end`** — 7 Playwright E2E journeys (A-G) through the real
    browser, Next.js app and FastAPI server.

---

## 3. Core procurement rules, as implemented

- **Requirement lifecycle** (`app/procurement/models.py`): `planned →
  required → ordered → partially_received → received → allocated →
  consumed`, or `cancelled` from any non-terminal state. Forward-only:
  `next_requirement_status` never regresses a requirement, and a
  requirement in a terminal state is never touched again.
- **PO lifecycle**: `draft` (fully editable) → `approved` (pricing locked,
  committed cost created) → `ordered`/`partially_received`/`received`
  (always **derived** from receipt data via `derive_po_status`, never set
  directly) → `cancelled` (reachable from any non-terminal status, reverses
  committed — never actual — cost).
- **Supplier identity is never duplicated**: `tenant_supplier_accounts`
  extends Plan 03's global `catalogue_suppliers` with a tenant-private
  commercial profile, the same "global identity / tenant-private
  commercial data" split `tenant_catalogue_overrides` already established
  (ADR-050 covers why PO numbering is per-tenant, not per-project, given a
  PO's `project_id` is nullable).
- **Over-receipt is rejected by default**: every line of a receipt is
  validated against `already_received + attempted > ordered` before any
  row is written — a rejected receipt never partially applies
  (`tests/test_procurement.py`'s dedicated tests, both single-call and
  cumulative-across-calls).
- **Financial integration** (ADR-051): approving a PO creates exactly one
  `committed` cost entry per item (guarded by an existence check on
  `purchase_order_item_id`, idempotent under retry — service-layer and
  HTTP alike); a full receipt flips that same row to `actual` in place,
  never a second row; a partial receipt deliberately leaves the full
  committed amount in place until the item is completely received (the
  documented V1 simplification, since `project_cost_entries` has no
  cross-row lineage to reconcile against); cancelling a PO deletes its
  committed (never actual) cost entries.
- **A `materials_ready` workflow gate** (ADR-052) blocks only when the
  project has a requirement in `{planned, required, ordered,
  partially_received}` — never when it has zero requirements — and the
  Command Center's `projects_blocked_by_materials` signal runs the exact
  same real gate evaluation, so the dashboard and the enforcement mechanism
  can never disagree about what "blocked" means.
- **Lead time is advisory only**: sourced solely from Plan 03's
  `tenant_catalogue_overrides.lead_time_days` — no second lead-time field,
  nothing computed from historical delivery data.
- **Quote/variation → procurement is assistance, never automation**: a
  project's quote items and approved variation items are surfaced as
  suggestions; each becomes a real material requirement only when the user
  presses "Send to procurement" for that specific line.

---

## 4. Workflow, RBAC and tenant isolation

- **Workflow integration**: the workflow engine remains the sole authority
  for a project's operational stage. The only workflow-side addition is the
  `materials_ready` gate type itself and its one real seed on `stone_v1`'s
  Fabrication stage — nothing in `app/procurement/` writes a workflow
  column directly.
- **RBAC**: every procurement read and write is gated
  `require_role(UserRole.OWNER, UserRole.STAFF)`, the same gate Plan 04's
  financials/variations already use — `UserRole` has only `OWNER`/`STAFF`.
- **Activity visibility**: `MATERIAL_REQUIREMENT_*`/`PURCHASE_ORDER_*`/
  `MATERIAL_ALLOCATED` are recorded to the internal `ActivityLog` only —
  the portal never reads it.
- **Tenant isolation**: every requirement/PO/receipt/allocation/supplier-
  account lookup is scoped by `tenant_id`, returning a clean 404 for a
  cross-tenant id — proven by `tests/test_procurement.py`'s dedicated
  tenant-isolation test and Journey E's real-browser + real-API coverage.

---

## 5. Verification

### Backend

```
1244 passed, 3 skipped
```
Full `pytest -q` run, including the new `tests/test_procurement.py` (29
tests: pure calculation coverage, material requirements, purchase orders —
sequential numbering, VAT totals, draft-editable/approved-locked, ordering
— receipts — partial-then-remaining, over-receipt rejection, requirement
status sync — the five financial-integration tests (idempotent committed
cost under retry, full receipt flips in place, partial receipt leaves the
committed amount unchanged, cancellation removes committed cost, a
project-less PO never touches project financials), allocations, tenant
isolation, late-delivery filtering, general-quoting regression, and Command
Center signal honesty) plus `tests/test_workflows.py`'s two new gate tests
and the updated `tests/test_automations.py`/`tests/test_command_centre.py`
regression tests. The 3 skips match the pre-existing baseline.

### Frontend

```
Test Files  36 passed (36)
     Tests  229 passed (229)
```
`pnpm test -- --run`, `pnpm exec tsc --noEmit`, `pnpm exec eslint .` all
clean. New component tests: `ProjectMaterialsPanel.test.tsx` (8, including
the quote-suggestion flow), the extended `CommandCentrePanel.test.tsx`, and
`app/catalogue/page.test.tsx`'s new "Add to project requirement" test.

### E2E

```
7 passed (49.7s)
```
`e2e/procurement-materials-operations.spec.ts` — Journeys A (Stone
Procurement), B (Construction Procurement), C (Partial Delivery), D
(Over-Receipt Safety), E (Tenant Isolation), F (Financial Integration,
including the retried-approval regression), G (Workflow Gate) — run
against the real browser, real Next.js dev server and real FastAPI server,
no mocking. Full-suite regression run (all pre-existing specs plus this
one) confirmed separately — see closeout report.

### Alembic

- `alembic heads` / `alembic current`: single head, `3c4d5e6f7a8b`.
- Two migrations this sprint: `2b3c4d5e6f7a` (additive — seven new tables,
  two new nullable columns on `project_cost_entries`) and `3c4d5e6f7a8b`
  (data-only — one `UPDATE` seeding `stone_v1`'s Fabrication gate).
- `alembic check` caught a real naming mismatch introduced by this sprint:
  `project_material_requirements`/`project_material_allocations` used
  abbreviated index names (`ix_pmr_*`/`ix_pma_*`) instead of the
  `ix_<table>_<column>` convention SQLAlchemy's `index=True` generates for
  every other table this migration touches. Fixed in the migration file,
  verified with a full local `downgrade`/`upgrade` cycle through it and a
  re-run of the full backend suite (still 1244 passed, 3 skipped). After
  the fix, `alembic check` reports **only** the same pre-existing drift
  Sprint 043 already documented as out of scope (`email_verification_tokens`,
  `password_reset_tokens`, `processed_stripe_events`,
  `project_workflow_history`, `projects.workflow_template_id`/
  `workflow_stage_id`, `quote_items.created_at`, `subscriptions`,
  `workflow_templates`) — nothing from this sprint's own tables remains.

### Migration safety

Purely additive: seven new tables, two new nullable columns, zero
`ALTER`/rewrite of any existing row's data. A pre-Plan-05 project has zero
procurement rows, and its Materials tab shows "No material requirements
yet" rather than a fabricated zero.

---

## 6. Known limitations

- **Partial-receipt cost splitting** (ADR-051): a PO item's committed cost
  does not split proportionally as partial deliveries land — it stays
  `committed` in full until the item is completely received. Documented,
  not silently hidden; reconciling proportional splitting would require
  giving `project_cost_entries` a cross-row lineage it does not have today.
- **No warehouse/stock ledger**: `project_material_allocations` records an
  allocation *event*, never a computed running stock balance — deliberate,
  per Task 14's "not a warehouse system" rule.
- **PO numbering "skips" per project**: because `PurchaseOrder.reference`
  is sequential per tenant (ADR-050), a single project's own PO list will
  show non-contiguous numbers when the tenant also raises POs against
  other projects or none at all.

---

## 7. What was explicitly not done

Per the governing instructions: production was never deployed to, Plan 06
was never started, no pricing/Stripe/trial model was touched, no historical
commercial record was rewritten, supplier identity was never duplicated,
stock/availability/delivery dates were never fabricated, and no quote item
or variation item was ever auto-purchased — every quote/variation
suggestion requires an explicit user action per line.
