# 05 — Billing: sandbox, webhook safety, reconciliation

**No Stripe API call of any kind was made in this session.** The claude.ai Stripe connector needs authentication, and the Stripe CLI is not installed. Nothing was read from or written to live or test Stripe.

## Done (code and local tests)

| Item | Result | Evidence |
|---|---|---|
| PR #66 compatibility: `invoice.parent.subscription_details.subscription` vs legacy `invoice.subscription` | Present in candidate `63e8ac9` (`BillingService._invoice_subscription_id`). Legacy is preferred when set. A non-subscription or missing parent changes nothing | Code reading; existing tests `evt_test_invoice_2026_parent_*` and `evt_test_invoice_legacy_*` pass locally |
| Event persistence safety | **Defect QA-STRIPE-ACK found and fixed (local).** The event used to be committed as processed before its effect, so a failed handler's retry was dropped. Now the marker and the effect commit together, and a failure rolls both back | `tests/test_billing_webhook_atomicity.py` (3 tests), plus `test_billing.py` and `test_billing_webhook_resources.py`: 49 passed locally |
| Admission/checkout freeze (#67 P0) | `NEW_ACCOUNT_ADMISSION=closed` refuses signup, new trials and first-time checkout with 403 before any Stripe call. Existing Stripe subscribers keep checkout; portal, cancel and resume are untouched. Default `open` | `tests/test_admission_gate.py` (7 tests) |

## Not done: BLOCKED (needs access or owner approval)

| Item | Why blocked | Next safe action |
|---|---|---|
| Sandbox price IDs and plan terms, 14-day trial, checkout with test card, signed webhooks, invoices, renewal failure, recovery, cancel/paid-through/resume, portal, out-of-order events | No Stripe test-mode access in this session | Owner authenticates the Stripe connector in **test mode**, or provides a restricted test key on staging only; then run against staging with synthetic tenants |
| Live read-only reconciliation (one active and one cancelled subscription, zero portal configurations, as previously observed) | Not re-verified: no Stripe access | Owner-authorised read-only listing; compare with `subscriptions` rows read-only; never replay live events |
| Live billing portal configuration, tax/refund disclosures | Owner commercial decision | Proposal only, after legal review (08) |
| Whether the live active subscription is a real customer | Owner fact (legal checklist) | Owner confirms |

## Residual risks noted in code

- `_handle_checkout_completed` and `_handle_subscription_upsert` rely on `metadata.tenant_id`. An event without it is a silent no-op, but it is still recorded as processed. That is correct for idempotency, but it should be visible in monitoring.
- A concurrent duplicate delivery now returns success without applying anything, and the first delivery applies the effect. Stripe ordering is still not guaranteed. The upsert logic preserves fields across either order (existing tests).
