# GeoCore launch: production promotion plan

**Status:** prepared, **not executed**. Production promotion needs explicit owner
authorisation. Evidence for the candidate: `docs/RELEASES/launch-integrated-release.md`.

## 1. What is being promoted

The integrated `main` SHA, recorded when the integration branch was merged
(`git rev-parse origin/main`; fill in below at execution and re-verify it equals
the tested tree plus documentation only):

`INTEGRATED_MAIN_SHA = <fill from origin/main before starting>`

Never promote `13e1474` (it lacks the compliance code production runs). Never
redeploy `production-release` at its current tip `1855657` (it lacks migration
`4d5e6f7a8b9c` and aborts at the migration gate against the production database).

## 2. Verified production topology (read-only, 8 Oct 2026)

| Item | Value |
| --- | --- |
| Railway project | `simo-os` `ff9b6a65-61bb-445c-a698-306f1e2c04b1` |
| Environment | `production` `c5f88dea-8c24-4770-b289-24529b775acb` (never `staging` `58f1f618-...`) |
| API service | `simo-api-production` `9dd930e7-4564-47b5-8cda-7924633cbd9d`, `api.geocore.one`, source branch `production-release`, check suites off |
| Web service | `simo-web-production` `0c47f367-d817-4b99-99ef-dc8b12df6df2`, `app.geocore.one`, source branch `production-release`, check suites off |
| Follow-up cron | `simo-follow-up-production` `5de44840-432b-4bb9-a1a1-9521e5f5cadd`, `0 3 * * *`, source branch `production-release` |
| Marketing | `simo-marketing-production` `688d71a9-26c0-4888-91e3-f57be036d9dd`, `geocore.one`, source branch `fix/start-logo-mark`, check suites on |
| Database | `simo-postgres-production` `079c14f9-44e2-490d-8d02-efed5fef6a28`, Alembic `4d5e6f7a8b9c` |

Current production deployments (record again immediately before starting):

| Service | Deployment | Source |
| --- | --- | --- |
| API | `668cd773-d075-4129-9c84-7ff20e7481b7` | CLI upload, 29 Sep 16:19Z; backend tree identical to `c35ef81`/`d8f6627` |
| Web | `11b82c4b-1739-4412-b905-55fea08efb6a` | CLI upload, 29 Sep 16:33Z |
| Marketing | `d1f0c2c5-1908-47e7-a336-1780ef197f31` | git, `d8f6627` |
| Follow-up | `bb5cd9bc-08ec-46e2-bc94-9c86a71921ed` | git, `1855657` image (24 Sep) |

## 3. What the promotion changes

- **Database: nothing.** `alembic upgrade head` (preDeploy) and the container's
  migration gate are both no-ops because production is already at the repo head
  `4d5e6f7a8b9c`. No migration is applied; none is downgraded.
- **API:** adds the production docs hardening (`/docs`, `/redoc`, `/openapi.json`
  become 404) and the operator-only `app.core.staging_fixture` module (it refuses
  outside Railway `staging`). All compliance code is already present.
- **Web:** the traffic-readiness UI hardening (10 `apps/web` files: auth/demo
  flows, dashboard route, mobile). Compliance UI is unchanged.
- **Marketing:** no change (the tree is identical to what is deployed). No
  marketing deployment is needed or wanted.
- **Follow-up cron:** rebuilt from the new source; the job code is unchanged.

## 4. Pre-flight (all must pass; stop on any failure)

1. `origin/main` is the intended SHA, CI for it is green, and
   `git merge-base --is-ancestor origin/production-release origin/main` is true
   (so `production-release` can fast-forward; it must gain only the 15 reviewed commits).
2. Re-read production state read-only: `python -m alembic current` on the API
   container prints `4d5e6f7a8b9c (head)`; record the four deployment ids above.
3. **Backup:** take a PostgreSQL custom-format dump of production per
   `docs/PRODUCTION_RUNBOOK.md` (private tunnel, never a public proxy), record its
   SHA-256 and size outside git, and confirm the uploads volume is mounted. The
   migration is a no-op, but the dump is the recovery point.
4. Confirm how a push to `production-release` deploys: the API, web and follow-up
   services all track it with check suites off, and a branch push is expected to
   deploy all three at once (they were created at the same instant on 24 Sep).
   This is likely but was not proven; watch for it rather than assume.
5. Note the owner-approved window and have `/health` and `/ready` baselines for
   `api.geocore.one`, and the home/login pages of `app.geocore.one`.

## 5. Promotion action (the only mutating step)

Fast-forward `production-release` to `INTEGRATED_MAIN_SHA` and push it:

```
git fetch origin
git merge-base --is-ancestor origin/production-release origin/main   # must succeed
git push origin origin/main:refs/heads/production-release            # fast-forward only, no --force
```

Then watch the API, web and follow-up deployments in the `production`
environment only. Do not touch the marketing service. Do not change Railway
variables. Do not run anything against the database.

## 6. Post-deploy verification

Immediately, on `https://api.geocore.one`:

- `GET /health` is 200 `{"status":"healthy"}`; `GET /ready` is 200 with the database reachable.
- `GET /docs`, `GET /redoc`, `GET /openapi.json` are all **404** (previously 200).
- Deploy logs show the preDeploy `alembic upgrade head` with no migration run and
  `alembic current` = `4d5e6f7a8b9c (head)`; no "Can't locate revision" error.

Then, using one owner-run synthetic tenant (`s019-` style, created through the
real signup flow, never a customer account):

- Signup, verification, login and the genuine 14-day no-card trial.
- Compliance: Settings privacy controls, workspace export/deletion request flow,
  marketing preferences/unsubscribe, signup consent, and the legal pages on `geocore.one`.
- Catalogue: 38 surfaces, 47 variants, 7 manufacturers, 3 brands, no placeholder suppliers.
- Customer, project, quote and invoice PDF; document upload and download.
- Customer portal: link, documents, messaging, and revoked-token rejection.
- Notifications, and the follow-up job on its next 03:00 UTC run (check its logs).
- Command centre dashboard shape.
- Review deploy and HTTP logs for 5xx and tracebacks for at least 30 minutes.

## 7. Abort and rollback conditions

Roll the application back, without touching the database, if any of these occur:

- `/health` or `/ready` fails, or a deployment crash-loops or aborts at the migration gate.
- Any 5xx spike, login/signup failure, or loss of a compliance control.
- A docs endpoint is still 200 after the new API is live (it indicates an old build is serving).
- Any production data anomaly.

**Application rollback target:** Railway's rollback to the previous deployment of
the affected service (API `668cd773`, web `11b82c4b`) while it is still marked
rollback-able (Railway keeps only the most recent prior deployment; confirm at the
time). If that is unavailable, redeploy from an immutable commit that **contains
migration `4d5e6f7a8b9c`**: `d8f6627` (its backend is identical to what runs today).
Never redeploy `1855657` or the old `production-release` tip.

**Database:** do not downgrade. `4d5e6f7a8b9c` only adds tables, which older
compliant code simply ignores, and a downgrade would drop live compliance tables.
Restoring the pre-deploy dump is a last resort for data corruption only, and needs
separate owner approval.

## 8. Known follow-ups (not part of this promotion)

- Renumber the vault branch's migrations before it merges (it reuses `4d5e6f7a8b9c`).
- Staging also runs `APP_ENV=production`, so it loses the docs endpoints at its next deploy.
- 135 `networkidle` waits remain in the e2e suite (132 outside the one hardened spec).
