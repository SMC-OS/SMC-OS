# SIMO OS — Railway Staging Runbook

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
