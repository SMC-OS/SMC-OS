# 19 — Release verdict, 13 Nov 2026

**GeoCore FINAL CUSTOMER RELEASE: NO-GO (not yet).** Production: NOT DEPLOYED. Customer admission: CLOSED. Nothing in production, live Stripe or backups was touched.

## Release candidate evidence
- Candidate SHA for acceptance: `607a51bf3c5afd41f5085a8542813715ed87abda` (branch `ccr-12966459-skf9q0`, PR #71). Not yet declared the immutable final SHA: owner approval of the release defaults is outstanding, and merging into `qa/geocore-closure-20261105` has not been done.
- CI on that SHA: backend, frontend, e2e, dependency audit and secret scan all success (one e2e ECONNRESET flake passed on rerun).
- Isolated QA deployment (project `geocore-qa-20261110`, env `acceptance`): API deployment `0e0cfb8c…` / web `e2bc4b67…` lineage; acceptance run 43354712181 verified API and web both at the exact SHA, migration `b6c7d8e9f0a1` applied, `/ready` 200.
- Deployed results on that exact SHA: browser acceptance 8/8; lifecycle, invoices, PDF text, portal 73/73; roles and tenant isolation 88/88; stone job to completion 10/10; security 38/38; capacity pass at 30 virtual users (error rate 0, p95 0.44 s, p99 ≈ 3 s). Earlier on the previous build: portal expiry and the PostgreSQL 18 matched database+uploads scratch recovery (restore 2.0 s on small data).

## What changed (Phase 1 release defaults, all subject to owner approval before production)
Owner-held financial approval with explicit delegation and recorded actor/amount/time; quote revisions that preserve the approved original; per-workspace invoice supplier settings (legal name, address, VAT status/number, bank/payment details, terms default 30 days) validated at issue and frozen with a calculated due date; numbering and arithmetic unchanged. Defects found and fixed on the way: invoice reference regex, Central-European glyphs (DejaVu vendored), `x-powered-by`, localhost `og:image` base, redeploy mechanism.

## Still open (cannot be closed without the owner, an operator or a professional)
| Gate | Exact need |
|---|---|
| Stripe test-mode lifecycle | No Stripe connector in this session; QA API has no Stripe variables. Add `GEOCORE_QA_STRIPE_SECRET_KEY` (restricted test key) and `GEOCORE_QA_STRIPE_WEBHOOK_SECRET` (test-mode endpoint `https://geocore-api-qa-acceptance.up.railway.app/api/v1/billing/webhook`). Then: activation, trial, checkout, failure/recovery, upgrade/downgrade, cancel/resume, portal, signed/duplicate/out-of-order webhooks |
| Real inbox delivery | `RESEND_API_KEY` for QA, verified sending domain, monitored test mailbox; then verification, resend, forgot/reset, invalid/expired/used links |
| Shared-staging recovery | New approved UTC window, named operator, notification, private encrypted storage, PG18 client; PITR/WAL verification |
| Production recovery/migration impact/catalogue import | Read-only production access in an approved window |
| Monitoring, alerts, escalation, support mailbox and targets | Owner accounts/mailbox and adopted targets |
| Legal/commercial acceptance | Doc 18 section 3 (solicitor, accountant, ICO decision); no approval claimed |
| Release-defaults policy | Owner approves approval policy and revisions; enters supplier details per workspace |
| Final immutable SHA | After approval: merge #71 → `qa/geocore-closure-20261105` (no deploy), re-run CI and QA acceptance on that SHA; never merge #69 (auto-deploys shared staging web) outside an approved window |

## Initial operating limits if/when released
≤10 paying workspaces and ≤30 concurrent users; no uptime, RTO or RPO promised.
