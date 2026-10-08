# GeoCore launch: integrated release candidate

**Status:** release candidate built and verified. **Not promoted to production.**

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

## 8. Not done

Production has not been promoted, redeployed or modified. `production-release`
was not touched and remains at `1855657`, which is **not a safe redeploy
target**: it lacks migration `4d5e6f7a8b9c`, so a build from it aborts at the
migration gate against the production database. See
`docs/RELEASES/launch-promotion-plan.md` for the next step.
