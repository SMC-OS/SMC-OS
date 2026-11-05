# 02 — Defect register

Status words: Verified, Defective, Blocked, Pending or Unknown. In this register, **Fixed (local)** means code and tests exist on the QA branch and pass locally. It is not a ledger status and does not close anything. A ledger item can only become Verified with staging evidence on the release SHA.

| ID | Severity | Ledger status | Engineering state | Fix | Blocker to Verified |
|---|---|---|---|---|---|
| STONE-GATE | Critical | Defective (unchanged) | Root causes reproduced at `63e8ac9`; fixed (local) | QA branch, P0 commit | Staging deploy needs migration and backup approval (06); staging retest g5 |
| DEF-003 | High | Defective (unchanged) | d1–d9 behaviours fixed (local) and tested | QA branch, P0 commit | Same as above |
| QA-STRIPE-ACK | High | not in ledger | Found by code review; fixed (local) | QA branch, billing commit | Sandbox Stripe retest with real test events (05) |
| QA-NAN-500 | Medium | not in ledger | Found while testing; fixed (local) | QA branch, P0 commit | CI and staging |
| QA-ALLOC-XPROJ | High | not in ledger | Found by code review; fixed (local) | QA branch, P0 commit | CI and staging |
| QA-ADMISSION | Critical (#67 P0) | gate `onboarding` / Issue #67 | Server-side gate implemented, default open | QA branch, admission commit | Owner must set `NEW_ACCOUNT_ADMISSION=closed` on staging, then production, after review |
| QA-VITEST-FLAKE | Low | not in ledger | Pre-existing timing flake in `app/quotes/new/stone/page.test.tsx` | Not fixed | Already present at `63e8ac9` (see 03) |
| HIST-RECEIVED | High (data) | not in ledger | Requirements may be wrongly `received` from before the fix | Read-only audit SQL only | Owner-approved read-only run on staging and production; humans decide each row |

## STONE-GATE — "Fully received material does not unlock Fabrication"

### Root cause

The path is Requirement → PO line (`material_requirement_id`) → Receipt → requirement sync → `materials_ready` gate.

Reproduced at `63e8ac9` on a disposable PostgreSQL 16.2, against the seeded `stone_v1` Fabrication stage: 10 of 12 tests failed. Raw output is in `evidence/stone-gate-repro-63e8ac9.txt`.

**Causes that leave the gate shut (the reported symptom):**
1. A PO line created without a link can never be linked after ordering. All of its deliveries are invisible to the requirement.
2. Float rounding: part deliveries of 1.1 + 1.1 + 1.1 against 3.3 had the third one refused as an over-receipt, so the order could never complete.

**Causes that open the gate too early (the opposite failure):**
1. Receiving 5 against 10 required marked the requirement `received`.
2. One of two linked lines marked it `received`.
3. Receipts were accepted on draft, approved and cancelled POs.
4. A PO line could link another project's requirement.
5. Several lines for the same item in one delivery bypassed the over-receipt check, because each line was checked separately.
6. An allocation could mark another project's requirement `allocated`, which opens that job's gate.

**Integrity problems:**
1. Receipt processing was several separate commits, so a crash midway could leave a partial delivery.
2. Retried deliveries were counted twice.
3. Cancelling the only PO left the requirement `ordered`.

**Which cause produced the owner's incident is NOT established.** That needs the affected staging job's data, read-only. `scripts/qa/stone_gate_historical_audit.sql` lists candidates for both directions.

### Fix (QA branch)

- **Recompute from all lines:** a requirement is recomputed from every linked PO line. It is `received` only when the received total covers `required_quantity` (same unit), or, when units differ, when every linked line is fully delivered. Cancelled POs count only what was actually delivered.
- **Float tolerance:** quantity comparisons allow 1e-6.
- **Receivable POs only:** receipts are accepted only on `ordered`, `partially_received` and `received` POs; others get 409.
- **Repair route for unlinked lines:** `POST /purchase-orders/{id}/items/{item_id}/link-requirement`, available to OWNER and STAFF. It links a line to a live requirement on the same project and tenant, refuses anything else with 422 or 409, then applies what that line already received. The Materials tab shows a warning and a selector for each unlinked line.
- **No automatic matching:** nothing is matched by name or quantity, and no historical data is changed.
- **Idempotency:** `PurchaseReceipt.idempotency_key` is a nullable column with a partial unique index per tenant (migration `a5f6b7c8d9e0`). The same key with the same lines returns the original receipt. The same key with different lines or a different PO gets 409. The UI sends one key per distinct delivery, reused on retry.
- **One transaction:** receipt rows, the committed→actual cost flip, requirement statuses, PO status and the activity log commit together. Any failure rolls all of it back. Automations run after the commit.
- **Row locks:** the PO row is locked (`SELECT … FOR UPDATE`) for receipt and cancellation, so concurrent deliveries cannot over-receive.
- **Duplicate lines:** duplicate lines for one item in a delivery are summed before the over-receipt check.
- **Allocations:** an allocation may only reference this project's live requirement and this workspace's PO line.
- **Numbers:** NaN, Infinity and non-positive quantities are refused with 422.

### Checklist status (each item individually)

| Item | Requirement | Local evidence (disposable DB) | Ledger |
|---|---|---|---|
| g1 | Requirement ↔ PO item linkage present | `test_linked_full_receipt_clears_the_gate`, `test_unlinked_po_item_can_be_linked_after_ordering_and_catches_up`, E2E Journey H | open |
| g2 | Full receipt sets `received` | `test_linked_full_receipt_clears_the_gate`, `test_decimal_part_deliveries_can_complete_an_order` | open |
| g3 | Gate re-evaluates after receipt | Same tests evaluate `evaluate_stage_gates` on the seeded `stone_v1` Fabrication stage before and after | open |
| g4 | Template → Fabrication only once all requirements are cleared | `test_one_received_requirement_does_not_clear_another_outstanding_one`, `test_one_of_two_linked_lines_does_not_open_the_gate`, E2E Journeys G, H and I | open |
| g5 | Real-world retest on staging | NOT RUN: staging does not run this code (06) | open |
| d1 | PO items explicitly link `material_requirement_id` | Create, update and link validation tests; cross-project and cross-tenant refused | open |
| d2 | Partial receipt stays `partially_received` | `test_partial_receipt_keeps_the_gate_closed`, `test_receiving_less_than_required_does_not_open_the_gate`, E2E Journey I | open |
| d3 | Full receipt advances to `received` | g2 tests | open |
| d4 | Gate recomputed after receipt | g3 tests | open |
| d5 | Retry is idempotent | `test_retried_delivery_with_same_key_is_not_counted_twice`, `test_a_reused_key_cannot_change_what_was_recorded`, UI key-reuse unit test | open |
| d6 | Over-receipt rejected | Existing over-receipt test, `test_duplicate_lines_for_one_item_in_a_delivery_cannot_over_receive`, `test_concurrent_deliveries_cannot_together_over_receive` | open |
| d7 | Cancellation handled | `test_cancelling_the_only_po_releases_the_ordered_requirement`, `test_receipt_after_cancellation_is_refused_and_delivered_goods_still_count`, draft/approved/cancelled 409 tests | open |
| d8 | Tenant isolation | `test_another_workspace_cannot_receive_or_link_on_this_po`, `test_po_item_cannot_link_another_projects_or_tenants_requirement`, existing tenant B test | open |
| d9 | Ledger alignment | `test_cost_moves_committed_to_actual_once_across_partials_and_retries`, `test_a_failure_mid_receipt_writes_nothing` | open |

**No checkbox is ticked.** The ledger's own rule (g5) and the mission both require a current staging test on the deployed artifact.

### Known limits that remain

- **Historical data:** requirements already wrongly `received` are not downgraded; status changes are forward-only. Use the read-only audit SQL and a human decision for each row.
- **Mixed units:** with a unit mismatch, completion falls back to "every linked line fully delivered". It never adds slabs to m².
- **Allocation from stock:** `allocated` still clears the gate without a receipt. This is by design ("received/allocated/consumed may unlock"), and the owner should confirm it.
- **Automations:** they run after the commit, so an automation failure does not undo a delivery. That is intended, and it is logged.

## QA-STRIPE-ACK — Stripe event marked processed before its effect

- **Found:** code review for Phase 5.
- **Defect:** `crud.mark_stripe_event_processed` committed the processed marker *before* the handler ran. A handler failure (DB error, deploy restart) returned 5xx, but Stripe's retry was then skipped as "already processed", so the subscription change was lost for good.
- **Fix:** the marker is only flushed, and it commits with the effect. A handler failure rolls both back. A concurrent duplicate hits the primary key and is treated as already processed.
- **Tests:** `tests/test_billing_webhook_atomicity.py` covers the injected failure (event left unrecorded, then the retry applies it), replay applied once, and an unhandled type still recorded. Existing webhook tests still pass.
- **Not done:** verification with real Stripe test-mode events and a reconciliation of live Stripe against app state (05).

## QA-NAN-500

- **Defect:** a request body containing `NaN` or `Infinity` passed validators written as `value < 0`. When a validator did refuse it, the 422 handler crashed while serialising NaN, which turned it into a 500.
- **Fix:** procurement validators require finite numbers. The global 422 handler echoes non-finite inputs as text.

## QA-ALLOC-XPROJ

- **Defect:** `POST /projects/{A}/allocations` with project B's requirement set B's requirement to `allocated`, which opened B's Fabrication gate. It also accepted any PO line id without checking its tenant.
- **Fix:** returns 422 unless the requirement belongs to A, is not cancelled, and the PO line belongs to the same workspace.
