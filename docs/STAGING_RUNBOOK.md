# GeoCore — Railway Staging Runbook

This runbook implements the approved Sprint 019 Railway staging design. It applies only to `simo-os/staging`; it does not authorize production deployment or custom domains.

## Release invariants

- API: `simo-api-staging`, one replica, UID 10001, Dockerfile default Uvicorn command only.
- Web: `simo-web-staging`, built with `APP_ENV=production` and the generated API HTTPS origin.
- Database: `simo-postgres-staging`, private Railway networking only.
- Uploads: `simo-uploads-staging` mounted at `/var/lib/simo-os/uploads`.
- `SEED_DATA_ENABLED=false`; application startup never seeds or migrates.
- The API pre-deploy command is `python -m app.core.runtime_check && alembic upgrade head && alembic current`.

## First deployment

1. Record the release commit and local verification evidence.
2. Create the project/environment/services and generate Railway domains only after the human authorization recorded for the release.
3. Set staging-only secrets in Railway. Required API values are `APP_ENV=production`, private `DATABASE_URL`, unique non-default JWT and seed placeholders, `SEED_DATA_ENABLED=false`, exact HTTPS `CORS_ALLOWED_ORIGINS`, `READINESS_TIMEOUT_SECONDS=2`, and `UPLOAD_DIR=/var/lib/simo-os/uploads`. Set only `APP_ENV=production` and the exact public API HTTPS `NEXT_PUBLIC_API_URL` on web.
4. Attach the empty upload volume. Railway mounts volumes as root: use the one-time no-traffic initializer `chown 10001:10001 /var/lib/simo-os/uploads && chmod 0750 /var/lib/simo-os/uploads` with `RAILWAY_RUN_UID=0`, require success, then remove both overrides before serving traffic.
5. Run/require the API pre-deploy command, then compare `alembic current` with the sole `alembic heads` revision.
6. Deploy API, require Railway `/health`, then public `/health=200` and `/ready=200` with request IDs. Confirm UID 10001, one replica, Uvicorn-only process, and no seed/migration logs.
7. Deploy web and require valid HTTPS, the exact API origin, allowed CORS, and the 22-gate smoke suite.

## Subsequent deployments — explicit migration verification (Sprint 020 finding)

During Sprint 020, deploying commit `3196fa3` to `simo-api-staging` via `railway up` (a CLI-triggered, locally-uploaded deploy, not a git/dashboard-triggered one) did not apply the two pending Alembic revisions. The service's `preDeployCommand` (`python -m app.core.runtime_check && alembic upgrade head && alembic current`) was correctly attached to the deployment — `runtime_check` provably executed (its structured startup line appeared in the deploy log) — but staging's `alembic_version` remained at `f81683afc3f4` while the deployed application code expected `d3e7a9c1f204`. This surfaced only as a runtime `psycopg.errors.UndefinedColumn: column "quote_id" of relation "projects" does not exist` on the first `POST /api/v1/projects` call; **`/health` and `/ready` both stayed green the entire time and did not detect the mismatch** — readiness only proves the database is *reachable*, not that its schema matches the running code.

This is recorded as an **observed CLI-deployment gap for this one release**, not a proven claim that every `railway up` deployment skips migrations — the root cause of why the configured pre-deploy step didn't take effect this time was not conclusively identified (the pre-deploy container's own alembic log output was absent from both the build and deploy log streams, which is itself worth investigating separately). Remediation used the same approved mechanism the runbook already prescribes: `railway ssh` into the running service, then `alembic upgrade head && alembic current`, run directly against staging (no raw SQL, no schema patched by hand, production untouched).

**New rule: after every staging deploy that includes pending Alembic migrations, explicitly verify the actual staging revision before treating the deploy as complete.** Do not infer migration success from `/health` or `/ready` alone — neither checks schema version. The verification command is `railway ssh --service simo-api-staging --environment staging -- alembic current`, and its output must match the local `alembic heads` value for the deployed commit.

**Sprint 021 addendum:** run this same verification even on a deploy that ships *no* migration — confirm `alembic current` still equals `alembic heads` for the deployed commit. `/health`/`/ready` prove reachability, never schema correctness, regardless of whether a migration was expected; a clean "no drift" result is itself the evidence, not an assumption.

## Clean-commit staging deployment (Sprint 021 finding)

`railway up` uploads whatever is on disk in the current directory (filtered by `.gitignore`/`.railwayignore`), not necessarily the exact reviewed commit — and its local indexer can hard-fail outright if the working tree contains a file or directory it cannot read (Sprint 021 hit a pre-existing, ACL-locked, non-gitignored directory left over from an earlier session; even `icacls` on it returned Access Denied). Do not attempt to force through such a failure by taking ownership of or deleting an unfamiliar, inaccessible path.

Instead, deploy from a clean export of the exact reviewed commit:

```
git archive <reviewed-sha> | tar -x -C <clean-target-dir>
cd <clean-target-dir>
railway up --project <project-id> --service <service-name> --environment <environment-id> -c
```

This guarantees the uploaded artifact is byte-for-byte the reviewed commit — no uncommitted changes, no stray untracked debris — and sidesteps local filesystem issues entirely rather than routing around them in place. Repeat once per service (API, web) from the same clean export.

## Browser-session isolation for staging auth verification (Sprint 021 finding)

Manual or agent-driven browser verification against staging must use a fresh, isolated browser context (a new Playwright `BrowserContext`, an incognito window, or equivalent) — never a persistent browser profile that may already hold an authenticated session for a real account. Sprint 021's staging verification found an already-authenticated real-user session in the shared browser profile before the synthetic staging login even began. The synthetic account was used as instructed and the session was cleared (`localStorage.clear()`) immediately afterward, but isolating from the start is the safer default — it removes the risk of ever mixing a synthetic test session with a real one, rather than relying on cleanup after the fact.

## Backup and restore

The target protection design includes daily PostgreSQL backups and PITR, daily upload-volume backups, and a matched recovery point before migration or storage-risk work. A matched point consists of a labeled Railway database backup, a custom-format `pg_dump --format=custom --no-owner`, and a portable upload archive that preserves every relative path below `/var/lib/simo-os/uploads` with a SHA-256 manifest and the paired database recovery-point identifier.

The resulting portable upload archive, manifest, logical database dump, and recovery-point evidence have a 30-day retention target in the private Google Drive folder `SIMO OS Recovery / Staging / Sprint 019`. Access is owner-only by default and limited to explicitly approved administrators; public/shared links are prohibited. Google Drive is recovery storage only and is never mounted or used by application requests.

Railway native volume Restore is not approved for this drill because it targets the source service/volume and can remount or redeploy the live API. The approved target architecture is a PostgreSQL PITR sibling paired with a separately named scratch service and scratch upload volume, followed by revision, metadata/file, staff/portal download, tenant-isolation, checksum, recovery-point, and RTO/RPO verification. This architecture summary does not authorize an operator action; the fail-closed gates below control configuration, creation, access, restoration, and cleanup, and active staging must remain unchanged.

### STOP — owner approval before backup/PITR configuration or creation

Do not proceed without fresh written owner approval for the exact maintenance window. Before approval, do not enable or change PITR, configure daily backups, create a manual database or upload-volume backup, open a Railway tunnel, create `pg_dump`, or create the upload archive/manifest. Present the writer-block interval, database recovery-point timestamp, representative synthetic document IDs, and confirmation that active volumes will not be restored, remounted, or redeployed.

After approval, record safe backup IDs and timestamps, create the custom-format dump and matched upload archive/manifest in an operator-controlled temporary directory outside the repository, and create redacted correlation evidence linking all four artifacts to the same database recovery point. Do not put paths, credentials, tokens, database URLs, customer data, or artifact contents in Git, CI, shell history, or routine logs.

### Independent SHA-256 verification before Google Drive upload

On the approved Windows operator workstation, collect each literal path through hidden console input so it is not placed in PowerShell history or echoed into a transcript. The helper keeps only the returned path string in process memory and immediately clears the temporary unmanaged buffer. Do not paste a path into an assignment command:

```powershell
function Read-HiddenLiteralPath([string]$Prompt) {
    $SecurePath = Read-Host -Prompt $Prompt -AsSecureString
    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePath)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer) }
}
$RecoveryArchive = Read-HiddenLiteralPath 'Recovery archive path'
$RecoveryManifest = Read-HiddenLiteralPath 'Recovery manifest path'
$RecoveryDump = Read-HiddenLiteralPath 'Recovery dump path'
$RecoveryCorrelationEvidence = Read-HiddenLiteralPath 'Recovery correlation-evidence path'
```

Hash each artifact's bytes directly before any upload:

```powershell
Get-FileHash -LiteralPath $RecoveryArchive -Algorithm SHA256 | Select-Object -ExpandProperty Hash
Get-FileHash -LiteralPath $RecoveryManifest -Algorithm SHA256 | Select-Object -ExpandProperty Hash
Get-FileHash -LiteralPath $RecoveryDump -Algorithm SHA256 | Select-Object -ExpandProperty Hash
Get-FileHash -LiteralPath $RecoveryCorrelationEvidence -Algorithm SHA256 | Select-Object -ExpandProperty Hash
```

Have the owner approve and retain those four values as approved out-of-band hash evidence, separate from the recovery bundle and its storage location. The manifest's `archive_sha256` is an internal consistency check only and must not be treated as independent evidence for the archive, manifest, dump, or correlation record. A missing value or mismatch is a STOP condition; do not upload.

### STOP — owner approval before Google Drive access or upload

Do not proceed without fresh written owner approval to access the private Drive folder or upload anything. Before approval, do not open the folder, inspect or change its permissions, create a share link, or upload the archive, manifest, dump, correlation evidence, or out-of-band hashes. Present the four independently computed SHA-256 values and the intended owner-only membership and 30-day retention controls. After approval, confirm there is no public/shared link and upload only the four approved recovery artifacts; never upload credentials or the out-of-band hash evidence with them.

### STOP — owner approval before paid scratch Railway resources

Do not proceed without fresh written owner approval for the exact temporary compute and storage impact. Before approval, do not create the named sibling PostgreSQL service, scratch API service, scratch database, or scratch upload volume. Present `simo-postgres-recovery-${RECOVERY_RUN_ID}`, `simo-api-recovery-${RECOVERY_RUN_ID}`, and `simo-uploads-recovery-${RECOVERY_RUN_ID}` and confirm they will have no public domain, customer traffic, active staging database reference, or active upload mount.

### Independent SHA-256 verification before restore or use

After approved Drive access, download the four artifacts to a new operator-controlled temporary directory outside the repository. Do not reuse the source paths collected before upload. In the same PowerShell session, clear any stale downloaded-path bindings, then collect the new download directory and all four downloaded artifact paths independently through `Read-HiddenLiteralPath` (redefine that helper exactly as shown above first if this is a new session):

```powershell
Remove-Variable -Name DownloadedRecoveryArchive,DownloadedRecoveryManifest,DownloadedRecoveryDump,DownloadedRecoveryCorrelationEvidence,DownloadedRecoveryDirectory -ErrorAction SilentlyContinue
$DownloadedRecoveryDirectory = Read-HiddenLiteralPath 'Fresh downloaded recovery directory'
$DownloadedRecoveryArchive = Read-HiddenLiteralPath 'Downloaded recovery archive path'
$DownloadedRecoveryManifest = Read-HiddenLiteralPath 'Downloaded recovery manifest path'
$DownloadedRecoveryDump = Read-HiddenLiteralPath 'Downloaded recovery dump path'
$DownloadedRecoveryCorrelationEvidence = Read-HiddenLiteralPath 'Downloaded recovery correlation-evidence path'

$DownloadedRecoveryDirectoryFull = [IO.Path]::GetFullPath($DownloadedRecoveryDirectory)
$DownloadedRecoveryPaths = @(
    $DownloadedRecoveryArchive,
    $DownloadedRecoveryManifest,
    $DownloadedRecoveryDump,
    $DownloadedRecoveryCorrelationEvidence
) | ForEach-Object { [IO.Path]::GetFullPath($_) }
$SourceRecoveryPaths = @(
    foreach ($Name in 'RecoveryArchive','RecoveryManifest','RecoveryDump','RecoveryCorrelationEvidence') {
        $Value = Get-Variable -Name $Name -ValueOnly -ErrorAction SilentlyContinue
        if ($Value) { [IO.Path]::GetFullPath($Value) }
    }
)
$SourceRecoveryDirectories = @(
    $SourceRecoveryPaths | ForEach-Object { [IO.Path]::GetDirectoryName($_) } | Sort-Object -Unique
)
if (-not (Test-Path -LiteralPath $DownloadedRecoveryDirectoryFull -PathType Container)) {
    throw 'STOP: downloaded recovery directory is missing.'
}
if (($DownloadedRecoveryPaths | Sort-Object -Unique).Count -ne 4) {
    throw 'STOP: downloaded recovery artifact paths are not distinct.'
}
if ($SourceRecoveryDirectories -contains $DownloadedRecoveryDirectoryFull) {
    throw 'STOP: download directory reuses a source recovery directory.'
}
foreach ($DownloadedPath in $DownloadedRecoveryPaths) {
    if ([IO.Path]::GetDirectoryName($DownloadedPath) -ne $DownloadedRecoveryDirectoryFull) {
        throw 'STOP: downloaded recovery artifact is outside the fresh download directory.'
    }
    if ($SourceRecoveryPaths -contains $DownloadedPath) {
        throw 'STOP: downloaded recovery artifact reuses a source recovery path.'
    }
}
```

Before any PITR, `pg_restore`, extraction, or other use, compute every digest again from only those newly rebound downloaded copies on the approved Windows operator workstation:

```powershell
Get-FileHash -LiteralPath $DownloadedRecoveryArchive -Algorithm SHA256 | Select-Object -ExpandProperty Hash
Get-FileHash -LiteralPath $DownloadedRecoveryManifest -Algorithm SHA256 | Select-Object -ExpandProperty Hash
Get-FileHash -LiteralPath $DownloadedRecoveryDump -Algorithm SHA256 | Select-Object -ExpandProperty Hash
Get-FileHash -LiteralPath $DownloadedRecoveryCorrelationEvidence -Algorithm SHA256 | Select-Object -ExpandProperty Hash
```

Compare all four values byte-for-byte with the approved out-of-band hash evidence recorded before upload. The manifest's `archive_sha256` must not replace this independent comparison. A missing value, mismatch, unexpected extra artifact, or changed correlation record is a STOP condition; quarantine the download and do not restore or use it. Keep local paths and Drive identifiers out of terminal transcripts and retained evidence.

### STOP — owner approval before any restore

Do not proceed without fresh written owner approval for the exact scratch targets and verified artifact hashes. Before approval, do not invoke Railway PITR, `pg_restore`, `restore_upload_bundle.py`, a native volume Restore, a scratch initializer, or any command that writes recovered data. Restore PITR only to the named sibling PostgreSQL service, the logical dump only to its distinct scratch database, and uploads only to the empty scratch volume; never restore to, replace, remount, redeploy, or write against active staging.

After approval and scratch-only restoration, verify read-only evidence: Alembic revision; representative tenant/customer/project/quote/document metadata; Tenant A access and Tenant B denial; portal scope; staff and portal download bytes against the manifest; matching database/upload recovery-point IDs; and measured RTO/RPO. Any mismatch fails the drill and leaves active staging unchanged.

### STOP — owner approval before scratch cleanup

Do not proceed without fresh written owner approval for cleanup after presenting the safe evidence bundle and exact scratch resource names. Before approval, do not delete the scratch service, scratch database, scratch volume, or local temporary recovery copies. After approval, delete only those explicitly named scratch resources and local copies; never delete accepted backups, PITR configuration, active staging resources, out-of-band evidence, or the private recovery folder. Retain the approved Drive bundle for 30 days unless the owner explicitly extends retention.

## Rollback

Application rollback selects a schema-compatible Railway deployment and retains the current database and upload volume. Re-check restored variables, `/health`, `/ready`, migration head/current, authenticated access, CORS, and persisted download before accepting rollback. A database downgrade is never automatic; it requires reviewed reversibility, a current backup, stopped incompatible writers, and explicit operator authorization.

### Proven procedure (Sprint 029)

`simo-api-staging`/`simo-web-staging` are not git-connected — there is no Railway "promote a previous deployment" list to click through. **A rollback here means re-running the normal clean-commit deploy procedure (above) against the previous known-good commit instead of the current one.** This was executed for real in Sprint 029 (RC `v1.0.0-rc.1` / `a8f1277` → previous known-good `737ac10` → back to the RC) and completed in under two minutes end-to-end per service pair:

1. Identify the previous known-good commit from your own deployment records (Railway's deployment history shows *when* each service last deployed, not the source git SHA, since deploys aren't git-linked — the operator/agent that performed each deploy is the source of truth for which SHA it was). Do not guess.
2. `git archive <previous-known-good-sha> | tar -x -C <clean-target-dir>` (never a working tree with local changes).
3. `railway up --project <id> --service <api-service-id> --environment <staging-environment-id> -c` from that export, then the same for the web service.
4. Verify `/health` = 200, `/ready` = 200, and `railway ssh --service simo-api-staging --environment staging -- alembic current` still matches `alembic heads` (a same-schema rollback — no migration between the two commits — is the simplest and safest case; if the previous commit predates a migration the current one requires, stop and treat it as a release BLOCKER rather than deploying it).
5. Run `scripts/staging/smoke.py` against the rolled-back deployment; expect the same passed/failed/blocked totals as the RC's own baseline run (a new failure here means the previous version is not actually compatible with the current data/schema state — a real finding, not something to explain away).
6. To return to the RC: repeat steps 2–5 with the RC's own tagged commit. The system must return to exactly the state it was in before the drill (same deployment health, same schema, same smoke result).

## Database backup/restore drill (lightweight — distinct from the PITR design below)

This is the mechanism Sprint 029 used, and the one to reuse for a routine "does our backup actually work" check. It is **not** the heavier PITR + scratch-Railway-service + Google-Drive drill in the "Backup and restore" section below — that stays gated behind its own STOP-approval checkpoints and untouched by this section. This lightweight drill needs no owner approval beyond the standing authorization to operate on staging, because it never creates paid resources, never leaves staging, and restores only into a disposable local target:

1. Open a private tunnel to staging Postgres — never a new public TCP proxy (`simo-postgres-staging` stays private-networking-only, per the release invariants above): `railway connect simo-postgres-staging --project <id> --environment <staging-environment-id> --tunnel-only --ssh --port <local-port>`. This prints the tunnel's one-time local credentials to its own output — treat that output as sensitive, avoid re-displaying it, and prefer piping it straight into a variable/file rather than a terminal that gets echoed back into a transcript or log a human will read.
2. Because staging Postgres may run a newer major version than the `postgres:16-alpine` pinned for local dev (confirmed: staging ran 18.6 as of Sprint 029, a real version-skew finding, not simulated), run `pg_dump`/`pg_restore` from a disposable container matching the *server's* major version, not the repo's pinned dev version — check with `pg_dump: server version mismatch` if it happens and bump the image tag accordingly.
3. `docker run --rm -e PGPASSWORD=... -v <local-dir>:/backup --add-host=host.docker.internal:host-gateway postgres:<matching-major>-alpine pg_dump --format=custom --no-owner -h host.docker.internal -p <local-port> -U postgres -d railway -f /backup/<name>.dump`. Record the resulting file's size and SHA-256 for the record; never commit the dump itself to git.
4. Start a disposable local Postgres container for the restore target, distinct from the shared local dev database (`simo-os-postgres`) and on a distinct port — this container is created fresh for the drill and removed afterward, never reused.
5. `pg_restore --host=... --port=<disposable-port> --username=... --dbname=... --no-owner --verbose <dump-file>` into it.
6. Validate the restored copy independently of the restore tool's own success message: `SELECT version_num FROM alembic_version` must equal the source's `alembic heads`; `\dt` must list every expected table; representative business-table row counts should be re-queried from the *live source* at drill time and compared for an exact match (staging is a low-write environment during a short drill window, so exact equality is the appropriate bar — a busier source would instead need a chosen, documented tolerance); and a set of `LEFT JOIN ... WHERE <fk-column> IS NOT NULL AND <parent>.id IS NULL` orphan checks across the real foreign-key graph should all return zero, alongside `SELECT conname FROM pg_constraint WHERE contype = 'f' AND NOT convalidated` returning zero rows.
7. Tear down: remove the disposable container, delete the local dump file, close the tunnel. Nothing from this drill persists outside the drill itself.

## Failure and recovery procedures (Sprint 029)

Every command below names `staging` explicitly (environment id or service name); none defaults to or infers an environment. Never substitute a production id/name into any of these commands.

**A. Application deployment failure** (the `railway up -c` command itself errors, or the build fails): the previous deployment stays live automatically — Railway does not cut traffic to a build that never finished. Fix the underlying cause (the build log linked in the CLI's own output names the exact failing step) and redeploy the same commit; no rollback action is needed since nothing was promoted.

**B. Bad application release** (the build/deploy succeeded but the app misbehaves once live — a failed `/health`/`/ready`, a broken workflow, an unexpected error rate): follow the Rollback procedure above to the last commit confirmed good by its own smoke run. Do not attempt a forward "fix" deploy under live incident pressure; roll back first, diagnose calmly, then ship a reviewed fix through the normal branch/PR/CI process.

**C. Migration failure** (`alembic upgrade head` in the pre-deploy command fails or leaves `alembic current` short of `alembic heads`): the deploy's own `preDeployCommand` gate should have already blocked traffic promotion (`deploy/railway/api.railway.toml`) — confirm with `railway ssh --service simo-api-staging --environment staging -- alembic current` vs `alembic heads` from the reviewed commit. Do not deploy application code that expects the failed migration. Fix the migration, verify it locally against a copy of representative data, and redeploy — never hand-patch the schema.

**D. Database loss/corruption incident**: stop further writes if practical, do not attempt an in-place repair, and follow the "Database backup/restore drill" procedure above using the most recent good backup, restoring first into a disposable target to confirm the backup is actually usable before considering any restore into staging itself — and only into staging (never production) with explicit operator authorization for that specific restore.

**E. Rollback to known-good app**: see "Rollback" → "Proven procedure (Sprint 029)" above.

**F. Restoring from backup**: see "Database backup/restore drill" above for the disposable-target drill; see "Backup and restore" below for the heavier PITR/scratch-service drill, which stays gated behind its own owner-approval STOP checkpoints and is not implied or shortcut by anything in this section.

**G. Re-promoting a release candidate**: redeploy the RC's own immutable tag/SHA (never a moved tag) via the same clean-commit procedure, then re-verify `/health`, `/ready`, `alembic current == alembic heads`, and a full smoke run before considering the RC live again — the system must return to exactly the state it was in before any drill.

## Evidence and redaction

Store deployment IDs, safe request IDs, commit SHA, domains, backup IDs, migration revision, health results, and smoke results outside Git. Never retain JWTs, portal tokens, authorization headers, database URLs, secret values, raw dumps, or customer data in repository files, CI artifacts, or routine logs.

## Recovery verification evidence (2026-08-24)

Two verification items approved and executed against the already-existing recovery tooling and an already-created recovery artifact, without opening PITR, Google Drive, or paid scratch Railway resources:

- WSL Python 3.14.4 compile check: GREEN across every Git-tracked `.py` file.
- Independent PostgreSQL restore: GREEN. The existing matched custom-format `pg_dump` artifact was restored with `pg_restore` into a fresh disposable local target, isolated from Railway and from active staging/production.
- Restored `alembic_version`: `f81683afc3f4`, matching the previously recorded Sprint 019 preflight head.
- Restored schema (all expected application tables), data (populated, non-empty), and foreign-key constraints (all valid): GREEN.
- Active staging/production was not accessed or modified during either check; the verification introduced zero repository changes.

Non-blocking follow-ups, recorded for the record and not resolved by this verification:

- The recovery dump's filename timestamp differs from the dump archive's internal creation timestamp; unreconciled.
- The upload-bundle / tenant-portal leg of this recovery drill (portable upload archive restore, SHA-256 manifest match, staff/portal download bytes, tenant-isolation checks) was **not exercised**, because no paired upload archive/manifest was available alongside the database dump artifact at verification time. That path remains unverified and is not represented as passing.
