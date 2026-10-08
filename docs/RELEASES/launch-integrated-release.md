# GeoCore launch: integrated release candidate

**Status:** promoted to production on 8 Oct 2026. Deployment, health, schema and
public-surface verification passed; no rollback. Authenticated production
acceptance is **outstanding** (section 9).

## 1. Why the traffic-readiness candidate was rebuilt

The traffic-readiness gate was accepted by the owner as **26 PASS / 0 FAIL /
1 BLOCKED-BY-DESIGN** (candidate `13e1474`, branch `fix/traffic-readiness-gate`;
staging smoke 20 PASS / 0 FAIL / 7 BLOCKED, six of those controls then verified
or evidenced out of band). The one accepted exception is `logs_request_ids`:
request-ID propagation, structured logging, redaction and unhandled-error
behaviour are implemented and unit-tested, and no staging-only crash endpoint
will be added just to exercise it.

Before any production promotion, a read-only preflight found that **production
already ran compliance/privacy code that the candidate did not contain**:

- production's database is at Alembic `4d5e6f7a8b9c` (`add_compliance_controls`),
  with its five tables present;
- production's API tree is byte-identical to the compliance line
  (`c35ef81` / `d8f6627`, 0 file differences across 255 files); its web build was
  uploaded after the compliance UI commits;
- the candidate descended from `main`, which had none of it. Promoting it as it
  stood would have removed `app/compliance/*`, `app/privacy/*` and the
  compliance changes to Settings, signup and the AI page from production.

So the candidate was rebuilt by integrating both lines. The additive compliance
migration stays: it is already live in production and staging.

## 2. What was built

| Item | Value |
| --- | --- |
| Integration branch | `launch/geocore-integrated-release` |
| Based on | `origin/main` `e764530` |
| Merged first | `origin/fix/start-logo-mark` `d8f6627` (compliance/privacy + marketing) |
| Merged second | `origin/fix/traffic-readiness-gate` `13e1474` (traffic readiness) |
| Merge commits | `a32d42b`, `06b4d14` (no conflicts) |
| Production API docs hardening | `1f51978` |
| CI reliability hardening | `544def2` |
| Tested tree | `544def2` (the final commit only adds this document and the promotion plan) |
| Alembic head | `4d5e6f7a8b9c` (single head, 39 revisions) |

The order matters: traffic readiness is layered on the compliance-capable code,
because production already runs the compliance line.

## 3. Compliance integration result

Compared with the fingerprinted production backend, the integrated tree has
**0 production-only files and 0 files with different content**. The only
addition is the operator-only `app/core/staging_fixture.py`. Every compliance
file (`app/compliance/*`, `app/privacy/*`, the eight shared backend files, and
the Settings, signup and AI page changes) is identical to `fix/start-logo-mark`.
The apps/marketing tree is identical to the production marketing build
(`d8f6627`), so marketing needs no deployment.

## 4. Migration graph

- `alembic heads`: `4d5e6f7a8b9c` only. `alembic history`: 39 revisions, none broken.
- Exactly one file declares `revision = "4d5e6f7a8b9c"`:
  `4d5e6f7a8b9c_add_compliance_controls.py`, git blob `927c997`, the same blob
  running in production.
- No vault migration, no second head, no destructive change.
- Clean-database upgrade from empty to head ran all 39 revisions.
- The `sprint-045-project-vault-documents-photos` branch is out of scope. It
  reuses revision id `4d5e6f7a8b9c` with a different body and must be renumbered
  (new ids, parented on the compliance `4d5e6f7a8b9c`) before it can merge.

## 5. Production API documentation hardening

`/docs`, `/redoc` and `/openapi.json` were publicly reachable on the production
and staging APIs. Nothing in the repo consumes them.

`Settings.api_docs_enabled` is false only for `AppEnvironment.PRODUCTION`, and
`create_app` then passes `docs_url`, `redoc_url` and `openapi_url` as `None`, so
the routes answer 404 rather than sitting behind a login. Development and test
are unchanged; `/health`, `/ready` and the API itself are unaffected.

**Staging:** Railway staging also sets `APP_ENV=production`, so this hardening
disables the three endpoints on staging after its next deployment too. Staging
was not redeployed as part of this work.

## 6. CI hardening

- `timeout-minutes` on every job (frontend 15, backend 25, e2e 30), against
  observed runs of about 1.5, 5-7 and 8.5-9 minutes. An e2e job once hung 88
  minutes installing a browser.
- `geocore-ai-and-settings.spec.ts` only: login, `/ai`, `/settings` and
  `/settings?section=billing` no longer wait on `networkidle`; they wait for the
  content and fill until values stick. No assertion removed, no retries added.
- Left as documented debt: three `networkidle` waits on `/` in that spec (they
  gate hydration-dependent clicks) and 132 more across 24 other specs
  (135 calls in total across 25 files).

## 7. Verification of the integrated candidate

| Gate | Result |
| --- | --- |
| Backend (full pytest, clean migrated Postgres) | 1454 passed, 1 skipped, 0 failed |
| Frontend lint, typecheck | pass |
| Frontend unit (Vitest, includes Settings, signup, AI page) | 300 / 300 |
| Contract/positioning checks, production build | pass |
| E2E (full Playwright, fresh migrated DB, one contiguous run) | 72 passed, 0 failed |
| `git diff --check`, tracked `.env`, secret-pattern scan | clean (0 hits) |

The local E2E ran against pre-warmed dev servers, because this machine could not
start the Next.js dev servers inside Playwright's 60 s window; CI starts its own.

## 8. Redeploy warning

`production-release` before the launch (`1855657`) is **not a safe redeploy
target**: it lacks migration `4d5e6f7a8b9c`, so a build from it aborts at the
migration gate against the production database. `production-release` now equals
the release SHA.

## 9. Production launch record (8 Oct 2026)

Release SHA: `f7a1eaa9e13c0fd8aeb9ff34ce0bfb7034ee2b10`
(PR #47 merge on `main`; GitHub CI run 37759850504, success).

| Item | Value |
| --- | --- |
| Promotion (UTC) | 2026-10-08T12:44:14Z, fast-forward push, no force |
| `production-release` | `1855657` to `f7a1eaa` |
| Railway project / environment | `simo-os` / `production` (`c5f88dea-...`) |
| API (`simo-api-production`) | `668cd773` to `9feb6436`, SUCCESS 12:45:56Z |
| Web (`simo-web-production`) | `11b82c4b` to `26be82a4`, SUCCESS 12:45:17Z |
| Follow-up cron (`simo-follow-up-production`) | `bb5cd9bc` to `7278d4ee`, SUCCESS 12:45:55Z, schedule `0 3 * * *` unchanged |
| Marketing (`simo-marketing-production`) | not deployed: tree identical to the build already live (`d1f0c2c5`, `d8f6627`) |
| Alembic before / after | `4d5e6f7a8b9c` / `4d5e6f7a8b9c` (no migration ran) |
| Rollback | not required, not used |

**Pre-launch backup.** Taken 2026-10-08T12:43:09Z with
`pg_dump --format=custom --no-owner` run inside the production Postgres container
(18.6; Docker was unavailable on the operator workstation, and the client there
must match the server major). Exit 0, 241,855 bytes, SHA-256
`c06e5529be3cc5343af0612ea7be8fa87015529871c18f6d102ebb17a5ffdca6`. In-container
`pg_restore --list` read 387 entries, including `alembic_version` and the
compliance tables, with no errors. The off-host copy is byte-identical (same
size and SHA-256) and is kept outside the repository on the operator workstation.
It was never restored. A local `pg_restore` 16 cannot read the format 1.16
archive that PostgreSQL 18 writes; restore tooling must be 18.x.

**Verified after the deployment:**

- `https://api.geocore.one/health` 200 `healthy`; `/ready` 200, database reachable.
- `/docs`, `/redoc`, `/openapi.json` now 404 (200 before the launch);
  `/api/v1/billing/plans` still 200.
- Schema unchanged: 52 tables, the five compliance tables present, no migration
  executed. Data intact (23 tenants, 23 users, 7 customers, 5 projects, 3 quotes).
- Catalogue 7 manufacturers, 3 brands, 38 surfaces, 47 variants, 0 suppliers.
- `app.core.staging_fixture` refuses in production.
- Startup logs: migration gate ran `alembic upgrade head` as a no-op, then
  `4d5e6f7a8b9c (head)`, then a healthy Uvicorn start; no 5xx in the launch
  window; web started on Next.js and was ready.
- `app.geocore.one`: login, signup (with Terms and Privacy Policy links), pricing
  (real prices from the API) render; protected routes redirect to `/login` with no
  loop; browser console clean.
- `www.geocore.one`: the home, pricing, request-demo, start and legal pages, plus
  all seven policies (privacy, terms, cookies, acceptable use, copyright takedown,
  data processing, subprocessors) return 200.
- Follow-up cron: new deployment healthy and ready, schedule intact, one service.
  Its first run on the new image is the next 03:00 UTC; the last run before the
  launch (8 Oct 03:00Z) succeeded.

**Not performed (outstanding).** Live signup, email verification, login, the genuine
14-day no-card trial, the compliance Settings controls, and creating a customer,
project and quote on production require creating a production account and entering
a password, which the launch automation was not permitted to do. They should be run
by the owner with one disposable synthetic tenant, never with the staging fixture.
The customer portal, command centre and notifications surfaces were not exercised
for the same reason.

**Finding unrelated to this release.** The apex `https://geocore.one` presents a
certificate that does not match (Railway shows its certificate as `ISSUING` and the
apex CNAME as unset), while `https://www.geocore.one` is valid. This predates the
launch, marketing was not touched, and DNS was not changed. It needs the owner's
DNS/certificate attention (see `docs/DNS_GEOCORE_ONE.md`).

**Rollback target.** Railway rollback to the previous API (`668cd773`) and web
(`11b82c4b`) deployments while they remain rollback-able; otherwise redeploy commit
`d8f6627`, which contains migration `4d5e6f7a8b9c`. Never `1855657`. The database
stays at `4d5e6f7a8b9c`; no downgrade.

**Accepted exception.** `logs_request_ids` remains blocked by design. Request IDs
were observed naturally in the production logs; no failure was induced.

**Verdict.** Production promotion succeeded and the deployed release is healthy.
Full launch verification is **not yet complete** until the owner-run authenticated
acceptance above passes.
