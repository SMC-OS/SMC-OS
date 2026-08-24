# Sprint 019 — Railway Unified Staging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver and prove a production-mode, Railway-hosted staging release of SIMO OS without weakening Sprint 018 runtime safety.

**Architecture:** Railway `simo-os/staging` has separate `simo-web-staging`, `simo-api-staging`, and `simo-postgres-staging` services. The API uses private PostgreSQL networking and one persistent upload volume; migration runs in an API pre-deploy container, while the traffic-serving API remains a single non-root Uvicorn process. Recovery adds isolated tooling that creates a portable manifest-backed upload bundle and a matched logical PostgreSQL dump for private Google Drive; restore uses only paired scratch resources and never active staging mounts or runtime paths.

**Tech Stack:** Railway, Docker, FastAPI, Alembic, PostgreSQL, Python standard-library `tarfile`/`hashlib`/`json`, Next.js 16, pnpm 9, Google Drive (operator-managed recovery storage), GitHub Actions, curl, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-sprint-019-railway-unified-staging-design.md`

## Global Constraints

- Use `APP_ENV=production` in Railway staging; SIMO OS has no relaxed staging mode.
- Never run Alembic, seed data, `chown`, or any wrapper from normal backend startup.
- API normal command remains the existing Dockerfile Uvicorn command, one replica, UID 10001.
- Set `SEED_DATA_ENABLED=false`; preserve strict secret, CORS, database, and absolute-upload validation.
- Use generated Railway HTTPS domains only; do not purchase/configure custom domains.
- Keep PostgreSQL private to the Railway environment; frontend communicates with the API public HTTPS domain only.
- Google Drive is recovery storage only: use the private `SIMO OS Recovery / Staging / Sprint 019` folder, owner/explicit-administrator access only, no public/shared link, and 30-day retention for the matched recovery bundle.
- Recovery tooling may create portable artifacts but must never become application runtime storage, be mounted by the API, or participate in staff/portal request handling.
- Never use Railway native volume Restore for `simo-uploads-staging`; it can replace the source mount and redeploy the active API. Never restore over `simo-postgres-staging` or `simo-uploads-staging`.
- Stop for explicit owner approval before enabling PITR (which may redeploy PostgreSQL), changing Google Drive access, creating paid scratch Railway resources, deleting any scratch resource, or taking any action that can affect active staging writers, data, or volumes.
- Do not modify `docs/ROADMAP.md`, start Sprint 020, commit, or push as part of this plan unless a later user explicitly authorizes it.
- Exclude `.agents/`, `.claude/`, `.env*`, uploads, database dumps, Railway tokens, build artifacts, and generated evidence containing secrets/tokens.
- Treat creation/modification of a Railway project, environment, service, domain, variable, volume, backup, deployment, restart, restore, or rollback as an external state mutation requiring the gate in Task 6.
- For every recovery drill, create one safe identifier `RECOVERY_RUN_ID` in the exact form `s019-recovery-YYYYMMDDTHHMMSSZ`. Derive every mutable artifact from it: PostgreSQL backup `${RECOVERY_RUN_ID}-postgres`, upload backup `${RECOVERY_RUN_ID}-uploads`, Drive files `${RECOVERY_RUN_ID}-uploads.tar`, `${RECOVERY_RUN_ID}-uploads.manifest.json`, `${RECOVERY_RUN_ID}-postgres.dump`, and `${RECOVERY_RUN_ID}-correlation.json`, sibling database service `simo-postgres-recovery-${RECOVERY_RUN_ID}`, scratch recovery API `simo-api-recovery-${RECOVERY_RUN_ID}`, and scratch volume `simo-uploads-recovery-${RECOVERY_RUN_ID}`.
- `s019-recovery-20260823T160400Z` is immutable historical evidence only. Its selected database timestamp fell outside the observed Railway PITR restore window, so it must not be renamed, overwritten, reinterpreted as restore-ready, or used for the PITR scratch drill.
- Immediately before a new recovery-point capture, fetch fresh read-only PITR state: `minRestoreTime`, `maxRestoreTime`, `enabled`, `bucketWired`, `backupSetCount`, and `archiverHealthy`, together with the existing identity-aware archive checks. Fail closed unless all remain healthy.
- Generate a new run ID only at execution start. Do not choose it from an old timestamp. The authoritative `recovery_target` must satisfy `minRestoreTime <= recovery_target <= maxRestoreTime` on a fresh query before any scratch PITR restore. If capture is newer than `maxRestoreTime`, preserve evidence and probe read-only until the window advances; never replace the PITR gate with a logical-dump-only restore.
- No approved maximum database/upload pairing gap currently exists; the 24-hour RPO objective is not such a limit. Record the actual gap and fail closed: do not label the anchors matched or begin the scratch drill until the owner explicitly accepts that run's recorded gap.

---

## File and responsibility map

| File | Action | Responsibility |
|---|---|---|
| `apps/web/Dockerfile` | Create | Non-root standalone Next.js production image built from the workspace root context. |
| `apps/web/next.config.ts` | Modify | Set Next.js standalone output without changing runtime API URL validation. |
| `deploy/railway/api.railway.toml` | Create | API config-as-code: root Dockerfile, pre-deploy release command, `/health`, restart policy; no start-command override. |
| `deploy/railway/web.railway.toml` | Create | Web config-as-code: web Dockerfile, health path, build/start settings. |
| `deploy/railway/staging.env.example` | Create | Names-only, secret-free Railway variable inventory and reference syntax. |
| `scripts/staging/smoke.py` | Create | Redacting, environment-driven 22-gate HTTPS/API workflow runner; no credential/token output. |
| `scripts/staging/check-health.ps1` | Create | Credential-free frontend/API `/health`/`/ready` monitor used locally and by CI. |
| `scripts/recovery/matched_bundle.py` | Create | Recovery-only portable upload archive and SHA-256/correlation-manifest creator; never imports application runtime code or Drive credentials. |
| `scripts/recovery/restore_upload_bundle.py` | Create | Recovery-only manifest verifier and safe extractor for an explicitly named scratch upload mount; rejects active staging paths and path traversal. |
| `.github/workflows/staging-monitor.yml` | Create | Five-minute/manual external monitor; accepts only public origins, no application secrets. |
| `.github/workflows/ci.yml` | Modify | Add Docker build and strict frontend production-build gates; keep existing test gates. |
| `docs/STAGING_RUNBOOK.md` | Create | Exact provision/deploy/backup/restore/rollback/operator evidence procedure, including the private Google Drive recovery bundle and scratch-only restore gates. |
| `docs/DECISIONS.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md`, `docs/CHANGELOG.md`, `docs/SPRINTS/sprint-019.md` | Modify/Create | Record Railway staging decision, service boundaries, health/monitoring operations, and completion evidence. |
| `docs/ROADMAP.md` | Do not modify | Explicitly excluded. |

## Task 1: Local baseline and release candidate verification (sequential, read-only)

**Files:** no changes.

- [ ] Run `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, and `git rev-list --left-right --count origin/main...HEAD`.
- [ ] Require `main`, a clean tracked tree, and only the intentionally untracked `.agents/`/`.claude/` directories plus the approved Sprint 019 design/plan work; stop if unrelated tracked changes exist.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/ -q`, `alembic current`, `alembic heads`, `alembic check`, `pnpm lint`, `pnpm check-types`, `pnpm --filter web test:runtime-config`, and `pnpm build`.
- [ ] Run strict build proof: set only `APP_ENV=production` and a safe synthetic HTTPS `NEXT_PUBLIC_API_URL`, then run the web build; separately prove missing and loopback URLs fail before a build completes.
- [ ] Run `docker build --tag simo-os:staging-candidate .`; inspect image user, command, health check, and `.dockerignore` exclusions. Record image ID, never credentials.
- [ ] Run `git diff --check` and a tracked-file secret/artifact scan: `git ls-files | rg '(^|/)(\.env|uploads|.*\.dump|.*\.sql|\.railway)(/|$)|\.pem$'` must print nothing.

**Exit:** all local gates pass; record exact commit SHA as `STAGING_RELEASE_SHA` outside the repository.

## Task 2: Add/test frontend production artifact (TDD; safe parallel stream after Task 1)

**Files:** Create `apps/web/Dockerfile`; Modify `apps/web/next.config.ts`; Test `apps/web` build commands.

- [ ] Write a failing container/build assertion that requires `output: "standalone"`, a non-root web image, `HOSTNAME=0.0.0.0`, and no build-time backend secrets.
- [ ] Run the assertion and prove RED against the current non-standalone config.
- [ ] Add `output: "standalone"` to the existing `nextConfig`; retain its current `resolveApiBaseUrl()` call unchanged.
- [ ] Add a multi-stage `apps/web/Dockerfile` using repository-root context: enable pinned pnpm, install with `pnpm install --frozen-lockfile`, build `pnpm --filter web build`, copy only standalone/static/public output, create a non-root user, and run `node apps/web/server.js` (or the emitted standalone server path verified by the build).
- [ ] Build with `APP_ENV=production` and `NEXT_PUBLIC_API_URL=https://api.example.invalid`; inspect as non-root and prove the public URL is the only configuration embedded in the artifact.
- [ ] Run RED/GREEN verification: runtime-config 7-case test, `pnpm lint`, `pnpm check-types`, ordinary build, strict safe build, and Docker image inspection.

**Produces:** a reproducible web artifact suitable for a Railway service whose root build context is the workspace root.

## Task 3: Add/test Railway config-as-code and secret-free contracts (TDD; parallel with Task 2)

**Files:** Create `deploy/railway/api.railway.toml`, `deploy/railway/web.railway.toml`, `deploy/railway/staging.env.example`; Test a new static contract test under `tests/test_railway_contract.py`.

- [ ] Write failing static tests that parse both TOML files and require:
  - API uses the root `Dockerfile`, has `preDeployCommand = "python -m app.core.runtime_check && alembic upgrade head && alembic current"`, `/health`, timeout 300, and no `startCommand`;
  - web uses `apps/web/Dockerfile`, `/`, an explicit health timeout, and no secret variable values;
  - neither file contains `seed`, `alembic` in a start command, `RAILWAY_RUN_UID`, an API token, an `.env` path, or a domain/secret literal;
  - the example inventory has every required backend/web variable but uses `${{simo-postgres-staging.DATABASE_URL}}` only as a reference example and contains no value resembling a credential.
- [ ] Run `pytest tests/test_railway_contract.py -q` and prove RED.
- [ ] Implement the minimal config files. Set API `dockerfilePath = "Dockerfile"`; set web `dockerfilePath = "apps/web/Dockerfile"`; use custom config paths in Railway service settings later. Do not define application secrets in TOML.
- [ ] Add comments/inventory stating exact production variables: `APP_ENV=production`, `PORT=8000` API-only, `DATABASE_URL=${{simo-postgres-staging.DATABASE_URL}}`, non-default sealed JWT/seed values, `SEED_DATA_ENABLED=false`, exact CORS web origin, `READINESS_TIMEOUT_SECONDS=2`, `UPLOAD_DIR=/var/lib/simo-os/uploads`, and frontend `NEXT_PUBLIC_API_URL=https://${{simo-api-staging.RAILWAY_PUBLIC_DOMAIN}}`.
- [ ] Re-run static test, `git diff --check`, and the secret scan from Task 1.

**Produces:** reviewed, secret-free configuration that Railway will consume only after the human gate.

## Task 4: Add monitor and smoke-runner contracts (TDD; parallel with Tasks 2–3)

**Files:** Create `scripts/staging/check-health.ps1`, `scripts/staging/smoke.py`, `.github/workflows/staging-monitor.yml`; Test `tests/test_staging_scripts.py`.

- [ ] Write failing tests that require public origins be HTTPS, reject loopback/path/query/fragment, redact `Authorization`, `token`, `password`, `secret`, and `DATABASE_URL` values from output, and require 22 named smoke gates.
- [ ] Run targeted tests and prove RED.
- [ ] Implement `check-health.ps1` with mandatory `-WebOrigin` and `-ApiOrigin`; use `Invoke-WebRequest` without credentials; require web success, `/health` exact payload, `/ready` exact payload, and valid `X-Request-ID`.
- [ ] Implement `smoke.py` with CLI arguments passed only through environment variables or a local ignored file. It must create two uniquely prefixed synthetic tenants through signup, retain tokens in memory only, emit sanitized status/result/hash evidence, and fail-fast on each named gate in the spec matrix.
- [ ] Add scheduled/manual GitHub workflow with public `STAGING_WEB_ORIGIN` and `STAGING_API_ORIGIN` repository variables; no Railway token or application secret. It invokes only `check-health.ps1` and uploads no response bodies.
- [ ] Re-run targeted script tests and execute `--help`/invalid-origin negative tests. Do not call a real staging origin yet.

**Produces:** portable external health monitor and a secret-safe deployed verification harness.

## Task 5: Documentation and CI integration (sequential after Tasks 2–4)

**Files:** Modify `.github/workflows/ci.yml`, `docs/DECISIONS.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md`, `docs/CHANGELOG.md`; Create `docs/STAGING_RUNBOOK.md`, `docs/SPRINTS/sprint-019.md`.

- [ ] Extend CI with a strict frontend production build using only a synthetic HTTPS API origin and with backend/web Docker build checks. Do not add deploy-on-push or Railway credentials to CI.
- [ ] Write `STAGING_RUNBOOK.md` from the approved sequence: local gate; human gate; provisioning; one-time root volume initialization; variable/release configuration; pre-deploy migration; service startup; monitor; backup schedules/PITR; matched manual recovery window; private Google Drive bundle upload; scratch-only restore; smoke; rollback. Include exact stop conditions, the prohibition on Railway native upload-volume restore, owner gates for PITR/Drive permissions/scratch creation/cleanup, and safe evidence fields.
- [ ] Add ADR-035 documenting Railway unified staging, one API replica, private PostgreSQL, generated domains, pre-deploy migration, and the temporary no-traffic root initialization exception.
- [ ] Update architecture/API/changelog/Sprint record without claiming a deployment before it occurs.
- [ ] Run all documentation link/command checks, `git diff --check`, secret/artifact scan, targeted new tests, full pytest, frontend lint/type/build, and Docker builds.

**Exit:** all repository artifacts are ready; still no Railway resource has been read or changed.

## Task 6: **HUMAN APPROVAL GATE — Railway mutations begin here** (mandatory sequential stop)

**Files:** no repository changes required.

- [ ] Present Task 1–5 results, exact `STAGING_RELEASE_SHA`, changed-file list, Docker image IDs, static-contract tests, and no-secret audit to the accountable operator.
- [ ] Obtain explicit written approval to create/modify Railway resources and acknowledge cost-sensitive actions: Railway paid compute, PostgreSQL volume, upload volume, daily snapshots, PITR storage/egress, logical-backup storage, and temporary duplicate storage during restore drills.
- [ ] Confirm operator has Railway project/account authority and will supply/create secrets directly in Railway, never in chat, shell history, repository files, or logs.
- [ ] If approval is absent, stop. Do not run `railway login`, `railway init`, `railway environment`, `railway service`, `railway variable`, `railway volume`, `railway domain`, backup/PITR, deploy, restart, restore, rollback, or any provider API call.

## Task 7: Railway project, environment, PostgreSQL, domains, and backup provisioning (sequential; external mutation)

**Consumes:** Task 6 approval, `STAGING_RELEASE_SHA`.

- [ ] Create/select project `simo-os`; create/select environment `staging`; record immutable IDs.
- [ ] Create exact services `simo-web-staging`, `simo-api-staging`, and Railway PostgreSQL `simo-postgres-staging`; connect each app service to the selected repository/commit with automatic deploy disabled.
- [ ] Generate Railway public domains for web and API only. Record rendered `https://…up.railway.app` origins; do not configure custom domains or expose PostgreSQL.
- [ ] Configure API root/build configuration to use `/deploy/railway/api.railway.toml`; configure web to use `/deploy/railway/web.railway.toml` with workspace-root build context.
- [ ] Enable PostgreSQL daily volume backups with `railway postgres pitr schedule set --daily --service simo-postgres-staging --environment staging`; read back the schedule and record retention without credentials.
- [ ] Before every risky migration/schema/data operation, create a labeled manual backup with `railway postgres pitr backup create --name ${RECOVERY_RUN_ID}-postgres --service simo-postgres-staging --environment staging`; record only its ID, label, timestamp, and recovery-point relationship.
- [ ] **STOP — owner approval required before PITR enablement.** Present that `railway postgres pitr enable --service simo-postgres-staging --environment staging` can create a `Postgres-PITR` bucket, add archive configuration, and redeploy the active PostgreSQL service. Do not run it until written approval confirms the maintenance window.
- [ ] After approval, enable PITR once; poll read-only PITR status until enabled, bucket wired, archive healthy, and the first base backup is available. Record the observed restore range/start time. A missing first base backup blocks restore work.
- [ ] Enable the daily backup schedule for the existing upload volume through Railway's approved volume-backup interface; read back the schedule. Do not invoke native volume Restore on `simo-uploads-staging`.
- [ ] Verify API `DATABASE_URL` will use private `${{simo-postgres-staging.DATABASE_URL}}`, not a public proxy.

## Task 8: Persistent volume initialization and steady-state API configuration (sequential; external mutation)

- [ ] Attach only `simo-uploads-staging` to `simo-api-staging` at `/var/lib/simo-os/uploads`; set API replicas to exactly one.
- [ ] Perform the one-time empty-volume initializer: temporarily set `RAILWAY_RUN_UID=0` and command `chown 10001:10001 /var/lib/simo-os/uploads && chmod 0750 /var/lib/simo-os/uploads`; deploy with no public traffic/workflow data; require exit 0.
- [ ] Remove the UID override and temporary command before the traffic-serving API deployment. Screenshot/export final service configuration proving neither remains.
- [ ] Set staging-only API variables in Railway: exact matrix from Task 3; generate unique JWT and seed placeholder secrets in Railway; use `SEED_DATA_ENABLED=false`; set CORS to the rendered web origin; set `UPLOAD_DIR` exactly to the mount path.
- [ ] Set web `APP_ENV=production` and `NEXT_PUBLIC_API_URL` to the rendered API origin. Confirm no backend secret is configured on web.
- [ ] Run the API pre-deploy command manually through Railway's release configuration and require sanitized `runtime_check` success, then `alembic upgrade head`, then `alembic current`. Independently run/record `alembic heads`; current must equal the sole head.

## Task 9: Deploy services and establish HTTPS/CORS/health monitoring (sequential; external mutation)

- [ ] Deploy `simo-api-staging` at `STAGING_RELEASE_SHA`; require Railway `/health` deployment health check success. Inspect process: UID 10001, Uvicorn-only command, one replica, no startup migration/seed log.
- [ ] Call public API `/health` then `/ready`; require 200/exact safe bodies/X-Request-ID. Record only request IDs and status.
- [ ] Deploy `simo-web-staging` at the same SHA; require valid HTTPS frontend page and no mixed-content/API-origin mismatch.
- [ ] Run allowed CORS OPTIONS/real-request probes from exact web origin; run denied probes from another HTTPS origin, `null`, and lookalike subdomain. Require only the exact origin is allowed.
- [ ] Set GitHub repository variables to public origins, enable the scheduled/manual monitor, manually dispatch it, and require pass. Confirm it contains no secrets.

## Task 10: Backup/restore drill and upload persistence restart test (sequential; destructive-risk operator control)

**Files:** Create `scripts/recovery/matched_bundle.py`, `scripts/recovery/restore_upload_bundle.py`; Test `tests/test_recovery_tools.py`; Modify `docs/STAGING_RUNBOOK.md`.

**Interfaces:** `matched_bundle.py` accepts `--source-dir`, `--archive-path`, `--manifest-path`, `--database-recovery-point`, and `--created-at`; it writes a portable archive and JSON manifest. `restore_upload_bundle.py` accepts `--archive-path`, `--manifest-path`, and `--scratch-upload-dir`; it verifies the manifest before extraction. Both exit non-zero without printing archive contents, credentials, tokens, or Drive paths beyond the approved folder name.

### Approved temporary remote creator procedure (operator-only)

This procedure is a narrow exception only to the prior prohibition on copying recovery tooling into Railway. It permits a verified, transient dependency closure under `/tmp` for the creator operation; it does not permit persistent deployment, image changes, copies into `/var/lib/simo-os/uploads`, or application-runtime use. Use only Railway project `ff9b6a65-61bb-445c-a698-306f1e2c04b1`, environment `58f1f618-f823-4c02-80b6-b1d6b630bb76`, and API service `375a8ff5-c6bb-4c47-ab96-40b7a9b0d06f`; do not run `railway link`. The upload source is `/var/lib/simo-os/uploads` and is read-only throughout.

1. Determine and record the exact local dependency closure of `matched_bundle.py`, including `recovery_safety.py` and only required imports.
2. Compute and record local SHA-256 digests for every transferred script.
3. Create one unique recovery-run-scoped remote directory below `/tmp` on `simo-api-staging`.
4. Transfer only the recorded dependency closure to that directory using byte-safe transport.
5. Compute remote SHA-256 digests and require exact equality with every recorded local script digest; stop on any mismatch or unexpected dependency.
6. Execute `matched_bundle.py` remotely from that `/tmp` directory against the read-only upload mount, writing the archive and manifest only under that same `/tmp` directory. Retain all creator protections: regular-file pinning, no-follow/identity checks, TOCTOU rejection, normalized-path and Windows-alias collision rejection, and creator/restore path parity.
7. Verify the remote archive and manifest before transfer, recording only safe file counts, sizes, and SHA-256 digests.
8. Transfer the archive and manifest byte-safely to the approved local recovery directory; require exact remote/local size and SHA-256 equality.
9. Independently verify archive/manifest integrity and every manifest hash locally with the approved restore/verification tooling in an isolated local verification directory; do not use an active mount or application path.
10. Create correlation metadata for the matched database/upload recovery pair and verified logical dump, with no credentials, tokens, passwords, database URLs, or authorization material.
11. Run the focused recovery verification required by the approved tooling and record the safe evidence.
12. Delete only the exact proven unique remote `/tmp` recovery directory and its temporary artifacts; never delete source uploads or valid Railway backups.
13. Verify staging `/health` and `/ready` after cleanup. Stop rather than deploying, restarting, rebuilding, or changing configuration if any procedure step requires such a mutation.

- [ ] Write failing tests for a source tree containing nested upload paths. Require deterministic manifest entries `{relative_path, sha256, size_bytes}`, preservation of exact relative paths, supplied database recovery-point ID/timestamp, and an archive digest. Require the creator to reject an archive/manifest path under the repository or an active mount path.
- [ ] Run `pytest tests/test_recovery_tools.py -q` and prove RED before creating recovery tooling.
- [ ] Implement `matched_bundle.py` using only Python standard-library archive, hashing, JSON, and path APIs. Walk source files in sorted relative-path order, reject symlinks and paths escaping the source, write the archive, then write the manifest only after archive creation succeeds. The manifest contains no credentials, bearer values, portal tokens, request bodies, database URLs, or document contents.
- [ ] Write failing restore tests that prove manifest/archive digest mismatch, missing member, extra member, duplicate path, absolute path, `..` traversal, symlink, and an attempt to target `/var/lib/simo-os/uploads` each fail without extraction.
- [ ] Implement `restore_upload_bundle.py`: require a caller-provided scratch directory whose normalized path is not `/var/lib/simo-os/uploads`; verify all manifest digests and archive membership before writing; extract only regular files beneath the empty scratch mount; re-hash every restored file; emit only safe counts/digests/recovery-point ID.
- [ ] Run `pytest tests/test_recovery_tools.py -q`, `pytest tests/test_staging_scripts.py -q`, and `git diff --check`; require GREEN before any recovery maintenance window.
- [ ] **STOP — owner approval required before maintenance-window actions affecting active staging.** Present the exact planned writer-block/maintenance interval, the selected matching database recovery-point timestamp, the synthetic representative document IDs, and the fact that no active volume restore/remount/redeploy will occur.
- [ ] Immediately before creating replacement anchors, obtain fresh read-only PITR evidence (`minRestoreTime`, `maxRestoreTime`, `enabled`, `bucketWired`, `backupSetCount`, `archiverHealthy`) and the identity-aware archive-health checks. Stop if any health predicate fails. Only then generate a new UTC `RECOVERY_RUN_ID`; it must not reuse the immutable historical run ID.
- [ ] In the approved window, create a labeled manual PostgreSQL backup and a manual upload-volume backup as close together as safely possible without application downtime; record safe IDs, external IDs where supplied, exact creation timestamps, and the actual gap. Select and record the authoritative PITR `recovery_target` for this run.
- [ ] If fresh PITR status does not yet contain `recovery_target`, preserve the new anchors and artifact evidence, then perform read-only status probes until `maxRestoreTime` reaches it. Stop if it does not advance; do not use a logical-dump-only restore as a substitute.
- [ ] Create `pg_dump --format=custom --no-owner` through a time-bounded Railway tunnel into an operator workstation temporary directory outside the repository. Generate the portable upload archive and SHA-256 manifest from the active upload volume only through the approved temporary remote creator procedure above; use the new recorded database recovery point and maintenance timestamp. Store all outputs under the new run ID only.
- [ ] Create correlation evidence containing the authoritative PITR target, both safe anchor IDs/timestamps, actual timestamp gap, observed RPO age, and the new artifact hashes. Because no maximum pairing gap is approved, stop for owner acceptance of that exact recorded gap before calling the anchors matched or attempting scratch PITR restore.
- [ ] **STOP — owner approval required before Google Drive access change/upload.** Verify the private folder `SIMO OS Recovery / Staging / Sprint 019` is owner-only by default, contains only explicitly approved administrators, has no public/shared link, and has 30-day retention. Upload only the archive, manifest, matching custom-format dump, and correlation evidence. Do not put Drive credentials in scripts, Railway variables, shell history, Git, CI, or application runtime.
- [ ] Restart only the active API through the approved service restart method without deployment, migration, variable, mount, or volume changes. Require `/health=200`, `/ready=200`, and identical staff and portal download SHA-256 values before the recovery drill proceeds.
- [ ] **STOP — owner approval required before paid scratch resources.** Present `simo-postgres-recovery-${RECOVERY_RUN_ID}`, `simo-api-recovery-${RECOVERY_RUN_ID}`, and `simo-uploads-recovery-${RECOVERY_RUN_ID}` plus their temporary compute/storage impact. Do not create any resource until written approval is renewed.
- [ ] Restore PostgreSQL by Railway PITR only to `simo-postgres-recovery-${RECOVERY_RUN_ID}` at the recorded timestamp. Do not run a volume-backup restore, `alembic upgrade`, `alembic stamp`, seed operation, or write against `simo-postgres-staging`.
- [ ] Create the no-domain scratch recovery service `simo-api-recovery-${RECOVERY_RUN_ID}` and attach only its new volume `simo-uploads-recovery-${RECOVERY_RUN_ID}`. Configure it with a reference to only `simo-postgres-recovery-${RECOVERY_RUN_ID}`, unique recovery-only secrets, `APP_ENV=production`, `SEED_DATA_ENABLED=false`, and the scratch upload mount. It must not reference the staging API's database URL or upload volume, receive a public domain, or accept customer traffic.
- [ ] Initialize ownership only on the empty scratch upload volume under an explicit no-traffic operator command; remove any temporary root override before starting the scratch recovery API as UID 10001. Download the four recovery-bundle artifacts from the approved private Drive folder to an operator-controlled temporary directory, verify their recorded hashes, and use `restore_upload_bundle.py` to restore only to the scratch mount.
- [ ] Restore the logical dump with `pg_restore --no-owner --exit-on-error` into a distinct scratch database on the PITR-restored sibling PostgreSQL service. Do not replace the sibling's recovered database or any active database.
- [ ] Verify read-only on scratch: expected Alembic revision; representative tenant/customer/project/quote/document metadata; Tenant A access; Tenant B denial; active portal scope; one staff and one portal document download; exact SHA-256 bytes against the manifest; and matching database/upload recovery-point IDs. Record elapsed start-to-verification duration as measured RTO and recovery-point age as measured RPO.
- [ ] **STOP — owner approval required before cleanup.** Present the safe evidence bundle and exact scratch service/volume/database names. After written approval, delete only those named scratch resources and local temporary recovery copies; retain the private Google Drive recovery bundle for 30 days unless the owner explicitly extends it. Never delete accepted backups, PITR configuration, active staging resources, or the private recovery folder.

## Task 11: Full 22-gate deployed smoke matrix and tenant-isolation review (sequential)

- [ ] Execute `scripts/staging/smoke.py` against public staging origins with an operator-supplied ephemeral test secret source; redact all process output.
- [ ] Require these 22 named results: **HTTPS reachability** (both frontend and API assertions); liveness; readiness; PostgreSQL; migration; no seeding; signup/login/auth; customer; project; quote/invoice; staff document; restart persistence; portal token; portal documents; portal messaging; token enforcement; tenant isolation; CORS allowed; CORS denied; logs/request IDs; repository secret scan; backup/restore.
- [ ] For the tenant-isolation gate, have Tenant B attempt Tenant A customer/project/quote-invoice/document/message/portal-management IDs and assert no cross-tenant read/write/linkage and prescribed 404/no-disclosure responses.
- [ ] For portal messaging, assert chronological text-only display; one customer message creates exactly one activity and notification; one staff message creates neither.
- [ ] For the backup/restore gate, require: daily PostgreSQL and upload schedules; labeled matched manual recovery points; enabled PITR with a healthy first base backup/archive; the 30-day private Google Drive recovery bundle containing only the portable upload archive, SHA-256 manifest, matching custom-format dump, and correlation evidence; a sibling PITR scratch database; a separate no-domain scratch upload service/volume; manifest checksum verification; staff/portal downloads; tenant/portal scope; and measured RTO/RPO. A native restore of `simo-uploads-staging`, a remount/redeploy of the active API for upload restoration, or an active-source database restore is an automatic failure.
- [ ] Inspect Railway structured logs by safe request ID only. Require absence of bearer values, portal tokens, query strings, body data, raw database URL, JWT/seed secrets, and traceback messages in public responses.
- [ ] Preserve sanitized evidence outside Git. The private Google Drive recovery bundle is not a CI artifact; no raw logs, tokens, dumps, archive contents, or Drive credentials enter CI, the repository, or smoke output.

## Task 12: Rollback/recovery rehearsal and final staging launch verification (sequential)

- [ ] Record last known-good API/web deployment IDs and current sole Alembic revision before each release.
- [ ] Perform a non-destructive rollback rehearsal: verify a previous image is schema-compatible; use Railway rollback only with operator approval; do not alter PostgreSQL/upload volume; rerun `/health`, `/ready`, auth, CORS, document persistence, and frontend checks. If a real rollback is not justified, document the dashboard/CLI procedure and validate it against deployment history without executing it.
- [ ] Confirm failed pre-deploy behavior: a deliberately invalid **non-secret** staging copy/config must be tested only in a disposable non-traffic service/environment; it must block deploy before startup. Never corrupt the accepted staging configuration to prove this.
- [ ] Confirm database downgrade is absent from startup/config/deploy paths. Treat any downgrade as a separately approved operator incident action after backup and compatibility review.
- [ ] Run final integrated gates: targeted Sprint 019 tests; full pytest; Alembic current/heads/check; strict config matrix; frontend lint/type/ordinary+strict builds; both Docker builds; monitor dispatch; `git diff --check`; tracked secret/artifact scan; security/configuration audit; tenant-isolation audit; scope-creep audit.
- [ ] Require final evidence to show: exact SHA, domains, deployment IDs, migration head/current, one API replica/UID 10001/Uvicorn-only, no seed/migration startup, daily backup schedules, manual recovery-point IDs, PITR/archive health, 30-day private-Drive bundle metadata without Drive credentials, scratch-only restore evidence, measured RTO/RPO, 22-gate pass, CORS pass, persistence pass, and rollback target.

## Dependencies and safe parallelism

1. Task 1 is sequential and read-only.
2. Tasks 2, 3, and 4 are safe parallel repository streams after Task 1 because their files do not overlap; each uses TDD.
3. Task 5 integrates those streams and must complete before the human gate.
4. Task 6 is an explicit stop. Tasks 7–12 cannot begin without written approval.
5. Tasks 7–10 are sequential: domains are needed for CORS/API URL; PostgreSQL is needed for migration; volume ownership is needed before production startup; API must be ready before web smoke; restore must follow persistence evidence.
6. During Task 11, independent HTTPS, CORS, and two-tenant probes may run in parallel only with unique synthetic data prefixes; migration, restart persistence, and restore remain exclusive.
7. Task 12 is the final sequential release gate.

## Self-review checklist

- [x] Covers all 17 requested planning areas, including a pre-resource human gate.
- [x] Preserves production mode, strict validation, Uvicorn-only startup, separate Alembic action, no seed, generated domains, single filesystem API instance, and excluded paths.
- [x] Lists exact Railway resources/actions and all application variable/reference contracts without secret values.
- [x] Identifies paid/irreversible-sensitive actions: compute, volumes, snapshots/PITR, logical storage, deployment/restart, restore/cutover, and scratch-resource cleanup.
- [x] Includes local verification, deployment, HTTPS/CORS, monitoring, backup/restore, upload restart, 22-gate smoke, tenant isolation, rollback/recovery, and final launch verification.
- [x] Implements the approved recovery amendment: daily Railway backups/PITR, private 30-day Google Drive matched bundle, recovery-only portable archive/manifest tooling, PITR sibling database, separate no-domain scratch upload service/volume, read-only paired verification, and explicit owner gates before PITR, Drive access, scratch creation, and cleanup.
- [x] Rejects Railway native upload-volume Restore for this drill and contains no path that restores, remounts, replaces, or redeploys active `simo-postgres-staging`, `simo-uploads-staging`, or `simo-api-staging` as part of upload recovery.
- [x] Resolves the approved spec's label/count mismatch: its table has separate frontend/API HTTPS rows plus 21 other rows (23 total) while calling itself a 22-gate matrix. This plan preserves both assertions inside one `HTTPS reachability` gate, yielding the required 22 gates without dropping coverage.
- [x] Contains no deferred placeholders and does not authorize provisioning, deployment, commit, push, custom domains, roadmap changes, or Sprint 020 before approval.
