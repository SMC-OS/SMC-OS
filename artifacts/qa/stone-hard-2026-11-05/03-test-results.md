# 03 — Test results and command log

## Environment

- **Local machine:** Windows 11, with Python from a venv built from the pinned `requirements.txt`, and Node 22 with pnpm 9.0.0 via corepack.
- **Database:** a disposable embedded PostgreSQL 16.2 (pgserver) on `127.0.0.1:55679`, database `simo_os`, created for this session. It holds synthetic data only. Every command was guarded so it ran only when `DATABASE_URL` contained `127.0.0.1`.
- **Accounts:** synthetic tenants with `@example.invalid` owners. No real person, customer, owner account or SIMO TEST was used.
- **Not tested:** staging and production. Nothing in this file was run against either.

## Results on the QA branch

| # | Suite | Command (from repo root unless noted) | Result | Notes |
|---|---|---|---|---|
| 1 | Reproduction at `63e8ac9` (before fix) | `pytest tests/test_procurement_stone_gate.py` | 10 failed, 2 passed | `evidence/stone-gate-repro-63e8ac9.txt` |
| 2 | STONE-GATE + procurement + workflows (after fix) | `pytest tests/test_procurement_stone_gate.py tests/test_procurement.py tests/test_workflows.py` | 96 passed | Includes concurrency, failure injection, idempotency, ledger, cross-tenant/project and allocation tests |
| 3 | Admission gate | `pytest tests/test_admission_gate.py` | 7 passed | |
| 4 | Billing incl. webhook atomicity | `pytest tests/test_billing_webhook_atomicity.py tests/test_billing_webhook_resources.py tests/test_billing.py` | 49 passed | |
| 5 | Ledger generator rules | `pytest tests/test_qa_matrix_rules.py` | 5 passed | |
| 6 | Full backend, run 2 (procurement fix complete; admission and webhook changes not yet included) | `pytest` | 1627 passed, 1 skipped (25m34s) | `evidence/full-backend-run2-summary.txt` |
| 7 | Full backend, run 3 (final code except `tests/test_qa_matrix_rules.py`, which was added after collection) | `pytest` | 1637 passed, 1 skipped (21m14s) | `evidence/full-backend-run3-summary.txt` |
| 8 | Frontend unit tests, changed areas | `cd apps/web && npx vitest run components/projects/ProjectMaterialsPanel app/signup lib --testTimeout=30000` | 78 passed | |
| 9 | Frontend unit tests, full suite | `cd apps/web && npx vitest run` | 415 passed, 4 failed in `app/quotes/new/stone/page.test.tsx` (5 s timeouts) | Pre-existing flake, see below |
| 10 | Typecheck | `cd apps/web && npx tsc --noEmit` | exit 0 | |
| 11 | ESLint, changed files | `cd apps/web && npx eslint <changed files>` | exit 0 | |
| 12 | Playwright procurement journeys A–I | `cd apps/web && npx playwright test procurement-materials-operations.spec.ts` | 6 passed, 3 failed on the 30 s per-test timeout; those 3 passed with `--timeout=120000` | `evidence/e2e-procurement-2-summary.txt`, `evidence/e2e-procurement-3-summary.txt` |
| 13 | Migration `a5f6b7c8d9e0` | `alembic upgrade head; alembic downgrade -1; alembic upgrade head` | passed | Disposable DB only |
| 14 | Historical audit SQL | executed read-only (`BEGIN READ ONLY … ROLLBACK`) | runs; 0 rows on the disposable DB | Says nothing about real data |
| 16 | Anonymous access sweep, every API operation | `pytest tests/test_api_unauthenticated_sweep.py` | 163 passed | No 5xx. Only 6 allow-listed public operations answer 2xx; the rest of the protected API returns 401 |
| 17 | Staging historical audit (read-only, aggregate) | `railway ssh` into `simo-api-staging`, `READ ONLY` transaction, counts only | 1 requirement, 0 suspects; `alembic_version` 94e5f6a7b8c9 | No identifiers exported; see 02 |
| 15 | Secret and personal-data scan of the diff | `git diff` grep for Stripe, JWT, AWS and PEM key patterns, password literals, personal e-mail domains | no hits | |

## Failures and how they were triaged

- **E2E Journey D failed on the first run. It was a real regression of mine, and it is fixed.**
  - **Symptom:** after narrowing the friendly over-receipt message to 409s whose text says "would exceed", the browser showed the raw "Request … failed with 409".
  - **Cause:** the web client's `ApiError` never carried the server's `detail`.
  - **Fix:** `ApiError.detail` was added; `message` is unchanged for every other caller. Unit tests now cover both 409 cases.
  - **Same fault elsewhere:** the sign-up 403 message had the same weakness, and its unit test passed only because it was built with the message pre-set. The test now constructs the error the way the real client does.
  - **Retest:** Journey D passes.
- **The E2E 30 s timeouts are environmental, not logic failures.**
  - The local Next.js dev server compiles on demand, and the machine was running the full backend suite at the same time.
  - The same three journeys passed with a 120 s budget, with no assertion changed.
  - CI's Playwright job is the independent check (see CI below).
- **The vitest timeouts in `app/quotes/new/stone/page.test.tsx` are pre-existing.**
  - This branch does not touch that file.
  - On an untouched checkout of `63e8ac9`, the file also failed (3 of 36) on 5 s timeouts.
  - With `--testTimeout=30000`, both `63e8ac9` and the QA branch pass 36 of 36.
  - Recorded as QA-VITEST-FLAKE (Low). Not fixed here.
- **Two admission tests failed on the first attempt because of test fixtures, not product code.**
  - The workspace already had a trial subscription row.
  - Cleanup after a real sign-up must delete verification tokens first.
  - The tests were corrected; no assertion was weakened.

## Final full backend run

Local run 3: 1637 passed, 1 skipped, 0 failed. CI's backend job on `73f7dd4` (below) is the authoritative full run on the committed SHA.

## CI (GitHub Actions, exact SHA `73f7dd4`)

Push run https://github.com/SMC-OS/SMC-OS/actions/runs/42127242681 and pull-request run https://github.com/SMC-OS/SMC-OS/actions/runs/42127317387 both concluded **success**.

| Job | Result |
|---|---|
| backend | 1643 passed (5m06s), with migrations applied from scratch by `alembic upgrade head` |
| frontend | lint, type-check, build and contract tests passed; vitest 53 files, 422 of 422 tests passed |
| e2e | Playwright: 77 passed (8.3m), the full suite, including procurement journeys A–I |
| dependency-audit | passed |

This is CI evidence on the QA SHA. It is **not** staging evidence, and no ledger status is changed by it.
