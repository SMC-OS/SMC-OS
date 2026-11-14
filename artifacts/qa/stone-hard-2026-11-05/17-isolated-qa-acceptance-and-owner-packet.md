# 17 — Isolated QA acceptance results and consolidated owner packet (12 Nov 2026)

Environment: isolated QA only (project `geocore-qa-20261110`, environment `acceptance`), synthetic data, candidate runtime tree identical to `7644a22`, migration `a5f6b7c8d9e0`. CI on the branch head is green. Production: NO-GO (unchanged). No production, live-Stripe, backup-deletion or customer-admission action was taken.

## Evidence (all from GitHub Actions against the deployed QA services)
| Area | Result | Run |
|---|---|---|
| STONE-GATE / DEF-003 browser tests | 8/8 passed (three consecutive runs) | 43172161693, 43173096347, 43183882421 |
| Lifecycle, invoices, PDF text, portal scope/revocation, MIME spoofing | 68/68 | 43183882421 |
| Owner/Staff roles (28 owner-only operations refuse Staff), remaining tenant isolation, editing, tasks, workflow | 73/73 | 43183882421 |
| Stone job enquiry→complete through the materials gate | 10/10 | 43183882421 |
| Capacity (5/15/30 VUs, bounded) | error rate 0; p95 0.27/0.29/0.40 s; pass | 43183882421 |
| Matched DB + uploads recovery drill (PG18 client, disposable DB) | all checks passed; restore 2.0 s | 43183225488 |
| Portal expiry on the deployed API | passed | 43183932147 |

Mechanism: no SSH (a project token cannot register keys). Reviewed scripts run inside the QA API container through a restorable start-command step; the original command and temporary variables are restored after every run (verified each time). QA web was corrected to the intended same-origin proxy configuration (`API_PROXY_URL` = API origin, `NEXT_PUBLIC_API_URL` = web origin).

## Findings that need an owner decision
1. **Staff financial approval.** Staff can approve quotes, variations and purchase orders and write project costs, with no limit and no second approver. Confirm this is intended, or require Owner approval above a threshold. Role matrix is not treated as approved.
2. **Invoice content (blocks PDF-QUALITY).** Layout is clean and arithmetic correct, but the invoice carries no supplier name/address/company number, no VAT number, no due date, no payment details or terms. Please supply: company name and number, registered address, VAT registration (or confirm not registered), bank details, payment terms. I will add them to the template and re-inspect.
3. **Approved quotes cannot be amended or reopened** (409). Confirm acceptable, or request a revision workflow.
4. **Capacity claim** is limited to ≤10 workspaces / ≤30 concurrent users on the current instance with small data; an intermittent p99 spike (~3 s) was seen twice at 15 users.

## Remaining gates and exactly what unblocks each
| Gate | Needs | From |
|---|---|---|
| Stripe checkout, failure/recovery, cancel/upgrade/downgrade, portal (test mode) | GitHub secrets `GEOCORE_QA_STRIPE_SECRET_KEY` (restricted **test** key) and `GEOCORE_QA_STRIPE_WEBHOOK_SECRET` (a webhook endpoint created for `https://geocore-api-qa-acceptance.up.railway.app/api/v1/billing/webhook`, test mode, events: checkout.session.completed, customer.subscription.*, invoice.paid, invoice.payment_failed). The eight price IDs are already recorded in PR #71; I will set them on QA through the same restorable mechanism. | Owner |
| Real e-mail verification and password reset | Resend API key for QA, a verified sending domain, and a monitored test mailbox (a `+qa` alias of an owner-controlled inbox works; I can read it through the connected Gmail tool if you approve that use). Synthetic verification does not count as inbox proof. | Owner |
| Shared-staging A1 recovery + scratch restore | New exactly approved window, named operator, private storage, PG18 client, user notice. QA drill proves the tooling path. | Owner + operator |
| PITR/WAL | Read-only diagnostics on staging; Railway backup/PITR settings | Operator |
| Monitoring/alerts, support process, legal/commercial review, admission decision | Owner decisions; UK solicitor review of terms and privacy | Owner |
| Production config check, final production release | Read-only production review and matched recovery point; then API first, web second | Operator + owner |

QA web variables changed (kept, intended): `API_PROXY_URL`, `NEXT_PUBLIC_API_URL`. Everything else restored to original.
