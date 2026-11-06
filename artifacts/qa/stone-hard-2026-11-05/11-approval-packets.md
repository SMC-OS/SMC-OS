# 11 — Approval packets (prepared 2026-11-06; NOTHING EXECUTED)

Each packet is a separate decision. Approving one does not approve another. Production stays HARD NO-GO throughout: no packet touches production data, production deploys or live payments, except A4, which is a read-only query.

Facts below were gathered read-only on 2026-11-06 at about 00:10 UTC through `railway ssh` into `simo-api-staging` (a `READ ONLY` transaction, aggregate output only) and the Railway configuration API.

---

## A1 — Staging backup before the migration

**Operation.** Take Railway manual backups of two staging volumes:
- `simo-postgres-staging` → `postgres-volume` (2,000 MB allocated);
- `simo-api-staging` → its uploads volume.

Record one matched recovery point. Nothing is restored, and no service is restarted or redeployed.

### Current state

| Item | Value |
|---|---|
| PostgreSQL | 18.6, database size 20.6 MB (20,584,127 bytes) |
| Schema | `alembic_version` = `94e5f6a7b8c9` |
| PITR / WAL archiving | **Already active.** `archive_mode=on`, 20,678 segments archived, last archived 2026-11-06 00:09 UTC. **2 archive failures, last on 2026-11-04 10:40 UTC.** These must be explained before PITR is relied on as the recovery path |
| Uploads | 3,766 files, 275,645,492 bytes; the uploads volume is about 454 MB, of which 276 MB is used |
| Workspaces | 146 in total. 141 have only synthetic users (`.invalid`/`example.*`). **5 contain non-synthetic users**, whose data will be inside the backup |
| Documents | 3,766, all in synthetic workspaces |
| Last write | 2026-11-01 07:31 UTC. Staging has been idle for about 5 days; the only scheduled traffic is the GET-only health monitor |

### Writer-block window (proposed)

- **Duration and timing:** 30 minutes, at an owner-chosen time.
- **How writes are blocked:** there is no maintenance mode in the deployed code (the barrier exists only on the unmerged `codex/maintenance-mode-barrier` branch). The block is procedural:
  1. The owner announces a staging freeze: no people, agents or E2E runs against staging.
  2. No deploys or variable changes to staging during the window.
  3. **T0 snapshot**, read-only, outside Git: database `now()`, `pg_current_wal_lsn()`, row counts (tenants, users, documents, projects, requirements, purchase orders, receipts, activity log), `max(timestamp)` of the activity log, and upload file count and bytes.
  4. Take both backups.
  5. **T1 snapshot:** the same queries. **The recovery point is valid only if T0 equals T1, apart from the LSN advancing through archive switches.** Otherwise it is a STOP, and the backups are retaken in a new window.
- **Optional stronger block** (not recommended, and a separate approval): temporarily remove the public domain or stop `simo-api-staging` for the window.

### Recovery-point record (kept outside Git)

- both Railway backup IDs and their creation timestamps;
- the T0 and T1 snapshots;
- `alembic_version` `94e5f6a7b8c9`;
- the PITR target time, equal to T0 if the archiver is healthy;
- SHA-256 of three representative synthetic documents, computed read-only inside the container at T0.

### Synthetic document identifiers

- The three most recent documents from all-synthetic workspaces were selected on 2026-11-06.
- Their IDs are held **outside Git**, in the operator's local scratch file `a1-synthetic-document-ids.txt` (shown to the owner at approval time).
- They are used only to prove restored bytes later (B5), via `sha256` of the stored file.

### Cost

- Railway bills backup storage at the volume rate, **$0.15/GB-month**, for the incremental size only (Railway docs: Backups → Pricing; Railway Metal pricing).
- **Upper bound:** about 0.3 GB of data across both volumes, so **under $0.05/month** while retained.
- **PITR:** already running. Its cost is unchanged by A1.
- **Compute:** none added.

### Limits and risks

- Railway documents that "manual backups are limited to 50% of the volume's total size". The uploads volume is about 61% used (276 of ~454 MB), so **its manual backup may be refused.** If so: STOP, and do not delete files to make room. The fallback is a read-only `tar` + SHA-256 manifest streamed to the operator machine. **The operator workstation currently has about 1.1 GB free on C:** (it ran out of space during this session); free space first.
- Five workspaces with non-synthetic users are inside the backup. It must be stored privately and never used as test fixtures.

### Rollback

- Taking a backup changes no live data.
- If the backup is unwanted, deleting it is its own approval.
- **Restoring from it is not part of A1.** Railway's restore targets the live volume and redeploys, which the runbook forbids for active volumes. Any restore goes to scratch resources under B5.

### Approve as

"A1 approved for window `<date/time UTC>`, both volumes, procedural writer block."

---

## A2 — Staging deploy of the tested SHA and STONE-GATE/DEF-003 browser acceptance

**SHA to deploy.** The QA-branch head that CI has proved green; this packet's commit records it in 03 and 10. Re-check that it contains `bb1c1e9` and `0d745af` (`git merge-base --is-ancestor`) on the day.

**Prerequisite:** A1 complete, with T0 = T1.

### Steps, in order (STOP on any failure)

1. **Pin the SHA.** Create the branch `staging/stone-gate-acceptance` at exactly `<SHA>`. Nothing else ever pushes to it.
2. **API first.**
   - Change `simo-api-staging`'s source branch from `fix/billing-invoice-parent-20261103` to `staging/stone-gate-acceptance` and deploy.
   - The pre-deploy runs `alembic upgrade head`, applying `a5f6b7c8d9e0` (additive: one nullable column plus a partial unique index).
   - **Verify:**
     - Railway shows the deployment at `<SHA>`;
     - `railway ssh --service simo-api-staging --environment staging -- alembic current` prints `a5f6b7c8d9e0 (head)`;
     - `/health` and `/ready` return 200;
     - `GET /api/v1/auth/admission` returns `{"signups_open": true}`;
     - no 5xx in the deploy logs.
   - Health alone is never treated as proof.
3. **Web second.**
   - Change `simo-web-staging`'s source branch from `fix/launch-quote-repeat-save-20261031` to `staging/stone-gate-acceptance` and deploy.
   - **Verify** the deployment SHA and that the sign-in page loads.
4. **Provision two synthetic owners.** These are staging data writes.
   - Run inside the API container:
     `SYNTHETIC_OWNER_PASSWORD=<generated> python scripts/qa/provision_synthetic_owner.py --email stone-gate-<run>@acceptance.invalid --company "Stone-gate acceptance <run>" --confirm-environment staging`
   - Do the same for a second owner (`stone-gate-other-<run>@...`) for d8.
   - The script refuses production, non-`.invalid` addresses and environment mismatches; this was tested locally.
   - It marks the e-mail verified, because `.invalid` cannot receive mail. That is **not** inbox evidence.
5. **Browser acceptance** from the operator machine:
   `STAGING_WEB_URL=<staging web> STAGING_API_URL=<staging api> STAGING_OWNER_EMAIL=… STAGING_OWNER_PASSWORD=… STAGING_OTHER_OWNER_EMAIL=… STAGING_OTHER_OWNER_PASSWORD=… pnpm --filter web exec playwright test -c playwright.staging.config.ts`
   - The configuration refuses any host that is not https, not "staging", or that looks like production.
   - It covers g1–g4 and d1–d9 in 8 tests:
     - g1–g4, d1, d3, d4: UI-linked line, full delivery, then the Template → Fabrication move;
     - the reported symptom: an unlinked UI line repaired in the UI;
     - d2 stone-partial, and d2 short order;
     - d6 over-receipt;
     - d5/d9 retry and ledger;
     - d7 cancellation;
     - d8 the other workspace.
   - Traces and screenshots go to `apps/web/staging-acceptance-results/` (git-ignored) and are kept outside Git.
   - **Dry run:** all 8 passed against a local production build on 2026-11-06 (`evidence/staging-acceptance-dryrun-summary.txt`). That is not staging evidence.
6. **Record.** Only then add staging evidence records (`environment: staging`, `release_sha: <SHA>`, real trace paths kept privately). Regenerate the ledger with `scripts/qa/build_qa_matrix.py --release-sha <SHA>`; that is the only way g1–g5 and d1–d9 can become Verified.

### Safety implications

- Staging schema write (the migration) and staging data writes: 2 workspaces plus about 8 projects, POs and receipts per run, all synthetic.
- While pinned, staging no longer follows the billing-fix or quote-fix branches. Both are already contained in the SHA.
- Automations may run for the synthetic workspaces. Any e-mail goes to `.invalid` addresses and cannot be delivered.
- No production, Stripe or customer impact.

### Rollback

- Switch both services back to their previous source branches and redeploy the previous deployments (IDs are recorded outside Git).
- The migration stays in place. It is additive, and older code ignores the nullable column and index.
- A schema downgrade (`alembic downgrade 94e5f6a7b8c9`) is only done with separate approval, after reviewing it. It would drop any recorded idempotency keys.
- If data must be reverted, restore to scratch under B5. The live volume is never restored.

### Approve as

"A2 approved for SHA `<SHA>`, API then web, two synthetic owners."

---

## A3 — Close new sign-ups on staging (#67 P0)

- **Operation:** set `NEW_ACCOUNT_ADMISSION=closed` on `simo-api-staging` and redeploy. This needs A2 code.
- **Verify:**
  - `GET /api/v1/auth/admission` returns `{"signups_open": false}`;
  - `POST /api/v1/auth/signup` returns 403;
  - an existing synthetic owner can still sign in;
  - first-time checkout returns 403 with no Stripe call.
- **Implications:** staging sign-up is closed, so future staging E2E needs the provisioning script. CI is unaffected, because it uses its own database.
- **Rollback:** set the variable to `open`. No data changes.
- **Production:** a later, separate decision, made only after A3 is verified.

## A4 — Production read-only historical audit

- **Operation:** `railway ssh` into `simo-api-production` and run the same aggregate-only script used on staging (`READ ONLY` transaction, rolled back, counts only). It looks for requirements wrongly `received` and for delivered unlinked lines.
- **Implications:**
  - code runs inside the production container;
  - a few read-only queries add negligible load;
  - no identifiers leave the container;
  - the session appears in Railway's logs.
- **Why it matters:** staging contains no sign of the incident, so production is the remaining place to find it.
- **No data is changed.** If suspects are found, each row needs a human decision and a separate, reviewed correction.

## A5 — Stripe test mode

- **Operation:** authenticate the Stripe connector in **test mode** (or provide a restricted test-mode key for staging use only), so the agent can run trial, checkout with a test card, signed webhooks, invoice failure/recovery, cancel/resume and portal journeys against staging with synthetic workspaces.
- **Implications:** test-mode objects only. Live mode stays untouched; the live reconciliation stays a separate read-only request.

## B1–B6 — Restore drill (runbook STOP gates, each its own approval)

| ID | Operation |
|---|---|
| B1 | Confirm the PITR/archiver health, including the 2 archive failures, and the retention period |
| B2 | Create a logical dump plus upload archive and manifest, and compute four independent SHA-256 values |
| B3 | Private Google Drive upload (owner-only, 30-day retention) |
| B4 | Create paid scratch services (`simo-postgres-recovery-<RUN_ID>`, `simo-api-recovery-<RUN_ID>`, `simo-uploads-recovery-<RUN_ID>`) with no public domain |
| B5 | Restore to scratch only, then verify revision, tenant A/B denial, document bytes against A1's hashes, and RPO/RTO |
| B6 | Clean up the scratch resources |

## Not requested (production promotion)

Merging PR #69 into any Railway-watched branch, deploying production, or opening paid sign-up remains HARD NO-GO. That decision needs every critical and high gate Verified on staging first.
