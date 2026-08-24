# Sprint 019 — Railway Unified Staging Design

**Date:** 2026-08-18
**Status:** Approved — amended by owner decisions on 2026-08-21 and 2026-08-24
**Scope:** Deploy the existing production-hardened SIMO OS release to a production-like Railway staging environment

## 1. Context

Sprint 018 made the repository safe to run in production mode: strict configuration validation, disabled production seeding, explicit CORS, liveness and database readiness, request IDs, structured logging, a non-root backend image, persistent-upload requirements, and a migration-first release contract. Sprint 019 exercises those contracts in a real hosted environment.

This sprint is an infrastructure and operational-readiness sprint. It does not add product features, relax runtime policy, reconcile the roadmap, or send production traffic.

## 2. Goals

Sprint 019 will:

1. Provision one isolated Railway `staging` environment containing separate web, API, and PostgreSQL services.
2. Deploy the existing Next.js frontend and production backend image over Railway-managed HTTPS domains.
3. Connect the API to Railway PostgreSQL only through the environment's private network.
4. mount a persistent upload volume at an absolute path and retain the single-API-instance topology required by filesystem storage;
5. run configuration validation and `alembic upgrade head` in a separate pre-deploy release container before the API starts;
6. configure staging-only secrets without placing values in Git, images, build output, or logs;
7. establish deploy-time liveness, continuous liveness/readiness monitoring, database and upload backups, and tested restore procedures;
8. prove the deployed authentication, core staff workflows, documents, portal, messaging, CORS, tenant isolation, and persistence behavior;
9. document an exact release, rollback, recovery, and operational-verification sequence suitable as the basis for a later production launch.

## 3. Binding constraints

The following Sprint 018 rules remain authoritative:

- The backend and frontend run with `APP_ENV=production` in staging. Railway's environment is named `staging`, but SIMO OS has no weakened `staging` runtime mode.
- Normal backend startup is the Docker image's Uvicorn-only command.
- Alembic never runs in `ENTRYPOINT`, `CMD`, FastAPI lifespan, or a normal application restart.
- The release migration is a separate Railway pre-deploy command and a non-zero exit blocks deployment.
- `SEED_DATA_ENABLED=false`; no users, demo rows, materials, activities, notifications, or other data are seeded automatically.
- The backend runs as the existing non-root UID 10001 after initial storage preparation.
- The frontend uses an exact HTTPS API origin and the backend allows only the exact HTTPS frontend origin through CORS.
- The upload path is absolute, mounted, writable, persistent, and served by one backend instance.
- `/health` is dependency-free. `/ready` performs the bounded PostgreSQL probe and does not certify migration state.
- Existing JWT, role, tenant filters, portal-token hashing, expiry, revocation, and customer scoping are unchanged.

## 4. Approved architecture

One Railway project named `simo-os` contains one isolated Railway environment named `staging`:

```text
simo-os / staging
├── simo-web-staging        Next.js public service
├── simo-api-staging        FastAPI public service, one replica
│   └── simo-uploads-staging persistent volume mounted at /var/lib/simo-os/uploads
└── simo-postgres-staging   Railway-managed PostgreSQL, private application access
```

Both application services deploy from the same Git repository and the pinned `main` commit selected for the staging release. They remain independently buildable and deployable. PostgreSQL and API traffic stays inside the Railway environment's private network; browsers reach only the public web and API HTTPS origins.

### 4.1 Service build and runtime boundaries

`simo-api-staging` builds from the repository-root `Dockerfile`. Set `PORT=8000`, matching the image's exposed port, Docker health check, and Uvicorn command. The start command is not overridden.

`simo-web-staging` uses the repository root as its build context because it is a pnpm/Turbo workspace. Its service configuration installs the pinned pnpm workspace, builds only `web`, and starts the Next.js production server on Railway's injected port. Any repository change required to make that production artifact self-contained belongs to Sprint 019 implementation and must not change product behavior.

Automatic deploy-on-push is disabled until the staging release workflow and smoke gates are proven. The first deployment is pinned to an exact commit. Later staging auto-deployment may be enabled only with the same pre-deploy and verification gates.

## 5. Naming and domain strategy

### 5.1 Railway resources

| Resource | Required name |
|---|---|
| Railway project | `simo-os` |
| Railway environment | `staging` |
| Frontend service | `simo-web-staging` |
| Backend service | `simo-api-staging` |
| PostgreSQL service | `simo-postgres-staging` |
| Upload volume | `simo-uploads-staging` |

Resource names include the environment even though Railway also scopes resources by environment. This makes logs, dashboards, backups, and operator commands unambiguous.

### 5.2 Initial staging domains

Sprint 019 uses Railway-generated TLS domains. Generate both domains before configuring either application so the circular frontend/API references are resolved before the first build:

- frontend origin: `https://${{simo-web-staging.RAILWAY_PUBLIC_DOMAIN}}`;
- API origin: `https://${{simo-api-staging.RAILWAY_PUBLIC_DOMAIN}}`.

The rendered values, not the template expressions, are recorded in the deployment evidence. Browser traffic never uses `.railway.internal`.

No custom domain is purchased or configured in Sprint 019. The reserved future convention is:

- frontend: `https://staging.<owned-domain>`;
- API: `https://api.staging.<owned-domain>`.

Moving to those names later is an explicit coordinated change to DNS/TLS, `NEXT_PUBLIC_API_URL`, and `CORS_ALLOWED_ORIGINS`, followed by a frontend rebuild and the full CORS/smoke gate.

## 6. Environment-variable and secret matrix

Railway variables are scoped to the `staging` environment. Sensitive values are sealed in Railway and are never copied to committed `.env` files. Reference variables are preferred over duplicated URLs.

### 6.1 Backend and release container

| Variable | Staging value/source | Classification | Rule |
|---|---|---|---|
| `APP_ENV` | `production` | config | Exercises strict Sprint 018 policy. |
| `PORT` | `8000` | config | Matches the unchanged Docker/Uvicorn command and Railway health-check port. |
| `DATABASE_URL` | `${{simo-postgres-staging.DATABASE_URL}}` | secret reference | Private Railway connection only; shared by API and its pre-deploy container. |
| `JWT_SECRET_KEY` | newly generated, at least 32 characters | sealed secret | Unique to staging; never reused from development or production. |
| `JWT_ALGORITHM` | `HS256` | config | Existing supported algorithm. |
| `JWT_EXPIRE_MINUTES` | `60` | config | Existing contract. |
| `SEED_ADMIN_EMAIL` | non-default staging-only value | sealed secret | Required by strict validation but never used because seeding is disabled. |
| `SEED_ADMIN_PASSWORD` | unique random value, at least 12 characters | sealed secret | Required by strict validation; never used to create an account. |
| `SEED_DATA_ENABLED` | `false` | config | Mandatory. |
| `CORS_ALLOWED_ORIGINS` | exact rendered frontend HTTPS origin | config | One origin, no wildcard, path, query, fragment, or trailing slash. |
| `READINESS_TIMEOUT_SECONDS` | `2` | config | Existing maximum. |
| `UPLOAD_DIR` | `/var/lib/simo-os/uploads` | config | Exactly equals the persistent-volume mount path. |
| `OPENAI_API_KEY` | unset unless separately authorized | sealed optional secret | AI drafting may return its documented unconfigured response; it is not a staging launch gate. |
| `OPENAI_MODEL` | existing default unless key is authorized | config | No deployment dependency. |

Railway-provided metadata variables may be used for deployment evidence, but the application does not require them. `DATABASE_PUBLIC_URL` is not supplied to the application.

### 6.2 Frontend build and runtime

| Variable | Staging value/source | Classification | Rule |
|---|---|---|---|
| `APP_ENV` | `production` | build/runtime config | Activates the strict frontend deployment-intent gate. |
| `NEXT_PUBLIC_API_URL` | `https://${{simo-api-staging.RAILWAY_PUBLIC_DOMAIN}}` | public build config | Exact public API origin; no path or trailing slash. It is intentionally browser-visible. |
| `PORT` | Railway-provided | runtime config | Next.js listens on the injected port and `0.0.0.0`. |

No JWT, database, seed, Railway API, or other backend secret is present in the frontend service or client bundle.

### 6.3 PostgreSQL

Railway manages the PostgreSQL credentials and service volume. The API consumes only the referenced private `DATABASE_URL`. Operator access for backup/restore uses a time-bounded Railway CLI tunnel where practical. Public TCP credentials must not be copied to application services, committed files, shell history, smoke-test output, or logs.

## 7. Persistent upload-volume contract

Attach `simo-uploads-staging` only to `simo-api-staging` at `/var/lib/simo-os/uploads`. Keep the API replica count at exactly one. Railway volume attachment prevents overlapping deployments, so brief API downtime during a volume-backed redeploy is accepted for staging and must be observed during the restart test.

Railway mounts a new volume as root, while the image's steady-state process is UID 10001. Before the first API application deployment, perform a one-time, no-traffic initialization deployment:

1. attach the empty volume at the approved path;
2. temporarily set `RAILWAY_RUN_UID=0` and replace the service command with `chown 10001:10001 /var/lib/simo-os/uploads && chmod 0750 /var/lib/simo-os/uploads`, targeting only the new empty mount root;
3. require the initializer to exit successfully;
4. remove the root override and initializer command before starting the API;
5. deploy the unchanged image command and prove the running process UID is 10001 and the sole application process is Uvicorn;
6. prove the startup writability probe succeeds without deleting existing files.

The root override is never present on a traffic-serving deployment and is not added to repository configuration. Reusing it on a non-empty volume requires an explicit operator review; routine releases and restarts never run `chown`, migration, seeding, or any other wrapper. A restored volume must be inspected for ownership before traffic is restored.

No customer upload is stored in the image or ephemeral filesystem. Volume capacity and utilization are checked before every release. Reaching the alert threshold triggers capacity expansion or an upload freeze; it does not silently fall back to ephemeral storage.

## 8. Migration and deployment sequence

### 8.1 First staging deployment

1. Verify local `main` and `origin/main` identify the approved release commit and the repository verification gates are green.
2. Create the Railway project/environment and the three named services without deploying application traffic.
3. Generate the two Railway public domains and record their rendered HTTPS origins.
4. Configure PostgreSQL and its backup policy, then configure the private reference `DATABASE_URL` on the API.
5. Create and initialize the upload volume exactly as §7 specifies. Remove the temporary root/command overrides and verify final service configuration before continuing.
6. Configure all backend variables and sealed secrets. Run `python -m app.core.runtime_check` in the release image and require sanitized exit 0.
7. Configure the API pre-deploy command as:

   ```text
   python -m app.core.runtime_check && alembic upgrade head && alembic current
   ```

   The pre-deploy container has the API environment and private network, but no upload volume. These commands must not read or write the upload filesystem. A non-zero exit blocks application deployment.
8. Independently record `alembic heads` from the release image and require one repository head. After pre-deploy, require `alembic current` to equal that sole head.
9. Deploy the API with its unchanged Uvicorn-only command, one replica, port 8000, and Railway deploy-time health-check path `/health`.
10. Require `/health=200`, then `/ready=200`, and inspect sanitized structured startup/request logs before any workflow test.
11. Configure the frontend with the exact API HTTPS origin, build with `APP_ENV=production`, and deploy the Next.js production server.
12. Require the frontend HTTPS check, allowed-origin CORS check, and complete smoke matrix in §13.
13. Capture deployment IDs, commit SHA, image/build identifiers, domains, migration revision, backup configuration, smoke results, and rollback target. Mark staging accepted only after every gate passes.

### 8.2 Normal staging release

For every later release:

1. identify the exact commit and last known-good web/API deployments;
2. run repository CI and production configuration checks;
3. take/confirm the required pre-migration database backup;
4. build the new services;
5. let the API pre-deploy container validate configuration and migrate to head;
6. verify migration success before the new API starts;
7. deploy API, then require `/health` and `/ready`;
8. deploy/rebuild web when its code or public API origin changed;
9. run the release smoke subset, CORS checks, and log/secret audit;
10. promote the release record to accepted staging.

Migrations are never coupled to normal process restarts. A failed pre-deploy command leaves the new API deployment inactive and triggers investigation; it does not trigger an automatic downgrade.

## 9. Health checks and monitoring

Railway's API deployment health-check path is `/health`. It is a deploy-time liveness gate, not continuous monitoring and not proof of database or schema readiness. Set `PORT=8000`; retain the endpoint's dependency-free `200 {"status":"healthy"}` contract.

Continuous staging monitoring uses a repository-owned GitHub Actions scheduled workflow, also manually dispatchable, to make five-minute HTTPS probes from outside Railway:

- frontend root must return a successful page response over valid TLS;
- API `/health` must return 200 and the exact healthy payload;
- API `/ready` must return 200 and the exact database-reachable payload;
- response headers for API probes must include a valid `X-Request-ID`.

The monitor needs no application credentials and records no portal links. A failed run alerts repository operators through GitHub Actions; `/health` failure identifies process/service availability, while `/health=200` plus `/ready=503` identifies a database-readiness incident. Railway deployment/crash notifications remain enabled. The schedule is a best-effort staging signal rather than an uptime SLA; full APM and business metrics remain out of scope.

Migration revision is checked at release time, not on every readiness request. `/ready=200` never substitutes for `alembic current == alembic heads`.

## 10. Backup and restore design

### 10.1 Fresh PITR-window matched recovery-point amendment

The immutable historical recovery run `s019-recovery-20260823T160400Z` remains valid evidence, including its local and Restricted Google Drive artifacts, but it is not eligible for the PITR scratch drill: its requested database recovery timestamp (`2026-08-23T16:08:45.495Z`) is later than the freshly observed Railway `maxRestoreTime` (`2026-08-23T15:22:54.774258Z`). No historical artifact is renamed, overwritten, reinterpreted, deleted, or used as a substitute for the required PITR-backed drill.

Before creating a replacement recovery point, the operator must obtain fresh read-only Railway PITR status and the existing identity-aware archive-health evidence. The entry gate records `minRestoreTime`, `maxRestoreTime`, `enabled`, `bucketWired`, `backupSetCount`, and `archiverHealthy`; it fails closed unless PITR is healthy and the PostgreSQL archive checks remain healthy. A stale restore window is never used.

Only when execution begins, generate a distinct immutable UTC `RECOVERY_RUN_ID` in the existing `s019-recovery-YYYYMMDDTHHMMSSZ` form. It derives a new database backup label, upload backup label, local artifact directory, Drive artifact names, correlation metadata, and scratch-resource names. It must never reuse `s019-recovery-20260823T160400Z` or its paths.

Within one approved maintenance window, create the supported new database-side and upload-side recovery anchors as close together as safely possible, without application downtime and with the active upload source read-only. Record safe Railway IDs, external IDs where supplied, creation timestamps, the authoritative database `recovery_target`, and the actual database/upload timestamp gap. The new database target is eligible for a PITR restore only when fresh status proves:

```text
minRestoreTime <= recovery_target <= maxRestoreTime
```

If capture completes after the then-current `maxRestoreTime`, preserve the new artifacts, re-query fresh PITR status, and wait/probe read-only until `maxRestoreTime` reaches the recorded target. Do not silently fall back to a logical-dump-only database restore. If the window does not advance sufficiently, stop and record the blocker without attempting scratch creation or restore.

This design has no separately approved maximum database-to-upload timestamp gap. The existing RPO objective (at most 24 hours from scheduled backups) is not a maximum pairing gap. Therefore the procedure must fail closed: it may preserve the new anchors and record the actual gap, but it must not call them a matched pair or begin the scratch PITR drill until the owner explicitly accepts that recorded gap for that run. Correlation metadata must state the authoritative PITR target, both anchors, their timestamps and IDs, the actual gap, the acceptance evidence, and the observed RPO age.

The replacement run produces its own custom-format PostgreSQL dump, uncompressed PAX TAR upload archive, SHA-256 manifest, and correlation evidence. All retain the established safety protections and private 30-day Drive retention. The scratch design remains unchanged: Railway PITR restores only to a sibling PostgreSQL service, and uploads restore only to an isolated scratch service and new scratch volume; active staging is never restored, remounted, or modified.

### 10.2 PostgreSQL protection

Before staging acceptance:

- enable Railway daily volume backups;
- create a manual database backup immediately before any migration that can alter data or schema;
- enable Railway PITR and confirm its first base backup completed;
- take a portable `pg_dump --format=custom --no-owner` through a Railway CLI tunnel and store it outside the Railway project in access-controlled storage;
- perform one initial `pg_restore --no-owner --exit-on-error` drill into a distinct scratch database on the non-traffic PITR-restored sibling PostgreSQL service, verify Alembic revision and representative row counts, record duration/recovery point, then remove only the explicitly named scratch database after approval.

Daily snapshots provide the baseline staging recovery point; PITR narrows recovery for database mistakes; the logical dump protects against project/volume deletion and provider lock-in. Backup metadata contains no secrets.

### 10.3 Upload-volume protection

Enable Railway daily backups for `simo-uploads-staging` and take a manual snapshot before risky storage operations. The database and upload recovery points are timestamped in the same approved maintenance window because document rows and files must be restored coherently.

Railway native volume restore is deliberately not used for the initial upload recovery drill. Railway restores a volume backup to its source service/environment by staging a replacement at the original mount path; applying that change can unmount the active volume and redeploy `simo-api-staging`. That behavior is incompatible with the required non-traffic validation target, so it is rejected for this drill.

Instead, create a portable matched upload backup in the same maintenance window as the selected database recovery point. The recovery-only artifact must:

- preserve every upload's exact storage filename and relative path below `/var/lib/simo-os/uploads`;
- contain a SHA-256 integrity manifest mapping each archived relative path to its digest and recording the backup timestamp and paired database recovery-point identifier;
- contain no credentials, bearer values, portal tokens, request bodies, or other secrets;
- form, together with its SHA-256 manifest, the matching PostgreSQL custom-format logical dump, and recovery-point correlation metadata/evidence, one recovery bundle retained for 30 days in the private Google Drive folder `SIMO OS Recovery / Staging / Sprint 019`; access is owner-only by default, extends only to explicitly approved administrators, and never uses public or shared links; and
- remain isolated from normal application request handling, deployment startup, and production/staging runtime storage.

#### Approved temporary remote creator execution

For the one approved operator recovery operation, the locally authored and reviewed creator may execute in the API container's mount namespace without becoming deployed application software. This narrowly supersedes only the prior prohibition on copying recovery scripts into Railway: verified, transient copies under one unique `/tmp` directory are permitted for this operation; copying scripts into the image, application directory, or `/var/lib/simo-os/uploads` remains prohibited. This is recovery tooling, not application runtime behavior.

The operator determines the exact local dependency closure of `scripts/recovery/matched_bundle.py` (including `recovery_safety.py` and no unreviewed import), records a SHA-256 digest for every transferred script, and uses only the explicit Railway project `ff9b6a65-61bb-445c-a698-306f1e2c04b1`, environment `58f1f618-f823-4c02-80b6-b1d6b630bb76`, and API service `375a8ff5-c6bb-4c47-ab96-40b7a9b0d06f`. The operation never uses `railway link` or an inferred project name. It creates a unique, recovery-run-scoped directory below `/tmp`, transfers only that verified dependency closure using byte-safe transport, and requires every remote script digest to equal its locally recorded digest before execution.

`matched_bundle.py` then runs from that temporary directory with `/var/lib/simo-os/uploads` as a read-only source. Its archive and manifest outputs are written only under the same temporary `/tmp` recovery directory. The creator retains its source-side regular-file pinning, no-follow and identity checks, swap/TOCTOU rejection, normalized-path collision rejection, Windows-alias rejection, and creator/restore portable-path parity. No source upload is changed, followed unsafely, or copied into an application path.

The operator records remote archive and manifest sizes and SHA-256 digests, transfers both artifacts to the local recovery directory with byte-safe transport, and requires exact local/remote size and digest equality. A separate local invocation of the approved restore/verification tooling independently validates manifest membership and every manifest SHA-256 in an isolated local verification directory before correlation metadata is finalized. The metadata must identify the matched database and upload recovery points, the recovery run, and the already-verified logical-dump digest/size/TOC count; it must contain no credentials, tokens, passwords, database URLs, or authorization material.

Only after local integrity evidence is captured may the operator remove the exact proven unique `/tmp` recovery directory and its temporary remote artifacts. The source mount, valid Railway backups, deployed image, service configuration, variables, and running process remain untouched. After cleanup, verify staging `/health` and `/ready`. Stop immediately on a remote script hash mismatch, unexpected dependency, required source modification, unsafe source acceptance/following, archive or manifest verification failure, remote/local artifact mismatch, inability to prove the cleanup target is the unique `/tmp` recovery directory, or any need for a deployment, restart, or configuration mutation.

Google Drive is recovery storage only. It is never mounted by the application, referenced by runtime configuration, or used to serve ordinary staff or portal document requests. At the end of the 30-day retention period, the recovery bundle is removed unless the owner explicitly extends retention.

The initial drill restores the portable upload artifact only into a newly named scratch recovery service with a newly attached scratch upload volume. The scratch service receives no public domain, customer traffic, production/staging `DATABASE_URL`, or live upload mount. It is paired with a separate Railway PITR-restored sibling PostgreSQL service; neither restored target replaces, remounts, or writes to `simo-postgres-staging` or `simo-uploads-staging`.

After restoration, verify one representative staff-authenticated document download and one representative portal document download only against the paired scratch targets. Require the restored document bytes to match the manifest digests and require document metadata, tenant/customer ownership, portal scope, and database/upload recovery-point identifiers to correlate. A missing file, digest mismatch, ownership mismatch, inaccessible scratch mount, or mismatch between the recorded database and upload recovery points fails the drill and leaves active staging unchanged. Record measured RTO and the actual recovery-point age as RPO. The 30-day Google Drive retention does not govern temporary Railway scratch resources: remove only the explicitly named scratch service and scratch upload volume after successful drill verification, evidence capture, and explicit operator cleanup approval.

### 10.3 Recovery procedure

1. stop or block application writers when a consistent recovery point is required;
2. select and record the database and upload recovery points;
3. restore PostgreSQL with Railway PITR to a sibling scratch service and restore the portable matched upload artifact to a separate scratch service/volume, leaving active staging sources intact;
4. verify PostgreSQL starts, `alembic current` is the expected revision, document metadata matches manifest-verified files, and tenant/portal access remains scoped;
5. approve cutover explicitly and update only the required Railway references/mount;
6. validate volume ownership for UID 10001, start the API, then run `/health`, `/ready`, auth, document, portal, and tenant-isolation smoke checks;
7. retain the prior source until the recovery is accepted.

Target recovery objectives for this staging environment are RPO at most 24 hours from scheduled backups and an initially measured—not assumed—RTO. The restore drill records the real RTO; failure to complete a restore is a launch blocker.

## 11. Rollback design

### 11.1 Application rollback

Railway application rollback restores a selected prior deployment's image and custom variables. Before rollback, confirm that deployment is retained and compatible with the database's current schema.

Rollback order:

1. stop further promotion and record the failing deployment IDs/request IDs;
2. determine whether API, web, configuration, database, or storage caused the failure;
3. if schema-compatible, roll back API and/or web to the last known-good Railway deployment;
4. do not change or recreate the upload volume;
5. do not run `alembic downgrade` automatically;
6. require `/health`, `/ready`, current/head verification, authenticated API, document persistence, CORS, and frontend smoke checks before acceptance.

Because Railway rollback restores that deployment's variables as well as its image, operators must re-audit the restored CORS/API URL/database/upload settings before returning staging to service.

### 11.2 Failed migration

If pre-deploy fails, the new API does not start. Preserve the logs, inspect the actual database revision, and prefer a corrected forward migration. The last serving application may continue only if compatible with the observed schema. No retry is automatic.

### 11.3 Explicit database downgrade

Application rollback never downgrades PostgreSQL. A database downgrade is an explicit operator action only when the exact migration's downgrade is reviewed and tested as safely reversible, a current backup exists, data-loss consequences are accepted, incompatible writers are stopped, and the target application is compatible. Afterward, verify revision, health/readiness, auth, documents, portal access, and tenant isolation before reopening traffic.

## 12. Security and tenancy controls

- Only web and API receive public HTTPS domains. PostgreSQL uses private networking for application traffic.
- Railway environment-scoped variables separate staging from any future production environment. Staging secrets are unique and least-privilege.
- Runtime validation remains fail-closed. No setting is weakened for Railway.
- Structured logs and deployment evidence exclude raw environment dumps, database URLs, authorization headers, bodies, concrete portal-token paths, seed passwords, and JWT secrets.
- Smoke data uses synthetic tenants and customers. It contains no real customer or production data.
- Portal tokens are captured only in the controlled test runner's memory and are not written to CI logs or artifacts.
- The public API remains protected by existing JWT/role/tenant rules; CORS is not treated as authorization.
- Cross-tenant probes use known synthetic IDs and require the existing 404/no-disclosure behavior.
- The API stays at one replica while uploads use one filesystem volume. Scaling requires an approved shared/object-storage design in a later sprint.
- The temporary root volume initializer is a recorded provisioning action with no traffic, no application process, and no persistence in final service configuration. Steady state is UID 10001.

## 13. Post-deployment smoke-test matrix

Create two synthetic workspaces, Tenant A and Tenant B, through the public signup flow. Unique run identifiers make records traceable. No test depends on a seeded account.

| Gate | Procedure | Required result |
|---|---|---|
| Frontend HTTPS | Load the Railway web origin in a clean browser session. | Valid TLS, successful page, no mixed content, frontend calls only the approved API origin. |
| API HTTPS | Call the API root over its Railway public domain. | Valid TLS and expected public response. |
| Liveness | `GET /health`. | 200 exact healthy payload and `X-Request-ID`. |
| Readiness | `GET /ready`. | 200 exact database-reachable payload and `X-Request-ID`. |
| PostgreSQL | Observe `/ready`, then run a minimal authenticated create/read. | Private database connection works; no public DB URL is used by API. |
| Migration | Run `alembic heads` in the release image and compare with recorded `alembic current`. | One head; current equals head. |
| No seeding | Inspect an empty database before signup and deployment logs/startup calls. | No demo/Owner/material/activity/notification rows created automatically; `SEED_DATA_ENABLED=false`. |
| Signup/login/auth | Create Tenant A and B owners; login; call `/api/v1/auth/me`; try missing/invalid token. | Valid identities and tenant claims; unauthorized calls return 401 without detail leakage. |
| Customer | Tenant A creates and reads a customer. | Correct tenant ownership and round-trip data. |
| Project | Tenant A creates a project for its customer and advances an allowed status transition. | Project remains linked and visible only to Tenant A. |
| Quote/invoice | Tenant A creates a tenant-tagged quote, lists/reads it, and downloads its invoice PDF. | Quote is tenant-scoped; invoice is valid downloadable PDF. |
| Staff document | Upload a uniquely hashed allowed file for Tenant A's customer, list it, and download it. | Bytes/hash match; stored path is the persistent mount. |
| Restart persistence | Restart/redeploy only the API without replacing the volume, then repeat staff download. | Same document bytes remain available; API returns to healthy/ready. |
| Portal token | Create an active portal link for Tenant A's customer and load its public view. | Only that customer's current portal data is returned. |
| Portal documents | List and download the uploaded document through the active portal token. | Same bytes; no other customer/tenant document appears. |
| Portal messaging | Send staff-to-customer and customer-to-staff messages and poll the thread. | Oldest-to-newest text-only messages; inbound customer message yields exactly one tenant activity and one notification; staff message yields neither. |
| Token enforcement | Revoke a disposable portal link and retry protected portal operations. | Inactive token is rejected without revealing resource existence. |
| Tenant isolation | Tenant B tries Tenant A customer, project, quote/invoice, document, message, and portal-management identifiers; compare list endpoints. | No cross-tenant read/write/linkage; 404/no disclosure where specified; Tenant B lists contain no Tenant A rows. |
| CORS allowed | Send browser preflight and real request with exact frontend `Origin`. | Exact `Access-Control-Allow-Origin` for the frontend. |
| CORS denied | Repeat from an unlisted HTTPS origin, `null`, and a lookalike subdomain. | No permissive allow-origin response; API auth remains independently enforced. |
| Logs/request IDs | Send safe custom and invalid request IDs; inspect correlated JSON logs and error paths. | IDs propagate/replace as designed; route templates used; no tokens, query strings, auth headers, bodies, secrets, or raw DB errors. |
| Repository secret scan | Inspect tracked diff/history and build inputs for environment/local artifacts. | No `.env`, secret, database data, upload, Railway state, or generated build artifact is tracked. |
| Backup/restore | Complete the PITR PostgreSQL sibling restore and the portable matched-upload restore into separate scratch targets. | Restored revision/data/files and SHA-256 manifest validate without modifying, remounting, or redeploying active staging storage. |

The smoke runner redacts tokens and credentials, cleans up only its uniquely identified records where supported, and preserves evidence containing status codes, IDs safe to retain, hashes, deployment IDs, timestamps, and pass/fail results.

## 14. Operational acceptance and evidence

Sprint 019 is complete only when one evidence bundle records:

- exact Git commit, Railway project/environment/service identifiers, and deployment IDs;
- rendered public origins and proof of valid HTTPS;
- sanitized environment-variable inventory and secret-presence checks (never secret values);
- API steady-state UID/process/replica count and Uvicorn-only command;
- pre-deploy command output, sole Alembic head, and matching current revision;
- `/health` and `/ready` results plus continuous-monitor configuration;
- database private-network connection evidence;
- upload mount path, capacity, Railway backup schedule, portable matched-upload artifact/manifest, restart persistence, and scratch-only restore drill;
- PostgreSQL backup/PITR/logical-dump configuration, paired sibling restore drill, and measured RTO/RPO;
- every §13 smoke result, including two-tenant isolation and portal security;
- CORS allowed/denied evidence;
- log redaction and repository secret/artifact audit;
- last known-good web/API rollback targets and a completed rollback rehearsal or non-destructive documented simulation;
- final Railway status showing no root override, no initializer command, no automatic seeding, and no migration in normal startup.

Any failed mandatory gate blocks Sprint 019 acceptance. A known platform limitation is documented rather than hidden or worked around by weakening Sprint 018.

## 15. Expected repository impact

Implementation planning may add only deployment and operational artifacts required by this design, such as Railway service configuration, a production frontend container/build contract if needed, deployment/smoke scripts that redact credentials, a staging runbook, an environment-variable template containing no values, CI/manual verification workflow, ADR/architecture/API/changelog updates, and Sprint 019 completion documentation.

Product APIs, schemas, authorization rules, and user interfaces are unchanged unless deployment evidence proves a genuine repository defect; any such defect requires a separate minimal TDD task within the approved deployment scope.

`docs/ROADMAP.md`, `.agents/`, and `.claude/` remain excluded.

## 16. Explicitly out of scope

- production deployment or production customer traffic;
- purchasing or configuring a custom domain;
- a second API replica while filesystem uploads remain;
- S3/object storage, CDN migration, virus scanning, or storage quotas;
- product feature work, account recovery/email, billing, subscriptions, rate limiting, WebSockets, or full APM;
- weakening configuration, CORS, seeding, logging, JWT, tenant, or portal security;
- automatic Alembic execution or data seeding during backend startup;
- automatic database downgrade;
- importing real production/customer data into staging;
- roadmap reconciliation or modification of `docs/ROADMAP.md`;
- Sprint 020.

## 17. Acceptance criteria

1. The approved four-resource Railway staging topology exists under the exact naming contract.
2. Web and API are separate, pinned to the accepted release commit, and reachable through valid Railway HTTPS domains.
3. API uses Railway PostgreSQL through private networking and reaches the sole Alembic head through a separate successful pre-deploy command.
4. Normal API startup remains Uvicorn-only, non-root, single-instance, migration-free, and seed-free.
5. Strict production backend/frontend validation passes without defaults, loopback URLs, wildcard CORS, relative storage, or exposed secrets.
6. The upload volume is mounted at `/var/lib/simo-os/uploads`, writable by UID 10001, backed up, and survives restart/redeployment with identical document bytes.
7. `/health` and `/ready` meet their distinct contracts at deploy time and under continuous external monitoring.
8. PostgreSQL and upload backups are configured and a non-destructive matched restore drill succeeds: PostgreSQL restores by PITR to a sibling scratch service and uploads restore from the portable manifest-backed artifact to a separate scratch service/volume.
9. Application and database rollback procedures preserve schema, storage, security, and explicit operator control.
10. Every mandatory smoke gate in §13 passes, including auth, customer, project, quote/invoice, documents, portal, messaging, CORS, no-seed, logs, and two-tenant isolation.
11. Deployment evidence contains no secret values or portal tokens, and repository/artifact scans are clean.
12. No application redesign, production launch, custom-domain purchase, roadmap change, Sprint 020 work, commit, or push occurs before its own approval.
