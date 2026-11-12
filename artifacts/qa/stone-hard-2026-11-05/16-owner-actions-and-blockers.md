# 16 — Consolidated owner actions and blockers (12 November 2026)

**Verdict: HARD NO-GO.** 0 of 28 launch-blocking gates are VERIFIED (see [15](./15-release-execution-ledger.md)). Nothing in this document approves a production change.

## Why work stopped where it did

The agent environment can reach GitHub but **not** Railway, Stripe or the isolated QA site (its egress is limited to GitHub and package registries). The isolated QA environment *is* reachable from a GitHub-hosted runner, which is why the public smoke passed (run 42855457897, HTTP 200 only). Every authenticated acceptance step needs a shell in the QA API container (to create e-mail-verified synthetic owners) or a Stripe test-mode key. Neither can be created without a credential only the owner can issue.

## The smallest remaining sequence

| # | Owner action | Unblocks | Effort |
|---|---|---|---|
| 1 | Create a **Railway project token** for `geocore-qa-20261110` / `acceptance` only, and save it as repository secret `GEOCORE_QA_RAILWAY_TOKEN` | Runs the eight STONE-GATE / DEF-003 browser tests on the deployed QA build (workflow *GeoCore isolated QA authenticated acceptance*), identity/migration check, provisioning proof | 5 min |
| 2 | Provide a **Stripe test-mode restricted key** and a dedicated QA webhook endpoint secret for the QA API (never the live key, never another environment's webhook) | The whole billing lifecycle (checkout, trial, upgrade/downgrade, failure and recovery, cancel, portal, webhooks) | 15 min |
| 3 | Name a **monitored test mailbox** and confirm the QA mail provider is configured | Registration, verification resend, password reset with real delivery; support enquiry test | 15 min |
| 4 | **Review the role matrix** (`tests/data/role_matrix.json`), above all: Staff may approve purchase orders, quotes and variations and receive deliveries. Say which of these should be Owner-only | ROLE-PERMS gate; any change is a small code edit with tests | 10 min |
| 5 | **Shared staging / production recovery:** a new exact 30-minute UTC window (the 10 Nov one expired), a named operator with Railway CLI and a PostgreSQL 18 client in WSL2, encrypted private storage, user notice at least 24 hours ahead, approval of the barrier procedure. Rehearse the whole drill on isolated QA first (step 1 enables that) | RECOVERY-POINT, SCRATCH-RESTORE, PITR-WAL; required before any production migration | operator |
| 6 | **UK solicitor review** and operator identity details (one packet); support mailbox and response targets | LEGAL-COMMERCIAL, SUPPORT | external |
| 7 | **Read-only access to production Railway config** (or run the checklist) including the catalogue-writing pre-deploy and previous deployments; confirm `NEW_ACCOUNT_ADMISSION` is closed | PROD-CONFIG, ADMISSION | 15 min |

After step 1 the agent can, without further input: run the eight tests, fix whatever fails, run the full customer journey, the authenticated security and tenant checks, a measured mixed-workload capacity test, and the recovery drill on isolated QA.

## What genuinely passed today (local or CI only, never upgraded to another environment)

- CI on `8a1e27f`: all four jobs green (run 42855794149, re-read). Full backend suite on the working tree: **1831 passed, 0 failed**.
- **Two data-integrity defects fixed** with regression tests that fail on the old code: orphan upload files, and a saved customer reported as an error.
- **A latent defect found and fixed** before it could block A2: the synthetic-owner script refused to run on staging and QA because it read `APP_ENV=production` as production.
- **Secret scanning gate created** and clean across the tree and all 468 commits (CI previously had none).
- **Role matrix** for all 150 authenticated operations, committed as a reviewable snapshot.
- **Invoice PDFs** generated and inspected: totals independently recomputed and exact, fonts and wrapping correct.
- **Billing plans** in code match the approved pricing exactly (Stripe-side objects unverified).
- Fresh dependency audits (Python and Node) clean.

## Not done, and why it cannot be done independently

Authenticated acceptance on QA, Stripe lifecycle, real e-mail, recovery drill, capacity test, production deployment and handover all need access listed above. No gate was marked VERIFIED on local or CI evidence alone, and nothing was changed on Railway, Stripe or production.
