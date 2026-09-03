# Sprint 031 — Final Stabilisation & Clean Production Launch

**Status:** CLOSED. All workstreams (A–H) complete. Production live on `v1.0.1`.

## 1. Baseline verified (2026-09-03)

- `origin/main` == `ec3e168465cf618757ff068782b58eaf9fa07713` (Sprint 030 merge commit). No unexpected commits landed since Sprint 030 closed.
- `v1.0.0` (annotated tag) dereferences to `ec3e168465cf618757ff068782b58eaf9fa07713` on both local and `origin` — confirmed immutable, untouched.
- Production, verified live: `/health` 200, `/ready` 200 (`{"status":"ready","database":"reachable"}`), `alembic current` == `alembic heads` == `2243d66f83da`.
- Railway `environment-status`: all 3 production services (`simo-api-production` deployment `2ea54cbd-5296-4ba0-bb37-694470722bfd`, `simo-web-production` deployment `2b48a72e-3615-4dba-be53-f67c9e3e8334`, `simo-postgres-production` deployment `e05fdbc1-636d-4b78-ae8b-8da4729ca29f`) online, 1/1 replicas running. `recentFailures: 3` is historical (Phase 21 incident response from Sprint 030), not current.

## 2. Workstream A — Web security hardening: current state

- `apps/web/next.config.ts`: only `output: "standalone"` plus the existing runtime-config resolution call. No `headers()` function.
- No `apps/web/middleware.ts` exists anywhere in the tree.
- Next.js version: `16.2.12` (App Router, `output: "standalone"`).
- Sprint 026's Contract C ("Security response headers") is scoped exclusively to `app/core/middleware.py` / `app/main.py` (the FastAPI backend) — confirmed again this sprint, no change to that reading. `apps/web` was never in scope for it.
- Confirmed live via `curl -sI` against production `/`: no `strict-transport-security`, `x-content-type-options`, `x-frame-options`, or `referrer-policy` headers on the Web response (API has all of these, confirmed the same way in Sprint 030).
- Plan: use Next 16's `headers()` config in `next.config.ts` (not middleware — avoids CSP/nonce complexity and matches "do not introduce a CSP that breaks Next.js"). Add HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and `X-Frame-Options: DENY` (plus the modern `frame-ancestors 'none'` via a minimal `Content-Security-Policy` limited to that one directive — safe, does not touch `script-src`/`style-src`, cannot break hydration or Tailwind). A full script/style CSP is explicitly out of scope this sprint per "do not introduce a CSP that breaks Next.js" and "where compatible" — a frame-ancestors-only CSP is compatible by construction since it constrains nothing the app itself loads.

## 3. Workstream B — Postgres private networking: current state

- Production `simo-postgres-production`: no `networking.privateNetworkEndpoint` alias configured (confirmed via `get-service-config`, Sprint 030). Its actual routable address is its platform-assigned `RAILWAY_PRIVATE_DOMAIN` (`simo-postgres-production.railway.internal`).
- Staging `simo-postgres-staging`: **does** have `networking.privateNetworkEndpoint: "postgres"` configured, so `postgres.railway.internal` resolves there — this is the asymmetry Sprint 030 found.
- Production `simo-api-production`'s `DATABASE_URL` is already corrected (Sprint 030) to reference `${{simo-postgres-production.RAILWAY_PRIVATE_DOMAIN}}` directly, with the `postgresql+psycopg` driver scheme matching `requirements.txt`'s `psycopg[binary]==3.2.13`. This is currently live and verified working (`/ready` 200).
- Staging's `DATABASE_URL` still relies on the `postgres` alias + `postgresql+psycopg` (confirmed working, matches staging's own alias).
- No tool in this session's Railway MCP surface can set/clear a service's `privateNetworkEndpoint` alias directly (confirmed absent from `update-service`'s parameter set). Normalising both environments onto the same *strategy* (a `RAILWAY_PRIVATE_DOMAIN`-based reference, no alias dependency) is achievable purely via `DATABASE_URL` variable changes — no infrastructure/alias change needed on either service. This is the "preferred outcome" the contract describes, and it's achievable without touching the alias at all: point staging's `DATABASE_URL` at `${{simo-postgres-staging.RAILWAY_PRIVATE_DOMAIN}}` too, so neither environment's connectivity depends on a manually-configured alias remaining in place. Production is not touched by this change (already on the target pattern); only staging's `DATABASE_URL` moves to match it, verified there first per the contract's own ordering (staging before production).

## 4. Workstream C — QA data relationship map

Full FK graph relevant to `SIMO-LAUNCH-QA-*` cleanup (`app/database/models.py`):

- `Tenant` — root.
- `User.tenant_id` NOT NULL. Referenced by: `Quote.approved_by_user_id` (nullable), `Project.assigned_user_id` (nullable), `Invitation.invited_by_user_id` (NOT NULL), `PortalLink.created_by_user_id` (NOT NULL), `Document.created_by_user_id` (NOT NULL), `Message.sender_user_id`-equivalent (NOT NULL), `Appointment.created_by_user_id` (NOT NULL), `NotificationRecord.recipient_user_id` (nullable).
- `Customer.tenant_id` nullable (set for our fixtures). Referenced by: `Quote.customer_id`, `Project.customer_id`, `PortalLink.customer_id` (NOT NULL), `Document.customer_id` (NOT NULL), `Message.customer_id` (NOT NULL).
- `Project.customer_id`, `Project.quote_id` (UNIQUE FK → `quotes.id`), `Project.tenant_id`, `Project.assigned_user_id`. Referenced by: `Appointment.project_id` (NOT NULL).
- `Quote.customer_id`, `Quote.tenant_id`, `Quote.approved_by_user_id`. Referenced by: `Project.quote_id`.
- `Material.tenant_id` nullable — no inbound FK from `quotes` (`quotes.material`/`quotes.thickness` are plain `String` columns, confirmed Sprint 030 — a material row is safe to remove independently of any quote).
- `NotificationRecord.source_id` is a bare nullable UUID, **no FK** (Sprint 024 contract, §"Schema") — safe to filter/delete by `source_type`/`source_id` pattern without an integrity constraint concern.
- `ActivityLog.tenant_id` nullable, no other FK dependencies.

**Safe deletion order (leaf → root) for one tenant's fixture data:**
1. `Appointment` (project_id, created_by_user_id)
2. `Document`, `Message` (customer_id, created_by_user_id) — if any exist for the fixture (none were created during Sprint 030's journey; included for completeness/idempotency)
3. `PortalLink` (customer_id, created_by_user_id)
4. `NotificationRecord` (tenant_id, recipient_user_id, source_id — no FK, but tenant-scoped)
5. `ActivityLog` (tenant_id)
6. `Invitation` (tenant_id, invited_by_user_id)
7. `Project` (must precede `Quote` — `Project.quote_id` references `quotes.id`)
8. `Quote`
9. `Customer`
10. `Material` (independent — the one `SIMO-LAUNCH-QA-MATERIAL-001` row)
11. `User` (only after every actor-reference above is cleared)
12. `Tenant` (only after every tenant-scoped row above is cleared)

No `ON DELETE CASCADE` is declared on any of these FKs — an out-of-order delete fails loudly with an `IntegrityError` rather than silently cascading into unrelated data. This is a safety net, not a design to route around: the cleanup mechanism must delete in the order above, inside one transaction, and roll back completely on any unexpected constraint violation rather than catching and continuing.

**Known Sprint 030 fixture identifiers** (exact match targets, no wildcard):
- Tenants: `SIMO-LAUNCH-QA-TENANT-A`, `SIMO-LAUNCH-QA-TENANT-B` (by `tenants.name`)
- Customer: `SIMO-LAUNCH-QA Customer Alpha` (by `customers.name` + `customers.email = customer-alpha@simo-qa.test`)
- Material: `SIMO-LAUNCH-QA-MATERIAL-001` (by `materials.name` + `thickness = "20mm"`)
- Users: `launch-qa-owner-a@simo-qa.test`, `launch-qa-staff-a@simo-qa.test`, `launch-qa-owner-b@simo-qa.test` (by email)
- Everything else (Project, Quote, Appointment, Invitation, PortalLink) is reached transitively via the two QA tenants' `tenant_id`, never by a separate pattern — this is what "exact match only, no wildcard/broad deletion" means in practice: the mechanism's only inputs are the literal tenant names/emails/material name above, and it fails closed (refuses to run) if a lookup returns zero rows (nothing to protect) or if scanning turns up any row whose `tenant_id` isn't one of the two resolved QA tenant IDs.

## 5. Workstream D — follow-up scheduler: current state

- `app/jobs/follow_up.py` confirmed pure CLI, no HTTP boundary, `python -m app.jobs.follow_up`, `--now` explicitly documented as verification-only (never production).
- Sprint 024 explicitly deferred a persistent Railway cron/scheduled-job service (§13/§14 out-of-scope) — this sprint is where that gets resolved, as the roadmap and Sprint 024's own docs anticipated.
- Railway's `update-service` MCP tool exposes a `cronSchedule` parameter directly (`"Cron schedule, e.g. '0 * * * *'. Minimum interval is 5 minutes."`) — Railway supports scheduled/cron services natively; no external scheduler package needed.
- Plan: a new Railway service (no GitHub source connection needed — matches the existing `simo-api-production`/`simo-web-production` pattern, both deployed via `railway up` from a clean `git archive` export, not git-connected), `cronSchedule` set to once daily, `startCommand` limited to exactly `python -m app.jobs.follow_up`, `DATABASE_URL` via the same Railway reference pattern as the API service, no `RAILWAY_RUN_UID` override (runs as the image's default non-root user already), no generated public domain.
- **This is a new, persistently-billed Railway resource.** Per this repository's own established convention (`docs/STAGING_RUNBOOK.md`'s repeated "STOP — owner approval before paid scratch Railway resources" gates for the *staging* recovery drill), creating new production infrastructure is flagged here for explicit confirmation before creation, not created unannounced.

## 6. Workstream E — backup/recovery: precedent

`docs/STAGING_RUNBOOK.md`'s entire "Backup and restore" section is gated behind four separate explicit "STOP — owner approval before..." checkpoints (PITR/backup configuration, Google Drive access, paid scratch Railway resources, any restore action, scratch cleanup) — written for staging, presumably by the project owner in an earlier sprint, as a deliberate safety convention for exactly this class of action. Sprint 031 asks for the *production* equivalent of the same drill. Applying the same convention: the backup itself (a `pg_dump`) is comparatively low-risk and will proceed as part of normal work, but creating a disposable scratch restore-verification environment (a second Postgres service) is flagged for explicit confirmation before creation, matching Workstream D's flag for the same underlying reason (new billed Railway resource) — not because Sprint 031's instructions omitted permission, but because this repository's own established pattern treats it as owner-gated regardless of which sprint is asking.

## 7. Scope discipline

Sprint 031 is final stabilisation/operations only. No new product features, no unrelated refactors. Every workstream maps directly to a Sprint 030 follow-up item or an explicitly-deferred-until-now item from an earlier sprint (Sprint 024's scheduler deferral, Sprint 030's Web-header and DB-networking findings, Sprint 030's retained QA fixture).

## LOCKED CONTRACT

**A — Web security hardening.** `apps/web/next.config.ts` `headers()` (not middleware): HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, and a `frame-ancestors 'none'`-only `Content-Security-Policy` (no `script-src`/`style-src` — out of scope, risk of breaking hydration/Tailwind for no contract-required benefit). TDD: a new `apps/web` test asserting the configured header set first (RED), then the minimal `next.config.ts` change (GREEN). Verified against a real deployed staging Web response before being treated as done, not just the local test suite.

**B — Postgres private-network normalisation.** Production is already on the target pattern (Sprint 030) and is not touched by this workstream. Staging's `DATABASE_URL` moves from the `postgres` alias to `${{simo-postgres-staging.RAILWAY_PRIVATE_DOMAIN}}`, matching production's proven pattern, verified on staging (DNS/TCP/`SELECT 1`/`/ready`/Alembic) before being considered closed. No alias is removed or reconfigured — the goal is that neither environment's connectivity *depends* on one, not that the existing staging alias is deleted.

**C — QA fixture cleanup.** `scripts/production/cleanup_launch_qa.py`, ORM/service-layer only, dry-run default, exact-identifier match only (the literal names/emails in §4 above — no prefix wildcard beyond the single documented `SIMO-LAUNCH-QA-` string match on `tenants.name`, verified against the two known tenant rows before any write), single transaction per run, the deletion order from §4, environment guard (refuses to run with a non-production `DATABASE_URL` host unless `--environment staging` is passed explicitly for the required pre-production test), `--confirm` required for any mutation. Strict TDD against local/staging synthetic fixtures first (dry-run correctness, exact-match-only, unrelated-tenant preservation, correct deletion order, transaction rollback on injected failure, idempotent repeat run, malformed/overbroad-selector rejection, environment guard). Production execution — backup first, then dry-run, then confirmed run — is a separate, explicitly-flagged checkpoint after the mechanism is proven, per this document's own §6 precedent.

**D — Follow-up scheduler.** New Railway service `simo-follow-up-production`: same application source as `simo-api-production` (clean `git archive` export of the accepted Sprint 031 candidate, not git-connected), `cronSchedule` once daily, `startCommand` exactly `python -m app.jobs.follow_up` (no other command), `DATABASE_URL` via the same `RAILWAY_PRIVATE_DOMAIN`-based reference as the API service, no generated public domain, non-root (image default). Timezone will be recorded explicitly in the runbook once the schedule is chosen (UTC, to match every other timestamp already recorded in this project's evidence). Verified on staging first: first eligible run creates the expected notification(s), an immediate second run creates zero duplicates (the existing `dedupe_key` UNIQUE constraint), a fresh/non-due enquiry is skipped. Creating the actual billed Railway service is a separate, explicitly-flagged checkpoint (§6 precedent), not created silently mid-implementation.

**E — Backup/recovery.** A production `pg_dump --format=custom --no-owner` after QA cleanup, timestamp/size/SHA-256 recorded outside any commit, no dump ever committed. A disposable restore-verification environment (a second, scratch Postgres service) is the same class of new-billed-resource action as D — flagged, not created silently.

**F — Full final UAT.** Complete local suite (backend, frontend, Playwright, runtime-config, Docker-contract, migration, new security/cleanup/scheduler tests, `git diff --check`) green before any deploy. Staging acceptance covering the full journey plus every hardening item this sprint adds. Smoke baseline: no worse than 20 PASS / 0 FAIL / 7 blocked-by-design — Sprint 031 is expected to legitimately close out the `migration`, `no_seeding`, `follow_up_notification`, and `repository_secret_scan` blocks it can now close (already independently verified in Sprint 030's execution, formalized here), not to introduce new unexplained failures.

**G — Release process.** `v1.0.0` is never moved. One PR to `main`, explicit merge commit only (no squash/rebase/force). Production is deployed from the exact merged `origin/main` SHA — verified via `containerimage` identity, not inferred. `v1.0.1` is created only after that exact SHA is confirmed live in production, on that exact commit, pushed once, never moved afterward.

**H — Documentation.** `docs/SPRINTS/sprint-031.md` (this file) closed out with full execution evidence; `docs/PRODUCTION_RUNBOOK.md` updated with the Web header set, the DB-networking model, the scheduler, and the backup evidence; `docs/ROADMAP.md` re-baselined per its own maintenance rule (Sprint 030 already closed the v1.0 table but never added a v1.0-plus-stabilisation entry, and this file's own text says "re-baseline this document once Sprint 030 is reached" — that condition is now met); `docs/STAGING_RUNBOOK.md` updated only if the DB-networking change (B) touches anything it documents. No secrets, no resolved `DATABASE_URL`, no PII, no dumps in any of the above.

**Out of scope, unconditionally:** any new product feature, any AI-Workforce/commerce roadmap item, any change to the quote/project/RBAC domain logic beyond what A–H require, squash or rebase of shared history, moving `v1.0.0`, any raw destructive SQL, any silent creation of new billed infrastructure.

## CLOSEOUT — Execution Evidence (2026-09-03)

### Checkpoint 1 — Production QA-fixture cleanup

`scripts/production/cleanup_launch_qa.py` built under strict TDD (15/15 tests green against a real local Postgres, `tests/test_cleanup_launch_qa.py`). A live production dry-run surfaced an unexpected relationship the original design missed — an orphaned anonymous quote (`tenant_id IS NULL`) referencing a QA customer, left behind by Sprint 030's token-expiry bug — caught per this sprint's own STOP-on-unexpected-relationship discipline, fixed under RED→GREEN (`orphan_quote_ids` handling added to `resolve_plan`/`execute_plan`), re-verified, then run with `--confirm` against production. Backup taken first (see Checkpoint 3). Post-cleanup and post-Sprint-031-deploy, production shows zero `SIMO-LAUNCH-QA-*` tenants/materials and zero orphaned anonymous quotes (verified again below, post-deploy).

### Checkpoint 2 — Persistent follow-up scheduler

New Railway service `simo-follow-up-production`: `cronSchedule: "0 3 * * *"` (03:00 UTC daily), `startCommand: python -m app.jobs.follow_up` exactly, no public domain, `DATABASE_URL` via the same `RAILWAY_PRIVATE_DOMAIN`-based reference as `simo-api-production`, non-root (image default). **Live-observed** (not just config-verified): `environment-status` recorded a real successful cron firing at `2026-09-03T03:01:43Z` (`cronJob.lastExecutionStatus: "succeeded"`). A manual `railway ssh ... python -m app.jobs.follow_up` run against the same service post-deploy also completed cleanly: `{"examined": 36, "created": 0, "skipped_existing": 3, "skipped_not_due": 33, "skipped_no_recipient": 0}` — correct dedupe/skip behaviour.

### Checkpoint 3 — Backup/restore verification drill

Production `pg_dump --format=custom --no-owner` (38,850 bytes, SHA-256 `ba3ac07d3ca8557c13d7c28a622935444242c23108d9ca3755f0e2e386718519`), never committed. Restored into a disposable scratch service `simo-postgres-recovery-sprint031` (hit and fixed a `PGDATA`-must-be-under-the-volume-mount-path startup loop on that image along the way). Verification: restore completed with zero `pg_restore` errors; `alembic_version` in the restored DB (`2243d66f83da`) matched the repo's `alembic heads` exactly; row counts and referential-integrity/orphan checks (customer/tenant/quote FK sanity) all clean. Evidence recorded to a local, uncommitted file (SHA-256, counts, checks). Scratch service + volume destroyed immediately after verification; `simo-postgres-production`'s own data/uploads volumes confirmed untouched (`deletedAt: null`) throughout.

### Workstream B — staging DB networking normalised

`simo-api-staging`'s `DATABASE_URL` moved from the `postgres` custom alias to the `RAILWAY_PRIVATE_DOMAIN`-based reference pattern (matching production), referencing `simo-postgres-staging`'s `POSTGRES_USER`/`POSTGRES_PASSWORD`/`RAILWAY_PRIVATE_DOMAIN`/`POSTGRES_DB`. Redeployed; `/ready` confirmed 200 post-change. Production untouched (already correct per Sprint 030).

### Workstream F — full final UAT

- Local backend (real Postgres): 571 passed, 1 skipped, 0 failed.
- Local frontend static contracts (runtime-config, docker-contract, security-headers): 21/21 passed.
- Local Vitest: 69/69 passed (one run showed transient worker-pool timeouts in 3 unrelated files under local contention; a clean isolated re-run confirmed all 29 tests in those files pass — non-regression).
- Local Playwright E2E: 13/13 passed (an earlier concurrent-run artifact produced spurious cross-contamination failures, discarded; the clean single run is authoritative).
- `git diff --check`: clean. Local DB Alembic revision matches repo head (`2243d66f83da`).
- Staging acceptance: all 3 services online/healthy; Web + API security headers live; CORS correctly scoped; staging DB at Alembic head; 27-gate `scripts/staging/smoke.py` run twice — 16/0/11 without quote args, **20 PASS / 0 FAIL / 7 BLOCKED** with `--quote-material "Sprint 019 Smoke Material" --quote-thickness "20mm"`, matching this document's own §F target exactly. All 7 remaining blocked gates are pre-existing/by-design (harness limitations, not failures); `migration`, `follow_up_notification`, `repository_secret_scan`, and `backup_restore` were independently satisfied by direct evidence outside the harness (Alembic query, live `railway ssh` job run, local secret-pattern scan, and Checkpoint 3 respectively).

### Workstream G — exact-SHA release

1. Branch `sprint-031-final-stabilisation-clean-launch` HEAD `9d5214b` — feature-branch CI green (backend/frontend/e2e).
2. PR #13 opened to `main`; diff scope verified (7 files, exactly Workstreams A + C code plus discovery/contract docs — no drift).
3. PR CI green (backend/frontend/e2e, both the push-triggered and PR-triggered runs).
4. Merged with an **explicit merge commit** `74e67a7303de0f16ae10777b61455010e8d6067d` — confirmed two parents (`ec3e168465cf618757ff068782b58eaf9fa07713` = prior `main`/`v1.0.0`, `9d5214beacc0da2a18fe96d76aaac1034d3312e4` = Sprint 031 feature HEAD). No squash, no rebase, no force push.
5. `9d5214b` confirmed an ancestor of `origin/main` post-merge.
6. Post-merge `main` CI green (backend/frontend/e2e).
7. Production API + Web deployed from a clean `git archive` of the exact merge SHA (not `redeploy`, which reuses stale build snapshots for config-sensitive changes — a lesson from Sprint 030). Deployed source verified two ways: (a) zero `diff -rq` between a fresh `git archive` of `74e67a7` and the exact directories uploaded via `railway up`; (b) the new security headers — absent from every prior production Web response — are live on the redeployed service, a content watermark unique to this commit.
8. Production verification, all green: `/health` 200, `/ready` 200 (`database: reachable`), Alembic `2243d66f83da` == heads, Web + API security headers live, CORS correctly scoped (allowed for the real origin, denied for an untrusted one), API PID 1 process confirmed `uid=10001` (non-root — verified via `/proc/1/status`, not just `railway ssh`'s own debug-shell context, which is separately root and not representative of the app process), `SEED_DATA_ENABLED=false`, zero `SIMO-LAUNCH-QA-*` residue, zero orphaned anonymous quotes, follow-up scheduler live-fired successfully (see Checkpoint 2). Production-safe smoke subset (health/ready/homepage/security-headers/auth-rejection/CORS-allowed/CORS-denied/DB-connectivity) all passed; the full data-creating `smoke.py` suite was deliberately **not** run against production, since its synthetic `s019-*`-prefixed fixtures fall outside what the tested exact-match cleanup mechanism can remove — matching Sprint 030's own "non-destructive gates only" precedent for production. `environment-status` showed 0 issues / 0 recent failures across all 4 production services after a ~10-minute stability window; API error rate 0% (the only 4xx's were this verification's own intentional auth-rejection/CORS-denied probes).
9. Only after all of the above: `v1.0.1` created as an annotated tag on `74e67a7303de0f16ae10777b61455010e8d6067d` and pushed once. Verified `v1.0.1` SHA == `origin/main` SHA == the exact deployed/verified commit. `v1.0.0` reconfirmed unmoved (`ec3e168465cf618757ff068782b58eaf9fa07713`).

### BLOCKER / HIGH count at close: **0 / 0**.

### Final status

**SIMO OS FINAL CLEAN PRODUCTION LAUNCH: SUCCESS**

SPRINT 031 CLOSED. SIMO OS CORE DEVELOPMENT SPRINT PROGRAM COMPLETE. PRODUCTION CLEAN. `v1.0.1` LIVE.
