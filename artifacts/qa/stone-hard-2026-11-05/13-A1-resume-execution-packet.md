# 13 — A1 resumed: writer barrier proven locally, alternative capture method, execution packet (8 November 2026)

> **Verdict: A1 BLOCKED (not executed). A2 BLOCKED. Release HARD NO-GO.**
> Nothing was changed on Railway, Stripe or production. No staging backup, dump, archive, barrier or deployment exists yet.
> Everything below marked *local* ran on a throwaway PostgreSQL cluster inside the agent's container and is **not staging evidence**.

## 1. What this session could and could not reach

| Item | Result |
|---|---|
| QA branch fetched and merged into the working branch | Done. Clean merge; every earlier commit, backup record and evidence file is preserved. No force-push. |
| Read documents 11, 12 and `docs/STAGING_RUNBOOK.md` in full | Done. |
| Railway staging (deployment IDs, `alembic current`, health, logs) | **Not verifiable from this session.** The container has no Railway CLI, no Railway credentials and no Railway connector, and the Railway API is unreachable through the egress proxy (HTTP 000). The last known staging revision is `94e5f6a7b8c9` (document 11, read-only, 6 Nov 2026). Treat the current deployment state as **unknown**. |
| Docker | No daemon. Native PostgreSQL 16.15 server binaries were available, so the rehearsal used those. |
| Staging users notified, private storage approved, window recorded | **No.** These are owner actions (section 8). |

Consequence: the staging steps of Phases 1.4, 4 and 5 cannot be executed from here. They are prepared so that an operator with Railway access can run them without further design work.

## 2. What was built

| File | Purpose |
|---|---|
| `scripts/recovery/writer_barrier.py` | Reversible two-layer writer barrier, drain, monitor, probes, release and emergency release |
| `scripts/recovery/content_fingerprint.py` | Content-level T0/T1 fingerprints (database and uploads) and read-only container-side commands |
| `scripts/recovery/a1_capture.py` | A1 capture without Railway manual backups: dump, archive, manifest, correlation record, four hashes, STOP handling |
| `scripts/recovery/pitr_diagnostics.sql` | Read-only PITR/WAL-archiver diagnostics with a pass/blocked decision rule |
| `tests/test_writer_barrier_rehearsal.py` | The rehearsal: 20 tests, 91 recorded checks, skipped automatically where PostgreSQL server binaries, root or `setpriv` are missing |
| `evidence/writer-barrier-rehearsal-local.json` | Recorded results of the rehearsal (synthetic data only, no secrets) |

Existing `matched_bundle.py` and `recovery_safety.py` are reused unchanged for the deterministic archive and per-file SHA-256 manifest.

## 3. Phase 2 — writer barrier: design and local results

**Design.** Two independent layers, neither needing an application deploy (the deployed staging code has no maintenance mode):

1. **Database:** `ALTER DATABASE … SET default_transaction_read_only = on`. Every session opened afterwards, under any role, is read-only. Sessions already open are drained: idle ones are terminated (nothing to lose); active and idle-in-transaction ones are **waited for, never killed**. A timeout leaves the barrier engaged and stops (fail closed). The setting is not part of a `pg_dump`.
2. **Uploads:** write bits removed from the whole uploads tree, with the exact modes recorded outside the tree first. Must run as the file owner (UID 10001); root bypasses permissions, so the probe refuses to run as root.

**Local results** (real API, `APP_ENV=production`, UID 10001; app role tried as both superuser and non-superuser; 91 checks, 0 failed, two consecutive full passes):

| Requirement | Result |
|---|---|
| API mutations blocked | Yes. `POST /customers` returns an error and writes nothing; the database fingerprint is byte-identical afterwards. |
| Direct DB writes blocked | Yes, for both a superuser and a non-superuser role: a no-op write and a real `INSERT` are both rejected. |
| Background jobs cannot modify records | Yes. A job-style writer using the app's own `SessionLocal` is rejected; the three real job entry points ran with no change to the database fingerprint. |
| Uploads and file modification blocked | Yes. A real new-file write and a write-open of an existing file fail; the API upload is rejected and leaves **no file behind**. |
| In-flight operations complete safely | Yes. A transaction mid-flight at engage time was waited for and committed intact. An undrainable one produced `DRAIN_TIMEOUT` (exit 3) and was **not** terminated; it later committed. |
| Reads keep working | Yes. `GET` endpoints, `/health`, `/ready`, document download (identical bytes) all returned 200 under the barrier. |
| Barrier removed safely | Yes. Database, uploads and API service restored **without restarting the API**; database and uploads fingerprints equal their pre-release state. |
| No data lost or corrupted | Under 6 concurrent writers: every acknowledged write was present and no request that started after the barrier left a row. See finding F3 for the one precise caveat. |
| Negative tests | Wrong cluster identity, production environment flag, record file inside the repo, double engage, a pre-existing setting of unknown origin, release with another database's record, probe as root: all refused. |
| Positive controls | Each denial is preceded by the same operation succeeding before the barrier, so the denial is attributable to the barrier. |

### Findings from the rehearsal (read before approving)

| # | Finding | Effect on the plan |
|---|---|---|
| F1 | **A database barrier alone is not enough.** The upload endpoint writes the file first and the database row second. With only the database barrier a rejected upload still leaves an orphan file. | The uploads layer is mandatory, as document 12 said. This is also a real (Low) application defect: any database failure during upload orphans a file. Logged as QA-UPLOAD-ORPHAN; not fixed here because A2 is pinned to `740b6b4`. |
| F2 | **An API restart during the freeze crash-loops.** Production start-up writes a probe file to the uploads directory and exits with "UPLOAD_DIR must be writable in production". | No deploy, variable change or restart of `simo-api-staging` during the window. If one happens: thaw uploads first (STOP condition). |
| F3 | **A request straddling the cutoff can be half-applied.** The customer row committed, the follow-up activity-log write was refused, and the client saw an error (2 of about 100 requests in the recorded load test). The database stays internally consistent. | Engage only when staging is idle (it has had no writes since 1 Nov), notify users, and take T0 only after the drain. The earlier finding that staging has been idle for days makes this unlikely, not impossible. |
| F4 | **The database layer is a default, not a lock.** A session that deliberately issues `SET default_transaction_read_only = off` can still write; PostgreSQL does not let an administrator prevent this for a superuser. The application never does so. | Mitigated by detection, not prevention: the monitor flagged the write within one sample and the content fingerprint differed. Any such event is a STOP. Stronger prevention (revoking write privileges for a non-superuser app role) would be a database privilege change and needs its own reviewed preflight; it is **not** proposed. |
| F5 | After removal, sessions opened under the barrier keep their read-only default. | Release evicts them (they never held a write). Rehearsed; the API recovered without a restart. |
| F6 | Under the barrier, writes return HTTP 500 rather than a clean 503. Login still worked in the rehearsal (it does not write). | Users see errors for writes during the window. The notification must say so. |
| F7 | Staging reports PostgreSQL **18.6**. `pg_dump` older than the server refuses to run. | The tool checks this and stops. The operator needs a `pg_dump` 18 client (runbook step 2 uses a matching-version container). Not rehearsed against PG 18. |
| F8 | The staging app role may be the Railway `postgres` superuser. Unknown. | `db-engage` records `rolsuper` for the admin role; the barrier works for both kinds in the rehearsal, but F4 applies to superusers. |

**Not rehearsed, and therefore not claimed:** PostgreSQL 18 behaviour, Railway's tunnel latency, `railway ssh` stdin and binary-stream behaviour, the container's real UID and umask, and the real 275 MB transfer time. The piped-script mechanism (`python3 - <command> < script`, nothing deployed) was proven locally as UID 10001. Scale was checked separately at staging size: manifest 0.4 s, archive 1.4 s, archive hash 0.3 s on local disk.

## 4. Barrier operational preflight (separate review required before use)

Document 12 forbids changing database privileges, disabling services or deploying a barrier build without a separately reviewed preflight. This is that preflight. **Approving A1 does not approve it; the owner must approve it explicitly.**

| What changes on staging | What does not |
|---|---|
| One row in `pg_db_role_setting` (database-level `default_transaction_read_only = on`) | No application table, schema, role, privilege or data |
| Mode bits of the uploads tree (write bits removed); inode change times move, file content and modification times do not | No service stop, domain removal, redeploy, variable change or volume change |
| Idle database sessions are terminated, so the API pool reconnects (about one retried request) | Nothing is restored to an active volume |

Run order (operator, inside the window):

```text
# DB layer, via the private tunnel, admin DSN in BARRIER_ADMIN_DSN (never on the command line)
python3 writer_barrier.py db-engage --record <private>/a1-barrier.json --confirm-environment staging \
        --expect-system-identifier <recorded in preflight> --drain-timeout 120
# Uploads layer, inside the API container as UID 10001, nothing deployed
railway ssh --service simo-api-staging --environment staging -- python3 - uploads-freeze --dir /var/lib/simo-os/uploads --state /tmp/a1-uploads-state.json < writer_barrier.py
railway ssh … -- python3 - uploads-probe --dir /var/lib/simo-os/uploads < writer_barrier.py
railway ssh … -- cat /tmp/a1-uploads-state.json > <private>/a1-uploads-state.json      # keep a copy off the container
python3 writer_barrier.py db-probe              # BARRIER_APP_DSN = the application's own DSN; no-op writes only on staging
python3 writer_barrier.py db-watch --record … --duration <seconds>   # optional continuous monitor
```

Reversal (also the **emergency unfreeze**, tested):

```text
railway ssh … -- python3 - uploads-thaw --dir /var/lib/simo-os/uploads --state /tmp/a1-uploads-state.json < writer_barrier.py
python3 writer_barrier.py db-release --record <private>/a1-barrier.json --grace 10
# if the record is lost:  db-release --emergency   and   uploads-thaw --emergency (restores the owner write bit)
```

Responsible operator: **owner to name** (not yet recorded). User impact: writes fail for up to 30 minutes; reads work.

## 5. Phase 3 — alternative A1 method (no Railway manual backup)

Railway refuses manual backups beyond 10 per volume and the uploads volume is also above the 50% manual-backup threshold. None of the forbidden actions are needed: no backup is deleted, retention and plan are unchanged, no volume is resized or restored.

`a1_capture.py` performs, in this order, and **stops** on any failure:

1. Preflight: window open, ≤ 30 minutes, ≥ 2 minutes left; cluster system identifier matches; barrier recorded as engaged and drained; no session older than the barrier; **no active or in-transaction session**; uploads frozen (zero writable entries); output directory private (0700), empty, outside the repo and the uploads tree; free disk ≥ 3 × (database + uploads); `pg_dump` major ≥ server major.
2. **T0:** complete database content fingerprint (row-text SHA-256 per table in one `REPEATABLE READ, READ ONLY` snapshot, plus every sequence position and the Alembic revision) and the complete uploads manifest (path, size, SHA-256 of every file). Counts alone are never accepted.
3. `pg_dump --format=custom --no-owner`; `pg_restore --list` must succeed and contain a data entry for every table.
4. Read-only copy of the uploads (`tar` over `railway ssh`), safe extraction, comparison with the T0 manifest (a transfer error stops the run), then the deterministic archive and manifest via `matched_bundle.py`; a three-way check (archive members = bundle manifest = live manifest).
5. **T1:** same fingerprints, compared byte-for-byte with T0, plus a barrier-continuity check (monitor thread and a mandatory final sample).
6. Correlation record binding window, cluster, revision, T0/T1 digests, barrier cutoff, artifact sizes and hashes, provider backup identifiers (none), and an explicit scope limit.
7. **Four hashes** (dump, archive, manifest, correlation record), each computed with Python and with the system `sha256sum` (they must agree), written to an out-of-band hash record outside the bundle; artifacts become read-only; dump and archive are re-read after hashing.

**STOP table:** barrier interrupted or lifted · any T0/T1 difference · unexpected writer or open transaction · window expired · SIGINT/SIGTERM · dump unlistable or missing a table · archive/manifest/live mismatch · transfer mismatch · low disk · `pg_dump` too old. Partial artifacts are **moved to `quarantine-*`, never deleted**, with a `STOP.json`. A1 is never marked PASS after a STOP.

**Local rehearsal result:** the success path ran in 3.2 s; the dump restored into a scratch database with an identical content fingerprint; the archive extracted to a tree identical to the live manifest; capture changed neither database nor uploads. Every STOP above was provoked for real (including a file appearing mid-capture, a corrupted archive, SIGTERM and a write slipping past the barrier) and all quarantined correctly. **This proves the tool, not the staging recovery point.** Restore usability and RPO/RTO on staging stay unproven until B4/B5.

## 6. Phase 3 — PITR and WAL-archive findings

Facts on record (document 11, read-only, 6 Nov 2026): `archive_mode=on`; 20,678 segments archived; last archived 6 Nov 00:09 UTC; **2 archive failures, last 4 Nov 10:40 UTC**; PITR status "restorable up to 5 Nov 07:02 UTC"; latest pgBackRest set 5 Nov 07:00 UTC; daily volume backups at 5 Nov 11:17 (postgres) and 11:14 (uploads).

What can and cannot be concluded without Railway access:

- **The two failures are UNEXPLAINED.** Nothing in the repository or the earlier records explains them. `pg_stat_archiver` counts attempts, and pgBackRest retries, so a failure followed by a successful push of the same segment is normally transient; but that must be shown, not assumed. The decision rule and the exact read-only queries are in `scripts/recovery/pitr_diagnostics.sql`; the pgBackRest checks (`pgbackrest info --output=json`, `pgbackrest check`, and the archive-push log around 4 Nov 10:40 UTC) run on the Postgres service and need the operator.
- **The "delayed restore window" is a discrepancy, not a measurement.** The archiver last pushed at 6 Nov 00:09 UTC, yet the provider reported the restorable window ending 5 Nov 07:02 UTC, about 17 hours earlier. A plausible reading (a hypothesis, unverified) is that the provider derives the window from its last completed pgBackRest refresh rather than from live WAL, so it lags the archiver. If that is right, PITR is better than reported; if the lag instead means newer WAL is not yet part of a verified chain, PITR is worse. Only `pgbackrest info` plus the diagnostics can say which.
- **Volume arithmetic (inference):** 20,678 segments at one per minute is about 14.4 days, which would fit an `archive_timeout` of 60 s and WAL archiving since about 22 October. Unconfirmed; the diagnostics print `archive_timeout`.
- **Existing daily volume backups are not a verified matched recovery point.** They were taken at different times per volume, were never restore-tested, and are not correlated to a database content fingerprint.

**B1 therefore stays BLOCKED.** `archive_mode=on` is not recoverability evidence.

## 7. Phase 4 — disk, storage and the working environment

| Artifact | Size (staging figures) |
|---|---|
| Logical dump (custom format, compressed) | ≤ 21 MB (database 20,584,127 bytes) |
| Uploads archive | about 279 MB (tested at 3,766 files / 275,645,492 bytes → 278,558,720 bytes) |
| Manifest, correlation record, fingerprints | well under 5 MB |
| Peak working space (stream + extracted tree + archive + dump) | about 0.9 GB; the tool requires 3 × (database + uploads) ≈ 0.9 GB free |

- **Not provisioned by me.** The agent's own container has 30 GB free but is not an approved private store, and staging holds 5 workspaces with non-synthetic users. No recovery artifact should ever be written there.
- The operator workstation previously had ~1.1 GB free (ENOSPC earlier). **Free at least 3 GB** before the window.
- **Run the tools in WSL2 on an ext4 path (not `/mnt/c`).** They use POSIX permission bits (0700/0400, UID 10001 checks); on Windows drives those bits are not honoured, and the tool fails closed rather than pretending. The runbook's PowerShell hash snippets remain valid as the *separate* check.
- Private storage: interim, an encrypted local volume owned by the operator. The Google Drive folder is gated by approval **B3**; nothing may be uploaded before the four hashes are approved out-of-band.

## 8. Proposed 30-minute maintenance window (NOT APPROVED — owner to confirm or replace)

| Field | Proposed value |
|---|---|
| Start | **2026-11-10T10:00:00Z** (Tuesday; same as 10:00 GMT in the UK) |
| End | **2026-11-10T10:30:00Z** |
| Environment | Railway `simo-os` / `staging` only. Production, Stripe live, and `main` untouched |
| Operator | *owner to name* |
| Scope | Database `simo-postgres-staging` and uploads volume of `simo-api-staging`; barrier, capture and release only |
| Impact | Writes fail for up to 30 minutes; reads work. No restart, redeploy or domain change |
| Notice | Send at least 24 hours before (before 2026-11-09T10:00:00Z) to the 5 workspaces with non-synthetic users |

Suggested notice: *"GeoCore staging will be read-only on Tuesday 10 November 2026 between 10:00 and 10:30 UTC for a backup. You can view data but cannot save changes. Please do not rely on staging for live work during this time."*

Time budget inside the window (the transfer is the unknown): engage and drain 0–3 min · probes 3–5 · T0 5–7 · dump 7–10 · uploads transfer and archive 10–20 · T1, hashes and verification 20–26 · release and checks 26–30. **Before the window**, time the read-only transfer once (`railway ssh … -- tar -C /var/lib/simo-os/uploads -cf - . | sha256sum`). If it takes more than about 8 minutes, a 30-minute window is too tight and a longer window should be requested rather than rushing the safeguards.

## 9. Execution prerequisites — status

| # | Prerequisite | Status | Owner |
|---|---|---|---|
| 1 | Exact UTC start and end recorded by the owner | ✖ proposed only | Owner |
| 2 | Operator named, with Railway CLI and a `pg_dump` 18 client in WSL2 | ✖ | Owner / operator |
| 3 | Barrier operational preflight (section 4) approved | ✖ | Owner |
| 4 | Writer-exclusion controls verified **on staging** (probes in the window) | ✖ rehearsed locally only | Operator |
| 5 | Approved private backup storage and ≥ 3 GB free | ✖ | Owner / operator |
| 6 | Staging users notified at least 24 hours ahead | ✖ | Owner |
| 7 | No unexpected writers or active transactions (checked by the tool at the start) | ✖ checked at run time | Tool |
| 8 | Unfreeze and recovery procedure tested | ✔ locally (including emergency); ✖ on staging | Operator |
| 9 | Read-only pre-window checks: staging identity, deployed SHAs, `alembic current`, role is superuser or not, `pg_stat_archiver`, transfer timing | ✖ no Railway access here | Operator |
| 10 | PITR/WAL health confirmed (section 6) | ✖ | Operator |

Owner approved the A1 objective earlier; that does not satisfy items 1–6 and was not treated as if it did.

## 10. A2 — remains blocked, prepared as before

Gate unchanged: A1 capture verified, staging access restored, then immutable `740b6b4` (branch `staging/stone-gate-acceptance`), API first, `alembic current` = `a5f6b7c8d9e0`, health/readiness/logs/integrity, then web, two synthetic owners, all **eight** real staging Playwright tests, STONE-GATE g1–g5 and DEF-003 d1–d9. Not started: no staging access and no verified A1. The local dry run (document 11) is not staging evidence and no ledger cell was changed.

### A2 pre-checks that did not need staging (re-confirmed 8 November 2026)

- CI is green on exactly `740b6b4`: push run 42138695942 and pull-request run 42138702465, both completed with conclusion `success` (read from GitHub). The later branch head `bf5d710` is also green (runs 42146974934 and 42146981927).
- `bb1c1e9` and `0d745af` are both ancestors of `740b6b4` (`git merge-base --is-ancestor`).
- Migration `a5f6b7c8d9e0` has `down_revision = 94e5f6a7b8c9`, the last revision known on staging, so it is a single additive step.
- The per-job counts (backend 1807, frontend 424, Playwright 77, audit passed) were taken from document 11 and were not re-read job by job.
