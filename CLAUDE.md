# GeoCore — Claude Code project memory

Shared portfolio rules (Git, deployment, secrets, evidence order) apply here and
are imported below. This file covers **GeoCore only**. Do not mix in SMC Pro
Studio or MeOra facts.

@AI-PROJECT-CONTEXT.md

Stable sections (1–10) change rarely; record any change to them as a new ADR in
`docs/DECISIONS.md` as well. Volatile facts live only in **CURRENT CHECKPOINT**
and **WHERE TO RESUME** at the bottom; update those after every verified
milestone.

---

## ⚠ CRITICAL DEPLOYMENT SAFETY

**Read this before any Git push, merge or branch operation in this
repository.** This is Railway configuration as verified on 2026-09-26
(read-only `describe-service` for every service). Re-verify it in Railway
before relying on it.

### Which branch deploys what

| Branch | Railway services connected to it | Effect of a push |
|---|---|---|
| `main` | **NONE.** No Railway service in staging or production currently deploys from `main`. | No deployment. |
| `production-release` | `simo-api-production`, `simo-web-production`, `simo-follow-up-production` | **Can trigger an immediate production deployment.** |
| `fix/start-logo-mark` | `simo-marketing-production` (`geocore.one`, `www.geocore.one`) **and** `simo-marketing-staging` | Can redeploy **both** staging and production marketing at once. |
| `claude/geocore-gap-remediation` | `simo-api-staging`, `simo-web-staging` | Can redeploy staging API/web. |

### Rules

- **Treat a push to `production-release` as a production deployment
  action, not a routine Git operation.** Do not push to it without the
  owner's explicit approval for that specific deployment.
- The production API's Railway `preDeployCommand` runs
  `python -m app.core.runtime_check && alembic upgrade head && alembic current`.
  **A deployment of `simo-api-production` migrates the production database.**
- **CI is not confirmed as a deployment gate.** Railway's
  "wait for CI" (`checkSuites`) is `false` on every connected service.
  A failing commit can still deploy.
- **Never reconcile `main` and `production-release` casually.** They have
  diverged (see CURRENT CHECKPOINT). Any reconciliation requires a dedicated,
  reviewed deployment plan approved by the owner.
- Pushing to `fix/start-logo-mark` or `claude/geocore-gap-remediation`
  also deploys. Treat those branches as deployment branches while they
  remain connected.
- `docs/STAGING_RUNBOOK.md` says staging follows `main`. **That is currently
  stale.** Staging API/web follow `claude/geocore-gap-remediation`.

### Extra production database service `Postgres`

**STATUS: UNIDENTIFIED / DO NOT MODIFY**

Known facts (Railway metadata only):

- Railway Postgres 18 (`postgres-ssl:18` template)
- created 2026-09-20
- has its own separate 50 GB volume
- contains data
- has no public endpoint (no domain or TCP proxy)
- its relationship to the production application has **NOT** been
  established

Do not connect to it, modify it, redeploy it, remove it or point anything at
it until the owner has identified it.

---

## 1. Product identity

- **What it is:** GeoCore is a multi-tenant SaaS operating system for
  construction and renovation businesses. It covers enquiries, CRM, quoting,
  approvals, projects, job financials, variations, procurement, calendar and
  tasks, automations, a token-based client portal, and subscription billing.
- **Formerly:** "SIMO OS". Renamed by ADR-037. Some infrastructure identifiers
  deliberately keep the old name: Railway service names `simo-*`, the upload
  mount `/var/lib/simo-os/uploads`, the logger `simo_os`, and the database
  name. **Do not rename them.**
- **Tenancy:** each business is a tenant. Simo Marble & Construction Ltd is
  one tenant, not the platform (ADR-036). Tenant company identity is data,
  never hard-coded.
- **Target users:** owners and staff of trade businesses. Positioning is
  "Stone & Construction" with twelve trades. Stone is one specialism, not the
  shape of the schema (ADR-039, ADR-043).
- **Public surfaces:** marketing site at `geocore.one` (plus `www`), app at
  `app.geocore.one`, API at `api.geocore.one`.
- **Version marker:** the `VERSION` file reads `1.0.0-rc.1` and was not bumped
  after later releases. The latest Git tag is `v1.2.0`. Later production
  releases are untagged; identify them by commit SHA.

## 2. Architecture (verified in the repository)

| Layer | Implementation |
|---|---|
| Backend | FastAPI (Python 3.12) in `app/`. Routes under `/api/v1`, plus unversioned `/`, `/health` (no dependencies) and `/ready` (bounded PostgreSQL check). App factory plus lifespan in `app/main.py`. Settings in `app/core/config.py`. |
| Frontend (app) | Next.js 16 / React 19 App Router in `apps/web`, Tailwind v4, hand-built components. Vitest plus Playwright. Its only backend is the API via `NEXT_PUBLIC_API_URL`. |
| Frontend (marketing) | Separate Next.js app in `apps/marketing` (ADR-038). Indexable. Pricing is server-rendered from `lib/plans.json`, which is generated from `GET /billing/plans` and drift-tested. |
| Database | PostgreSQL 16. SQLAlchemy 2.0 models in `app/database/models.py`. Alembic migrations in `alembic/versions`. |
| Auth | Own JWT auth (`pyjwt`, bcrypt 5), tenant-scoped claims, `token_version` session revocation, roles via `require_role()` (Owner/Staff). Email verification, password reset and signed-in password change (ADR-056). Login and password-change throttling. **Not** Supabase. |
| Client portal | Opaque token links, no customer login: project/quote status, invoice, documents, messaging. |
| File storage | Local disk on a Railway persistent volume (`UPLOAD_DIR`, production mount `/var/lib/simo-os/uploads`). No object storage. |
| Payments | Stripe subscriptions (`app/billing/`): plans, 14-day no-card trial (ADR-054), Checkout, webhook with processed-event dedupe. Price IDs come from `STRIPE_PRICE_*` variables. |
| Email | Resend (`app/communications/`), plus a delivery-status webhook. Needs `RESEND_API_KEY`, `EMAIL_SENDING_DOMAIN` and `FRONTEND_BASE_URL`. |
| AI | "GeoCore AI" (`app/ai/`). Provider set by `AI_PROVIDER`: OpenAI or Gemini, via `OPENAI_*` and `GEMINI_*`. Every reply names the engine that answered (ADR-041). The legacy keyword `brain/` and `assistant/` stubs are mostly empty. |
| PDFs | ReportLab: quotes/invoices, variations, purchase orders. |
| Analytics / error monitoring | **None found.** No Sentry, no PostHog, no APM. Logs are structured JSON with `X-Request-ID`. |
| Hosting | Railway project `simo-os`, with `staging` and `production` environments. Build configs are in `deploy/railway/*.railway.toml` and use Dockerfiles. |

Environment-variable **names** are in `.env.example`, `deploy/railway/staging.env.example`
and `app/core/config.py`. Never write their values here.

## 3. Repository structure

| Path | Contents |
|---|---|
| `app/` | Backend modules. Each has `models.py` / `service.py` / `router.py`: `auth`, `tenants`, `users`, `invitations`, `customers`, `quotes`, `projects`, `tasks`, `calendar`, `appointments`, `activity`, `notifications`, `automations`, `workflows`, `financials`, `variations`, `procurement`, `catalogue`, `materials` (legacy), `trades`, `portal`, `documents`, `messages`, `communications`, `billing`, `demo_requests`, `dashboard`, `ai`, `jobs` (CLI jobs), `core` (config, health, logging, errors, runtime check) |
| `apps/web/` | Authenticated product. Routes: `/`, `/customers`, `/projects` (Project 360), `/quotes` (incl. `/quotes/new/stone`), `/catalogue`, `/calendar`, `/automations`, `/ai`, `/settings`, `/pricing`, `/onboarding`, auth pages, `/portal/[token]`, `/invite/[token]`. E2E specs in `apps/web/e2e`. |
| `apps/marketing/` | Public site: `/`, `/pricing`, `/request-demo`, `/start` (paid-campaign landing) |
| `packages/` | Shared ESLint/TS config, UI stubs |
| `alembic/` | Migrations (single linear head expected) |
| `tests/` | Backend pytest suite |
| `scripts/production/` | Ops scripts (not in the image): `set_tenant_identity.py`, `cleanup_launch_qa.py` |
| `scripts/staging/` | `smoke.py`, `check-health.ps1`, `verify_trial_billing.py` (Stripe TEST mode only) |
| `scripts/recovery/`, `scripts/release/` | Upload-bundle restore tools, RC manifest |
| `deploy/railway/` | Railway build/deploy config per service |
| `docs/` | `SYSTEM_ARCHITECTURE.md`, `DECISIONS.md` (ADR-001…056), `API_SPEC.md`, `DATABASE_SCHEMA.md`, `ROADMAP.md`, `SPRINTS/`, runbooks, `CUSTOMER_PORTAL.md`, `DNS_GEOCORE_ONE.md`, `RELEASES/` |

**Doc freshness warning:** `SYSTEM_ARCHITECTURE.md` says "current as of
Sprint 018". `ROADMAP.md` stops at Sprint 036/037. Sprint files 040–044 say
"not deployed, not merged" in their headers, but all of them are now merged
and in production. Treat `docs/DECISIONS.md` and Git as more current than
those documents.

## 4. Main modules and state

States: IMPLEMENTED · PARTIAL · BLOCKED · PLANNED · DEPRECATED

| Module | State | Notes |
|---|---|---|
| Tenancy, signup, JWT auth, RBAC, invitations, team management | IMPLEMENTED | Email verification and password reset via Resend. Password change (ADR-056). 72-byte bcrypt guard is on `production-release` only; see checkpoint. |
| 2FA, session management UI | PLANNED | No endpoints exist. |
| Customers / CRM, enquiry→customer conversion, demo requests | IMPLEMENTED | Demo leads go to GeoCore's own sales tenant when `PLATFORM_SALES_TENANT_ID` is set (ADR-055). |
| Quotes: universal multi-line, stone quote engine V2, approval, quote→project, PDF invoice | IMPLEMENTED | Catalogue commercial data is snapshotted at creation (ADR-045). |
| Master materials and supplier catalogue | IMPLEMENTED (data PARTIAL) | Global reference data is loaded only by a controlled seed (§13 of the production runbook). Expected 38/47/7/3/0. Whether production has been seeded is **not verified**. |
| Projects / Project 360, adaptive trade workflows | IMPLEMENTED | Workflow engine alongside the legacy pipeline (ADR-042). Real procurement gate on stone fabrication (ADR-052). |
| Tasks, calendar, appointments / site visits | IMPLEMENTED | No external calendar sync. ICS export is PLANNED. |
| Job financials, variations | IMPLEMENTED | Contract value comes from the approved quote plus approved variations (ADR-047/048). |
| Procurement: material requirements, purchase orders, receipts, allocations | IMPLEMENTED | Known limits: partial-receipt cost is not split; no stock ledger (Sprint 044 §6). |
| Automations | IMPLEMENTED | Nine triggers. Actions stay inside the workspace (ADR-040). Scan jobs via `python -m app.jobs.automations`. |
| Notifications, follow-up job, trial reminders | IMPLEMENTED | Daily job `python -m app.jobs.follow_up` runs as the Railway cron service `simo-follow-up-production`. |
| Communications Centre, notification preferences, AI drafting with human gate, pipeline V2 | PARTIAL / UNMERGED | These exist only on the unmerged branch `sprint-039-communications-ai-pipeline` (5 commits, 2026-09-10/11). Relationship to what later merged is **not verified**. |
| Client portal (view, documents, messaging) | IMPLEMENTED | Customer-side approval and uploads are PLANNED (`docs/CUSTOMER_PORTAL.md`). |
| Billing: Stripe subscriptions, 14-day no-card trial | IMPLEMENTED | Stripe TEST-mode staging verification script exists. Whether it has been run successfully is **not verified**. |
| GeoCore AI | IMPLEMENTED (provider-dependent) | Degrades honestly when no provider key is set. |
| AI workforce stubs (`app/assistant/*`, `app/brain/*`) | DEPRECATED / PLANNED | Mostly empty. Do not build on them without a plan. |
| Marketing site, campaign landing `/start` | IMPLEMENTED | |
| Tenant logo on PDFs, tenant statutory details for the production tenant | PLANNED / BLOCKED (owner data) | Never fabricate a company number or VAT number. |

## 5. Database

- **Technology:** PostgreSQL 16 (Railway services `simo-postgres-production`
  and `simo-postgres-staging`, private networking).
- **Migrations:** Alembic, one linear head. Verify with `alembic heads`
  (exactly one) and `alembic current` (equal to it).
  - `alembic check` reports known, documented drift (Sprint 044 §5). Do not
    "fix" that drift incidentally.
- **Tenancy model:** every business table carries `tenant_id`, and every query
  is filtered by it in the service layer (ADR-026/029). There is **no RLS**.
  Isolation is enforced in application code and covered by tests. New queries
  must filter by tenant.
- **Conventions:** additive migrations preferred. Nullable columns rather than
  sentinel values. Index names follow SQLAlchemy's `ix_<table>_<column>`. A
  downgrade that would destroy data must refuse rather than delete.
- **Migrations run automatically on deploy.** The API service's Railway
  `preDeployCommand` is `python -m app.core.runtime_check && alembic upgrade head && alembic current`
  (ADR-035). **Merging or deploying a branch that contains a migration
  therefore migrates that environment's database.**
- **Safety rules:**
  - Never run `alembic downgrade`, `DROP`/`TRUNCATE`, or data scripts against
    staging or production without explicit owner approval, a recorded
    backup, and a written rollback.
  - Production ops scripts run inside `simo-api-production` via `railway ssh`
    (runbook §12). They are not copied into the image.
  - The catalogue seed refuses production unless given `--confirm-production`.
    Run it only under runbook §13.1.
- **Backups:** backup/restore drill documented (runbook §10, staging runbook).
  A manual production backup of 2026-09-23 14:03 UK time is designated for
  the first catalogue seed; **do not delete it.** Staging has a
  `Postgres-PITR` bucket. Production contains an extra service named
  `Postgres`: **UNIDENTIFIED / DO NOT MODIFY** (see CRITICAL DEPLOYMENT
  SAFETY).

## 6. Authentication and authorisation

- Signup creates a tenant plus Owner. JWT carries `tenant_id` and
  `token_version`. Default expiry is 60 minutes, with no refresh token.
- Roles: `OWNER`, `STAFF`. Owner-only: invitations, team management, some
  billing and settings. All authenticated routes are tenant-scoped.
- Email verification is enforced before workspace access. A trial or billing
  gate returns 402 once a trial has ended; auth and billing routes stay
  reachable.
- Password policy is central (`validate_password_strength`), with bcrypt
  72-byte handling. The portal uses hashed opaque tokens and no user row.

## 7. Payments / subscriptions

- Stripe only (no RevenueCat). Plans: Starter, Team, Pro, Business
  (monthly/annual price IDs from env), plus Enterprise via sales.
- The 14-day trial needs no card and creates no Stripe objects until
  Checkout. One trial per workspace, ever.
- The Stripe webhook is the source of truth for subscription state. Events
  are deduped in `processed_stripe_events`. Out-of-order and replayed events
  are tested.
- Staging uses Stripe TEST mode only. `verify_trial_billing.py` refuses
  anything but a `sk_test_` key.
- Whether production Stripe credentials are live, and in which mode, is **not
  verified** in this file. Check Railway variable names (not values) and the
  Stripe dashboard before any billing claim.

## 8. Testing and quality gates

```sh
pytest                                         # backend (needs PostgreSQL + alembic upgrade head)
pnpm lint && pnpm check-types && pnpm build    # all JS workspaces
pnpm --filter web test                         # Vitest component tests
pnpm --filter web test:e2e                     # Playwright (needs running API + DB)
pnpm --filter web test:runtime-config / test:docker-contract / test:security-headers / test:robots / test:sales-cta / test:positioning
pnpm --filter marketing test:indexability / test:logo-quality / test:positioning
alembic heads && alembic current               # single head, matched
```

CI (`.github/workflows/ci.yml`) runs backend, frontend and E2E jobs on every
push and PR. `staging-monitor.yml` checks public staging health every 5
minutes.

**Deployment-ready requires:** all CI jobs green on the exact commit, a single
Alembic head, a successful staging deploy of that commit, and staging
verification (`scripts/staging/smoke.py` plus the feature's own journey).

Last reported counts (from commit messages, not re-run in the 2026-09-26
audit): backend 1330 passed / 3 skipped, web 264, Playwright 65.

## 9. Deployment topology

Railway project `simo-os`. Source settings verified 2026-09-26. Every
Git-connected service has `checkSuites: false` (does not wait for CI).

| Service | Env | Source | Branch | Domain / role |
|---|---|---|---|---|
| `simo-api-production` | production | `SMC-OS/SMC-OS` | `production-release` | `api.geocore.one`. API. Upload volume at `/var/lib/simo-os/uploads`. preDeploy runs migrations. |
| `simo-web-production` | production | `SMC-OS/SMC-OS` | `production-release` | `app.geocore.one` |
| `simo-follow-up-production` | production | `SMC-OS/SMC-OS` | `production-release` | Cron `0 3 * * *`, `python -m app.jobs.follow_up` |
| `simo-marketing-production` | production | `SMC-OS/SMC-OS` | `fix/start-logo-mark` | `geocore.one`, `www.geocore.one` |
| `simo-postgres-production` | production | image `postgres-ssl:18` | — | Production database (50 GB volume) |
| `Postgres` | production | image `postgres-ssl:18` | — | **UNIDENTIFIED / DO NOT MODIFY** |
| `simo-api-staging` | staging | `SMC-OS/SMC-OS` | `claude/geocore-gap-remediation` | Staging API (Railway domain only) |
| `simo-web-staging` | staging | `SMC-OS/SMC-OS` | `claude/geocore-gap-remediation` | Staging app (Railway domain only) |
| `simo-marketing-staging` | staging | `SMC-OS/SMC-OS` | `fix/start-logo-mark` | Staging marketing (Railway domain only) |
| `simo-postgres-staging` | staging | image `postgres-ssl:18` | — | Staging database, WAL archiving to bucket `Postgres-PITR` |

- **No service follows `main`.** The staging runbook's statement that
  staging follows `main` is stale.
- Branch connections can be changed in Railway at any time. **Re-check the
  source branch of every affected service before any push.**
- **Release sequence** (`docs/PRODUCTION_RUNBOOK.md` §2): runtime preflight →
  `alembic upgrade head` (runs in preDeploy) → `alembic current` equals the
  sole head → start → `/health` 200 → `/ready` 200 → authenticated request
  (plus upload smoke after storage changes) → `python -m app.catalogue.reference_data`
  → only then treat as released.
- **Post-deploy verification:** the Railway deployment for the exact commit
  shows `SUCCESS`, `/health`, `/ready`, a real sign-in, and the feature's
  journey. For marketing and domains, follow runbook §11.3.
- **Rollback:** redeploy the previous schema-compatible image (Railway
  rollback). There is no automatic DB downgrade (runbook §5–6).
- **Never say "deployed" because of a push or merge.** Cite the Railway
  deployment ID, commit SHA and verification output.

## 10. Project-specific safety rules

- A push to `production-release` is a production deployment (see CRITICAL
  DEPLOYMENT SAFETY). Never push to it, or to `main`, without explicit
  approval. Never force-push either.
- Do not change Railway variables, services, domains, cron schedules or
  volumes during an audit or docs task.
- Do not run the catalogue seed, QA cleanup, tenant-identity script or any
  production write without approval for that specific run.
- Do not delete or merge the unmerged branches listed in the checkpoint
  without review. They may hold the only copy of work.
- Keep the five states separate (source, Git, database, deployment, live
  production).
- If previously reported work seems missing, search branches, deployments and
  PRs first. A 2026-09-23 audit found that an earlier "remediation"
  description referenced artefacts that never existed in the repository
  (commit `412a675`).

---

## CURRENT CHECKPOINT

**Last verified: 2026-09-26.** Evidence was read-only: the Git remote,
Railway service configuration and deployment records, and Railway metrics.
Live URLs were **not** reachable from the audit sandbox.

### SOURCE CODE STATE
- Latest completed product work in the repository: Plans 01–05 (adaptive
  workflows / Project 360, public homepage + demo + trial funnel, master
  catalogue + stone quote V2, job financials + variations, procurement),
  post-release remediation, catalogue Phase A, billing Phase B (14-day
  no-card trial), signed-in password change, marketing `/start` campaign
  page, and the 72-byte password guard.
- Repository Alembic head: `3c4d5e6f7a8b`. There have been no migrations
  since Plan 05.

### GIT STATE
- `main` @ `8a575c8` (2026-09-24).
- `production-release` @ `1855657` (2026-09-24).
- **The branches have diverged:**
  - `main` contains campaign work not present in `production-release`:
    `05faa21` "feat(marketing): add paid campaign landing page" and
    `8a575c8` "fix(marketing): correct campaign logo proportions".
  - `production-release` contains the password >72-byte hotfix not present
    in `main`: `1855657` "fix(auth): refuse passwords over 72 bytes instead
    of returning 500". It is also on `hotfix/password-72-byte-guard` and
    `claude/geocore-gap-remediation`.
  - Their common base is `75b6a79`.
  - **Reconciliation requires a dedicated, reviewed deployment plan.** Any
    push to `production-release` deploys production (see CRITICAL
    DEPLOYMENT SAFETY).
- Unmerged branches with unique commits. They may hold the only copy of
  that work, so do not delete or merge them without review:
  - `sprint-039-communications-ai-pipeline` (5 commits: Communications
    Centre, notification preferences, AI drafting, pipeline V2)
  - `tools/hotfix72-staging-verifier` (3 commits beyond `1855657`: staging
    verifier for the 72-byte fix)
  - `claude/sprint-036-geocore-product-eoqkqb` (1 docs commit)

### DATABASE STATE
- Applied Alembic revision in staging and production: **not directly
  verified.** It is implied only by a successful preDeploy
  (`alembic upgrade head`) on the `1855657` API deployments. Confirm with
  `alembic current` inside each environment before any schema work.
- Production catalogue reference data (38/47/7/3/0): **not verified.**
- Extra production `Postgres` service: **UNIDENTIFIED / DO NOT MODIFY.**

### DEPLOYMENT STATE (Railway records)

| Service | Deployed commit | Source branch | When (UTC) | Status |
|---|---|---|---|---|
| `simo-api-production` | `1855657` | `production-release` | 2026-09-24 21:40 | SUCCESS |
| `simo-web-production` | `1855657` | `production-release` | 2026-09-24 21:40 | SUCCESS |
| `simo-follow-up-production` | `1855657` | `production-release` | 2026-09-24 21:40 | SUCCESS |
| `simo-marketing-production` | `8a575c8` | `fix/start-logo-mark` | 2026-09-26 03:41 | SUCCESS |
| `simo-api-staging` | `1855657` | `claude/geocore-gap-remediation` | 2026-09-24 21:07 | SUCCESS |
| `simo-web-staging` | `1855657` | `claude/geocore-gap-remediation` | 2026-09-24 21:07 | SUCCESS |
| `simo-marketing-staging` | `8a575c8` | `fix/start-logo-mark` | 2026-09-24 21:40 | SUCCESS |

- `simo-follow-up-production` cron is `0 3 * * *`. The runbook §14 note
  says it was `null` on 2026-09-23. The variable *name* `RESEND_API_KEY`
  exists on the service; `EMAIL_SENDING_DOMAIN` is not among its variable
  names.
- No staged Railway changes were pending in either environment.

### LIVE PRODUCTION STATE
- **Not verified.** Egress to `*.geocore.one` was blocked from the audit
  sandbox. A `SUCCESS` deployment record is not proof of a verified live
  release. Verify `/health`, `/ready`, sign-in and `/pricing` on the live
  domains.

### Known blockers / debt
- Branch divergence (`main` ⟂ `production-release`), and no CI gate on
  deployments.
- The extra production `Postgres` service is unidentified.
- Owner-gated items: production catalogue seed, Stripe live-activation
  status, follow-up job email variables, tenant statutory details, and the
  DNS items in `docs/DNS_GEOCORE_ONE.md`.
- Stale docs: `SYSTEM_ARCHITECTURE.md`, `ROADMAP.md` (stops at 036),
  `STAGING_RUNBOOK.md` (claims staging follows `main`), and the sprint
  040–044 header statuses.
- `VERSION` file not bumped.
- No error monitoring or product analytics.

## WHERE TO RESUME

- **Checkpoint:**
  - production app services = `production-release`@`1855657`
  - production marketing = `8a575c8`
  - `main` = `8a575c8`
  - Alembic head `3c4d5e6f7a8b`
- **Most recently completed:** 72-byte password hotfix deployed to
  production (2026-09-24). Campaign landing page deployed to marketing
  (2026-09-26).
- **Remains:**
  1. Plan the `main` / `production-release` reconciliation. It needs a
     dedicated, reviewed deployment plan approved by the owner; do not do
     it ad hoc.
  2. Owner identifies the extra production `Postgres` service.
  3. Decide the fate of `sprint-039-communications-ai-pipeline` and
     `tools/hotfix72-staging-verifier`.
  4. Owner-approved production catalogue seed (runbook §13.1).
  5. Confirm the follow-up job's email variables.
  6. Refresh the stale docs listed above.
  7. Plan 06 has not been started or defined in the repository.
- **Verify first:**
  - `git fetch`, then compare `origin/main` and `origin/production-release`
    both ways
  - the Railway source branch and latest deployment of every service
  - `alembic current` in each environment
  - live `/health` and `/ready`
- **Safest next action:** documentation-only work on a branch that no
  Railway service follows. Confirm this in Railway first.
- **Do NOT change yet:**
  - `production-release`, `fix/start-logo-mark` and
    `claude/geocore-gap-remediation`: pushing to any of them deploys
  - Railway service sources, variables, cron schedules or volumes
  - production data
  - the `Postgres` service
  - the unmerged branches
  - any Alembic migration
  - infrastructure identifiers named `simo-*`
