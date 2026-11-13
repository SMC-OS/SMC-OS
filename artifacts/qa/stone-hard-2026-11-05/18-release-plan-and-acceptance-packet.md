# 18 — Final release plan, PR relationship and legal/commercial acceptance packet (13 Nov 2026)

Nothing here records legal approval. Items marked OWNER need the owner's or a professional's own act.

## 1. PR relationship and promotion path (no deployment triggered by this document)
| PR | Base ← head | State | Deploys anything? |
|---|---|---|---|
| #70 | `qa/geocore-closure-20261105` ← `ccr-12966459-skf9q0` | merged (earlier recovery tooling) | no |
| #71 | `qa/geocore-closure-20261105` ← `ccr-12966459-skf9q0` | open, this work | no (the base is not Railway-watched); isolated QA tracks the head branch only |
| #69 | `fix/launch-quote-repeat-save-20261031` ← `qa/geocore-closure-20261105` | open DRAFT | **YES — merging it auto-deploys shared staging web. Do not merge outside an owner-approved window.** |

Plan: (1) owner approves the release defaults; (2) merge #71 into `qa/geocore-closure-20261105` (safe, no deploy); (3) declare the resulting commit as the immutable final SHA; (4) run full CI on that exact SHA and re-run the deployed acceptance on isolated QA pinned to it; (5) only then, in an approved window, merge #69 / promote to production in the order **API first, web second**. `740b6b4` stays the recorded baseline.

## 2. Gate matrix still open after the release defaults
| Gate | Blocker | Who |
|---|---|---|
| Release defaults (approval authority, revisions, supplier settings) | Owner approval of the policy; deployed re-run on the final SHA | Owner |
| Stripe test-mode lifecycle | No Stripe connector exists in this session; QA API has no `STRIPE_*` variables. Needs GitHub secrets `GEOCORE_QA_STRIPE_SECRET_KEY` (restricted test key) and `GEOCORE_QA_STRIPE_WEBHOOK_SECRET`, and a test-mode webhook endpoint for the QA API | Owner |
| Real inbox delivery | No Resend configuration on QA; needs `RESEND_API_KEY`, verified sending domain, monitored test mailbox | Owner |
| Shared-staging recovery (A1/A2, PITR/WAL) | New approved UTC window, named operator, notice, private encrypted storage, PG18 client | Owner + operator |
| Monitoring, alerts, incident escalation, support mailbox | Tooling accounts and mailbox owned by the operator | Owner |
| Legal/commercial acceptance | Section 3 | Owner + solicitor/accountant |
| Production recovery point, migration impact, supplier-catalogue import | Read-only production access and an approved window | Operator |

## 3. Legal / commercial acceptance packet (fill in; do not publish until reviewed)
| Item | Facts on record (not re-verified; from `docs/LEGAL_REVIEW_CHECKLIST.md`) | Needed |
|---|---|---|
| Operator identity | Mohammad Al Kawarit trading as GeoCore, UK sole trader; no company number | Owner to confirm exact legal wording used on Terms/Privacy |
| Address for notices | Suite RA01, 195-197 Wood Street, London E17 3NU (virtual office) | Owner to confirm it is acceptable for legal notices/ICO registration |
| VAT | No VAT number evidenced; none is shown anywhere | Accountant to confirm registration position and whether subscription pricing is VAT-inclusive |
| Terms of service, Privacy notice, DPA, cookie notice | Drafts exist in the app | UK solicitor review (not evidenced) |
| Subprocessors and international transfers | Railway (hosting), Stripe (billing), Resend (e-mail) per `docs/AI_DATA_FLOW.md`/runbooks | Confirm list, regions and transfer mechanism |
| Refund, cancellation and renewal policy | Behaviour implemented (cancel at period end, resume) | Owner decision on wording; solicitor review |
| ICO data-protection fee | Undecided | Owner |
| Support | No adopted response targets | Owner to adopt hours and targets; do not promise 24/7 or any RTO/RPO |

## 4. Initial operating limits (from measurement, not aspiration)
Measured on isolated QA: ≤30 concurrent virtual users, ≤10 workspaces, small datasets, error rate 0, p95 ≤0.4 s (occasional p99 ≈3 s at 15 users). The first controlled cohort must stay within **≤10 paying workspaces and ≤30 concurrent users** until a larger measurement exists. No uptime, RTO or RPO is promised: the QA drill restored in seconds on tiny data with no point-in-time recovery.

## 5. Production sequence (only after every applicable gate is VERIFIED and the owner authorises)
1. Production recovery point and rollback verified; admission stays closed (`NEW_ACCOUNT_ADMISSION=closed`).
2. Deploy API at the final SHA; verify migrations (`b6c7d8e9f0a1` is additive and reversible), supplier-catalogue import, database integrity, `/ready`, logs.
3. Deploy web second; verify registration, e-mail delivery, customer/project, quote, invoice/PDF, billing and tenant isolation with authorised synthetic fixtures.
4. Request admission approval for the first cohort within the limits above.
