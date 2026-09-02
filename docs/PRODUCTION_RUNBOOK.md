# SIMO OS — Production Release and Operations Runbook

**Scope:** Provider-neutral backend release, rollback, health, and persistent-upload operations for Sprint 018.

This runbook is the production contract. It does not select a hosting provider. Replace image names, database hosts, and deployment-system commands with the operator's actual values, but preserve the order and stop conditions below.

## 1. Production prerequisites

Before a release, provide the backend application and the one-off release job with the same production configuration. Never write secret values into command output, image layers, or this document.

Required runtime inventory:

- `APP_ENV=production`
- `DATABASE_URL` set to the production PostgreSQL database, not the repository development default
- `JWT_SECRET_KEY` set to a non-default secret of at least 32 characters
- `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` set to non-default values; the password must be at least 12 characters
- `SEED_DATA_ENABLED=false`
- `CORS_ALLOWED_ORIGINS` set to one or more comma-separated HTTPS browser origins
- `UPLOAD_DIR` set to an absolute path backed by persistent storage
- `READINESS_TIMEOUT_SECONDS` left at its two-second default or set to a positive value no greater than two seconds

For the frontend production build, set `APP_ENV=production` and `NEXT_PUBLIC_API_URL` to the deployed backend's absolute HTTPS origin. The URL must contain no credentials, wildcard, loopback host, path, query, or fragment. `APP_ENV` is SIMO OS deployment intent and is separate from Next.js `NODE_ENV`; a normal local/CI optimized build may leave it unset and retain the loopback fallback.

The production upload path must already exist before application startup. The container's non-root application user must be able to create and remove files in it. Production startup tests writability with a temporary private probe; it does not create a missing production directory and does not delete or rewrite an existing customer document.

Record, outside this repository, who owns the database and upload-volume backups, the backup schedule and retention, the restore location, and the last successful restore test. A volume without a tested restore process is not production-ready.

## 2. Normative release sequence

Run these gates in order. Any failure blocks traffic promotion.

1. Mount the persistent `UPLOAD_DIR`, supply the production environment, and verify the intended release image.
2. Run the read-only configuration preflight using that image/environment:

   ```text
   python -m app.core.runtime_check
   ```

   Require exit code 0. The success output is sanitized and contains only the environment, safe database host/name metadata, CORS-origin count, upload path, and seed-enabled state. It does not contact PostgreSQL, migrate, create directories, or seed data.
3. Run migrations as a one-off release command/job using the new application image:

   ```text
   alembic upgrade head
   ```

   This is never an application-container startup command.
4. Require migration success, then verify that the current revision and the repository's only head agree:

   ```text
   alembic current
   alembic heads
   ```

   Stop if `current` does not report the same sole head as `heads`.
5. Start or restart the backend application containers. The default container process starts only Uvicorn with `app.main:app`; it does not run Alembic or seed data.
6. Poll the dependency-free liveness endpoint until it succeeds:

   ```text
   GET /health
   200 {"status":"healthy"}
   ```
7. Poll database-aware readiness until it succeeds:

   ```text
   GET /ready
   200 {"status":"ready","database":"reachable"}
   ```
8. Make a minimal authenticated API request. On first setup and after any storage change, also complete the upload persistence smoke test in §4.
9. Only after every prior gate succeeds, route production traffic to the new release.

Capture the preflight, migration, revision, startup, and health outputs in the deployment system. Do not promote a release merely because `/health` passes: liveness does not establish database availability or migration state.

## 3. Health-check interpretation

Both health routes are unversioned and unauthenticated. Every response includes an `X-Request-ID` header for correlation.

| Observation | Meaning | Operator action |
|---|---|---|
| `/health` fails | The application process cannot serve HTTP or startup failed. | Keep traffic blocked; inspect `startup_failed` and container logs, then restart only after correcting the cause. |
| `/health` is 200; `/ready` is 503 | The process is alive, but PostgreSQL is unavailable or the bounded probe timed out. | Keep traffic blocked; inspect `readiness_failed`, database networking, credentials, and availability. |
| Both are 200; Alembic revision check failed | HTTP and PostgreSQL connectivity work, but schema state is unverified or wrong. | Keep traffic blocked; repair the release migration state. `/ready` does not certify an Alembic revision. |
| Both are 200 after migration verification | The runtime gates pass. | Complete the authenticated and storage smoke checks before promotion. |

Readiness failure returns only `503 {"status":"not_ready","database":"unreachable"}`. Database hosts, credentials, connection strings, driver errors, and stack traces must remain in protected operator logs, never in the response.

## 4. Persistent upload-volume operations

Sprint 018 retains local filesystem document storage. Supported production topology is one backend application instance, or multiple instances that all mount the same correctly supported persistent filesystem. Independent per-instance disks are unsupported because different instances would see different customer documents.

Before accepting real uploads:

1. Confirm `UPLOAD_DIR` is an absolute mounted path and is owned or writable by the non-root application UID.
2. Start the application with the mount and require `/health` and `/ready` success.
3. Through an authenticated tenant account, upload a uniquely named test document against a test customer.
4. Download it through the authenticated document route and verify its contents.
5. Restart or replace the application container without deleting or recreating the mounted volume.
6. Download the same document again, including through an active client-portal link if that path is in production use.
7. Remove the test record/file using the approved operational process; the product has no document-delete endpoint.

Back up both PostgreSQL metadata and upload-volume bytes on a coordinated schedule. A restore test must restore the database and volume to a mutually consistent recovery point, then verify authenticated and portal downloads. Application rollback never rolls back or removes the volume.

## 5. Application rollback

An application rollback deploys the previous application image with the same production environment and persistent upload volume. It does **not** run `alembic downgrade` automatically.

Rollback is permitted only when the previous image is known to be compatible with the database schema currently at head. If compatibility is unknown, stop and assess before deploying the old image; do not guess while traffic is live.

Application rollback sequence:

1. Stop traffic promotion or drain the failed release according to the deployment platform.
2. Confirm the previous image is schema-compatible with the current database revision.
3. Deploy the previous image without changing the database or upload volume.
4. Verify `/health`, `/ready`, the current/sole Alembic head, one authenticated request, and document persistence.
5. Restore traffic only after all gates pass.

## 6. Explicit database downgrade policy

There is no automated database downgrade path. `alembic downgrade -1` is an explicit operator action and is not the default response to a failed release. Prefer a forward fix or a schema-compatible application rollback.

A database downgrade may be considered only when all of these conditions are satisfied:

- the exact migration's downgrade has been reviewed and tested as safely reversible;
- data-loss and compatibility implications are understood and accepted by the accountable operator;
- incompatible application writers are stopped or otherwise prevented from writing;
- a current database backup exists and access to a verified restore procedure has been confirmed;
- the target application image is compatible with the downgraded schema.

After an approved downgrade, verify `alembic current` against the intended revision, start the compatible application, run `/health` and `/ready`, exercise an authenticated request and document download, and only then restore traffic.

## 7. Logging and incident correlation

Production application logs are one JSON object per line on stdout/stderr. Stable Sprint 018 events are `http_request_completed`, `unhandled_exception`, `readiness_failed`, and `startup_failed`. Use the response's `X-Request-ID` to find request-scoped records. Client-provided request IDs are accepted only when they match the bounded safe character contract; otherwise the backend generates a UUID.

Routine logs contain route templates rather than concrete URLs and omit query strings, authorization headers, bodies, secret values, and database URLs. Do not weaken these boundaries while investigating an incident. A full APM or metrics platform is outside Sprint 018.

## 8. Container and migration boundaries

The provider-neutral production image runs as a dedicated non-root user, exposes port 8000, and starts only Uvicorn by default. Its liveness health check calls `/health`; the deployment traffic gate must separately call `/ready`.

Use the same image with an operator override for the one-off `alembic upgrade head` release job. Never add Alembic, seed commands, or an entrypoint wrapper to normal backend startup. Production `SEED_DATA_ENABLED` must remain `false`; production application startup creates no users, materials, activities, notifications, or other sample rows.

## 9. Appendix — Railway-specific first-deployment notes (Sprint 030)

These are operational lessons from this project's actual first production deployment on Railway. They supplement, not replace, the provider-neutral gates above.

**Fresh volumes mount root-owned.** A brand-new Railway volume is not automatically owned by the container's non-root user, so `/health`/`/ready` will fail with a permission error on first boot even though the image and config are correct. Fix it with a **temporary, minimal, one-shot initializer deployment**, not by running the real application as root:

1. Set `RAILWAY_RUN_UID=0` on the service.
2. Set a start command that does *only* `chown <uid>:<uid> <UPLOAD_DIR> && chmod 0750 <UPLOAD_DIR>` — nothing else. Temporarily clear `preDeployCommand` too, so a migration step can't run under root.
3. Deploy, confirm the chown/chmod succeeded and that the application process never started (inspect the full deploy log — it should contain no `Uvicorn running` line).
4. Revert `RAILWAY_RUN_UID` and the start-command/`preDeployCommand` overrides, then deploy a **genuinely fresh** build (see below) to bring the normal non-root process back up.

**A same-service "redeploy" can silently reuse a stale build/command.** If a start-command or `preDeployCommand` change doesn't seem to take effect after a redeploy, don't assume the config is wrong — the redeploy action itself may have reused a previous build snapshot's runtime command. Trigger a genuinely new build instead (e.g. `railway up` from a clean `git archive <sha> | tar -x` export of the exact candidate commit) whenever a start-command-level change must be guaranteed to apply.

**A Postgres service's private-network hostname is not always what it looks like it should be.** Railway's official Postgres template self-reports a `DATABASE_URL` using a conventional short hostname (e.g. `postgres.railway.internal`), but that hostname only resolves for other services in the same project/environment if the Postgres service has a matching custom private-network endpoint alias configured. A service without that alias is only reachable at its actual platform-assigned `RAILWAY_PRIVATE_DOMAIN` (its own service name, e.g. `<service-name>.railway.internal`). Before trusting a self-reported `DATABASE_URL`, compare it against `RAILWAY_PRIVATE_DOMAIN` for the same service, and prefer a variable reference built from the latter (e.g. `postgresql+psycopg://${{db-service.PGUSER}}:${{db-service.PGPASSWORD}}@${{db-service.RAILWAY_PRIVATE_DOMAIN}}:${{db-service.PGPORT}}/${{db-service.PGDATABASE}}`) over copying the former verbatim. Also double-check the SQLAlchemy driver qualifier (e.g. `+psycopg`) matches what's actually installed (`psycopg[binary]` vs. the legacy `psycopg2`) — a bare `postgresql://` scheme defaults to `psycopg2` regardless of what the host is.
