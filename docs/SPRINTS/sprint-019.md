# Sprint 019 — Railway Unified Staging

Sprint 019 establishes the SIMO OS staging release contract: separate Railway web and API services, private PostgreSQL, persistent filesystem uploads, production runtime validation, health/readiness monitoring, and a non-production smoke workflow.

Recovery is deliberately isolated from application runtime behavior. PostgreSQL uses Railway daily backups, PITR, and matched custom-format logical dumps. Upload recovery uses a portable archive with a SHA-256 manifest and paired database recovery-point identifier. The paired artifacts are retained for 30 days in the private Google Drive folder `SIMO OS Recovery / Staging / Sprint 019`; no public links are permitted. Recovery restores only to explicitly named scratch targets. Railway native upload-volume Restore must never be used against the active API volume.

Completion remains gated on explicit owner approval before PITR enablement, Google Drive access or artifact upload, scratch-resource creation, restore, cleanup, commit, or push.

## Recovery verification evidence (2026-08-24)

Two outstanding verification items were approved and executed against the existing working tree and the existing recovery tooling/documentation, without broadening into Railway, Google Drive, PITR, deployment, migration, production configuration, commit, or push work.

- WSL Python 3.14.4 compile check: GREEN. Every Git-tracked `.py` file compiled cleanly under Python 3.14.4 in WSL against this exact working tree.
- Independent PostgreSQL restore: GREEN. The existing matched custom-format `pg_dump` recovery artifact was restored, using `pg_restore`, into a fresh disposable local target isolated from Railway and production/staging.
- Restored Alembic head: `f81683afc3f4`, matching the previously recorded Sprint 019 preflight head and this repository's current migration chain head.
- Restored schema, data, and foreign-key validation: GREEN. All expected application tables were present with populated (non-empty) data, and every foreign-key constraint restored as valid.
- Production remained untouched throughout both checks; no Railway, Google Drive, PITR, or deployment surface was accessed.
- The verification itself introduced zero repository changes (confirmed by identical `git status --short` before and after).

### Non-blocking follow-ups

- The recovery dump's filename timestamp differs from the dump archive's internal creation timestamp. This has not been reconciled and does not itself indicate a restore defect.
- Upload-bundle / tenant-portal recovery verification was **not exercised**: the corresponding paired upload archive and manifest were unavailable alongside the database dump artifact at verification time. That path of the recovery drill (portable upload archive restore, SHA-256 manifest match, staff/portal download, tenant-isolation checks) remains unverified and must not be treated as passing.
