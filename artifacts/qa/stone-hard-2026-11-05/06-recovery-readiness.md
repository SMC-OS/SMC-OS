# 06 — Recovery readiness and staging approval packet

**Status: BLOCKED. Nothing in this file has been executed against staging or production.** Each step below needs fresh written owner approval under `docs/STAGING_RUNBOOK.md`. A message saying "continue" is not approval for a specific STOP gate.

## A. Staging deployment of the QA branch (needed for STONE-GATE g5 and DEF-003)

### What it would change

| Item | Detail |
|---|---|
| Services | `simo-api-staging` (watches `fix/billing-invoice-parent-20261103` at `bb1c1e9`), then `simo-web-staging` (watches `fix/launch-quote-repeat-save-20261031` at `0d745af`) |
| Code | The QA branch is based on `63e8ac9`. Checked with `git merge-base --is-ancestor`: `bb1c1e9` (staging API), `0d745af` (staging web), `d5f6012` (production) and `daf8759` (marketing) are all ancestors of `63e8ac9`, so no deployed fix would be lost. Re-check on the final QA SHA. |
| Migration | `a5f6b7c8d9e0`: adds nullable `purchase_receipts.idempotency_key` VARCHAR(128) and a partial unique index `uq_purchase_receipts_tenant_idempotency_key (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL` |
| Applied by | The staging API pre-deploy command (`alembic upgrade head`) on the first deploy |
| Schema risk | Additive only. No data rewrite and no NOT NULL. The index build takes a lock on `purchase_receipts` while it runs (not `CONCURRENTLY`), which is seconds on staging-sized data |
| Down migration | Drops the index and the column, losing any idempotency keys recorded. It was tested up, down and up on a disposable PostgreSQL 16.2 |
| Config change | The services' source branch, or a manual deploy of an exact SHA. That is a staging configuration change and needs approval |

### Prerequisites the owner must approve (runbook STOP gates)

1. **STOP: backup before the migration.** Pick one of two routes.
   - The lightweight drill (runbook section "Database backup/restore drill") needs Docker, which this workstation does not have.
   - Otherwise approve a Railway manual backup of `simo-postgres-staging` and the writer-block window.
   - Record the backup ID and timestamp.
2. **Approval to point staging at the QA SHA.** That means the exact SHA after CI is green, deploying API first and then web.
3. **Synthetic tenants only.** Use disposable `@example.invalid` owners; this needs no real inbox. Never use the owner's account, SIMO TEST or a real customer.

### Commands, after approval only

```
# 1. Prove the deployed code contains the current staging fixes
git merge-base --is-ancestor bb1c1e9 <QA_SHA> && git merge-base --is-ancestor 0d745af <QA_SHA>
# 2. Backup (owner-approved route), record the backup id outside Git
# 3. Deploy API at <QA_SHA>; then verify the schema, not only health:
railway ssh --service simo-api-staging --environment staging -- alembic current   # must print a5f6b7c8d9e0 (head)
curl -fsS $STAGING_API_URL/health
# 4. Deploy web at <QA_SHA>; run Playwright journeys G, H and I and the STONE-GATE checklist with synthetic tenants
```

### Rollback

- **Application rollback:** redeploy the previous staging API and web deployments (their IDs are recorded outside Git, per the runbook). The added column and index are ignored by older code, so a schema downgrade is not needed. The runbook requires reviewed reversibility before any downgrade.
- **Schema downgrade:** only with owner authorisation, via `alembic downgrade 94e5f6a7b8c9`.

## Owner sign-off sheet

Tick each line and write the date to approve it. Each line approves only what it says.

- [ ] **A1. Staging backup before the migration:** Railway manual backup of `simo-postgres-staging`. Backup ID recorded outside Git.
- [ ] **A2. Staging deploy of QA SHA `<sha>`:** API first, then web. Migration `a5f6b7c8d9e0` is applied by pre-deploy. Verify `alembic current` and run journeys G/H/I with synthetic tenants.
- [ ] **A3. Staging admission closed:** set `NEW_ACCOUNT_ADMISSION=closed` on `simo-api-staging` and verify 403 on sign-up.
- [ ] **A4. Production read-only aggregate audit:** the same script as staging, `READ ONLY`, prints counts only. It looks for requirements wrongly `received` and for delivered unlinked lines.
- [ ] **A5. Stripe test mode:** connector authentication in test mode, used only with staging and synthetic tenants.
- [ ] **B1–B6. Backup/PITR, Drive, scratch resources, restore and cleanup:** each needs its own approval (section B).

Already verified read-only (2026-11-05): staging `alembic current` = `94e5f6a7b8c9`, which is the new migration's parent, so the migration applies as a single step.

## B. Backup/PITR and scratch restore drill (gate `restore`, journey `recovery-restore`)

| Step | Runbook gate | State |
|---|---|---|
| PITR/WAL archiving | Already active on staging (read-only check 2026-11-06: archive_mode on, last archived 00:09 UTC, 2 archive failures, last 2026-11-04). Health and retention are unverified | B1 in 11-approval-packets.md |
| Matched recovery point before the migration | STOP: owner approval | Packet A1 in 11-approval-packets.md; not executed |
| Upload archive + manifest + dump + correlation, four SHA-256 values | Same | BLOCKED |
| Google Drive access/upload | STOP | BLOCKED |
| Paid scratch services `simo-postgres-recovery-<RUN_ID>`, `simo-api-recovery-<RUN_ID>`, `simo-uploads-recovery-<RUN_ID>` | STOP | BLOCKED |
| Restore to scratch only, verify revision, tenant A/B denial, download bytes, RPO/RTO | STOP | BLOCKED |
| Cleanup of scratch | STOP | BLOCKED |

- Active Railway volumes are never restored, remounted or redeployed.
- No RPO or RTO is claimed.
- Upload ownership: both API services mount a volume at `/var/lib/simo-os/uploads`: production volume `<volume-id>`, staging volume `<volume-id>`. There is a single replica, so uploads are not shared between instances.

## C. Production pre-deploy is data-writing

Production's `preDeployCommand` runs `alembic upgrade head` and `python -m app.catalogue.import_supplier_references --confirm-production` on every deploy. Treat any production deploy as a schema and catalogue write that needs a matched backup first. This session did not deploy anything.
