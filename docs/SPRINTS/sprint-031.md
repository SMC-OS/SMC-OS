# Sprint 031 — Final Stabilisation & Clean Production Launch

**Status:** Discovery in progress.

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

Per the contract about to be locked: Sprint 031 is final stabilisation/operations only. No new product features, no unrelated refactors. Every workstream below maps directly to a Sprint 030 follow-up item or an explicitly-deferred-until-now item from an earlier sprint (Sprint 024's scheduler deferral, Sprint 030's Web-header and DB-networking findings, Sprint 030's retained QA fixture).
