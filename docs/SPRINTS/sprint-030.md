# Sprint 030 — Production Launch

## Objective

Sprint 029 proved the release process itself works: an immutable Release
Candidate, a real staging rollback, and a real backup/restore drill all
passed. Sprint 030 is the final core launch sprint — it prepares and
verifies a real production environment end to end, **stopping at an
explicit hard gate before the first production deployment**, per this
sprint's own locked instructions. No new product feature, UI change, or
business-logic change is in scope; every action here is launch
infrastructure, configuration, and verification.

Confirmed scope: Sprint 030 = **Production Launch**, per `docs/ROADMAP.md`'s
locked v1.0 table (`| **030** | **Production Launch** 🚀 |`). Not
reinterpreted as another development sprint.

## Phase 2 — Authoritative release evidence (reconfirmed, not assumed)

- `docs/ROADMAP.md`: Sprint 030 is the terminal v1.0 milestone; no Sprint
  031+ scope is defined until this one closes.
- `docs/SPRINTS/sprint-029.md`: RC `v1.0.0-rc.1` at commit
  `a8f12776c548e91c0558fd43a05b84b7a6c2d1c7`, immutable, tag verified via
  `git rev-list -n 1 v1.0.0-rc.1` to still resolve to that exact SHA — **this
  session re-verified that immediately after creating this branch**, see
  Phase 13 below. Real rollback and backup/restore drills both PASS.
- `docs/SPRINTS/sprint-028.md`: 72/72 acceptance-matrix PASS, 0 open
  BLOCKER/HIGH, 2 MEDIUM + 1 LOW found and fixed.
- `docs/STAGING_RUNBOOK.md`: clean-commit deploy procedure, migration-first
  release sequence, the now-proven rollback/backup/restore procedures
  (Sprint 029), and the heavier PITR drill (still gated, still untouched).
- `docs/SYSTEM_ARCHITECTURE.md` / `docs/PRODUCTION_RUNBOOK.md`: the
  provider-neutral release sequence (`runtime_check` → `alembic upgrade
  head` → verify `current == heads` → start Uvicorn → `/health` → `/ready`)
  already fully specifies the production release gate this sprint reuses
  as-is — nothing new to invent here, only to execute for real.

## Phase 3 — Staging credential rotation (executed and verified)

Sprint 029 recorded an incidental exposure: `railway connect
--tunnel-only`'s one-time local tunnel credentials for
`simo-postgres-staging` appeared in that session's own tool output.

**Determination: the credential was still live, not ephemeral.** Compared
directly against the current `POSTGRES_PASSWORD` Railway variable — they
matched exactly. Rotation was required and performed:

1. Opened a fresh private SSH tunnel (`railway connect simo-postgres-staging
   --tunnel-only --ssh`) to `simo-postgres-staging`.
2. **Finding, recorded for the runbook:** this tunnel path does not actually
   enforce the Postgres password at all — a deliberately wrong password
   connected successfully. The tunnel's real security boundary is the
   SSH-key-authenticated Railway session, not the printed password; the
   password shown is cosmetic/connection-string compatibility only. This
   materially reduces the real exploitability of the original exposure
   (an external party without SSH access to this Railway project could not
   have used just that string to connect), but rotation was still completed
   as the correct precaution, since the same role password is also the real
   credential used for the actual internal-network connection
   `simo-api-staging` depends on.
3. Ran `ALTER ROLE postgres WITH PASSWORD '<new>'` against the real
   database (verified: the new password authenticated immediately after;
   this is the path that matters).
4. Updated `POSTGRES_PASSWORD`, `PGPASSWORD`, and `DATABASE_URL` on
   `simo-postgres-staging` to the new value (`railway variable set --stdin`,
   never on the command line, never printed).
5. Confirmed `simo-api-staging`'s own resolved `DATABASE_URL` **is a live
   Railway reference** — its SHA-256 changed automatically once the source
   variable changed (compared by hash only, values never printed either
   side).
6. Redeployed `simo-api-staging` (`redeploy`, same existing build, no
   rebuild) so the running container picked up the new value at process
   start (env vars are not hot-reloaded into an already-running container).
7. Verified: `/health` 200, `/ready` 200, `railway ssh ... alembic current`
   still `2243d66f83da (head)` (matches heads), and the real follow-up CLI
   (`python -m app.jobs.follow_up`) still reaches the database and returns
   real results (`"examined": 32`) — all against the **new** credential,
   confirmed by the redeploy's own pre-deploy gate re-running
   `runtime_check && alembic upgrade head && alembic current` successfully
   against it.
8. `git grep` across the full tracked repository for both the old and the
   new password string: **zero matches**, either side.
9. Tunnel closed, all local temp files holding either credential deleted.

**Second incidental exposure, disclosed:** while diagnosing why the tunnel
accepted a wrong password, this session displayed the tunnel's log file a
second time via a filter that excluded the `Password:` line but not the
`URL:` line (which embeds the same value) — the **same already-flagged**
password was shown again, not a new one, and it was rotated within the same
session shortly after. No other credential was exposed. This finding is
folded into the Sprint 030 runbook update (Phase 35): future tunnel-log
handling should treat the entire block as sensitive, not just the line
literally labeled `Password:`.

**Rotation is complete and verified.** This is the last outstanding item
carried over from Sprint 029.

## Phase 5 — Production Railway environment (reverified, not assumed)

`railway list-services` on project `simo-os`, re-run fresh in this session:
the `production` environment (`c5f88dea-8c24-4770-b289-24529b775acb`)
**still has zero deployed services** — no API, no web, no database, no
volumes, no domains. Sprint 029's finding stands, reverified rather than
assumed stale. Nothing has been deployed to it; nothing is deployed to it by
this document.

## Phase 6 — Locked production topology

Staging is the proven reference (`simo-api-staging`, `simo-web-staging`,
`simo-postgres-staging`, all Railway-managed). Production mirrors the same
shape and naming convention, with **no synthetic/test-only services**:

| Service | Source | Notes |
|---|---|---|
| `simo-api-production` | Dockerfile (repo root), same image build as staging | `deploy/railway/api.railway.toml`'s config reused verbatim for the API service, pointed at the new production service |
| `simo-web-production` | `apps/web/Dockerfile`, same build as staging | `deploy/railway/web.railway.toml` reused verbatim |
| `simo-postgres-production` | Railway's standard Postgres template (same as staging's `simo-postgres-staging`) | **Empty at creation** — no data import from staging, no seed rows beyond what `SEED_DATA_ENABLED=false` startup itself creates (none) |

Pre-deploy command (unchanged from staging, already generic to environment):
`python -m app.core.runtime_check && alembic upgrade head && alembic
current`. Health check path `/health`. Build: Railpack/Dockerfile, identical
to staging. Internal networking: private only, matching
`simo-postgres-staging`'s existing convention — no public database proxy in
production, ever. Public domains: Railway-generated
`*.up.railway.app` domains for launch (see Phase 9) — no custom DNS is
configured yet in this repository/account, so none is claimed as live.

No smoke-test fixtures, no staging seed data, no staging-only credentials,
and no test accounts are part of this topology — production starts from
nothing but its own schema.

## Phase 7 — Production database plan

- PostgreSQL version: match staging's actual running version, **18.x**
  (Sprint 029 discovered staging runs 18.6, not the `postgres:16-alpine`
  pinned for local dev — production should not silently inherit the
  16-vs-18 mismatch; use Railway's current default Postgres template, which
  is 18.x, for parity with staging rather than the older local-dev pin).
- Required extensions: none beyond what a stock Railway Postgres template
  provisions — the application uses SQLAlchemy/Alembic-managed tables only,
  no `CREATE EXTENSION` anywhere in the migration history (verified:
  `grep -r "CREATE EXTENSION" alembic/` — no matches).
- Initial schema process: **empty PostgreSQL → `alembic upgrade head` (via
  the standard pre-deploy command, not a manual step) → done.** No manual
  SQL, no data import, no synthetic business records. The single Alembic
  head at launch time must be `2243d66f83da` unless Sprint 030 itself adds
  a migration (it does not, per this contract).
- Backup mechanism: the same lightweight `pg_dump`/`pg_restore` drill
  proven in Sprint 029, first exercised for real against production data
  once real workspace data exists (Phase 23) — establishing the baseline,
  not a one-time novelty.
- Restore procedure: identical to the Sprint 029 drill, restoring only into
  a disposable isolated target — **never back into production**, even
  during a drill.
- Retention: no automated retention/rotation schedule exists yet in this
  repository for either staging or production — this is an accepted
  Sprint 030 launch-time limitation (documented in Phase 34's known
  limitations), not silently invented here.

## Phase 8 — Production environment-variable inventory (names/status only — no values)

| Variable | Required | Category | Production-safe source |
|---|---|---|---|
| `APP_ENV` | yes | runtime mode | literal `production` |
| `DATABASE_URL` | yes | database | Railway reference `${{simo-postgres-production.DATABASE_URL}}` — never a copied static string |
| `JWT_SECRET_KEY` | yes | auth secret | new Railway-sealed secret, distinct from staging's |
| `JWT_ALGORITHM` | yes | auth config | `HS256` (unchanged default, safe) |
| `JWT_EXPIRE_MINUTES` | yes | auth config | `60` (unchanged default, safe) |
| `SEED_ADMIN_EMAIL` | yes (validated even though seeding is disabled) | secret-adjacent | new Railway-sealed value, distinct from staging's and from the code default `owner@simo-os.local` |
| `SEED_ADMIN_PASSWORD` | yes (same reason) | secret | new Railway-sealed value, ≥12 chars, distinct from staging's and from the code default |
| `SEED_DATA_ENABLED` | yes | **hard requirement** | `false` |
| `CORS_ALLOWED_ORIGINS` | yes | security | the production web origin's exact HTTPS domain, via Railway reference once the web domain is generated — never staging's domain, never a wildcard |
| `READINESS_TIMEOUT_SECONDS` | no (has a safe default) | runtime config | `2` (unchanged default) |
| `UPLOAD_DIR` | yes | storage | `/var/lib/simo-os/uploads`, backed by a real production volume (not yet created — Phase 22) |
| `PORT` | yes | runtime | `8000` (unchanged default) |
| `OPENAI_API_KEY` | **no** | optional | never a startup dependency (`app/core/config.py`'s own comment: "Never required, never a startup dependency"); omit entirely for launch — AI draft remains deferred per roadmap |
| `NEXT_PUBLIC_API_URL` (web) | yes | frontend runtime | the production API's exact HTTPS domain, via Railway reference — **never staging's API URL** |
| `APP_ENV` (web) | yes | frontend build | literal `production` |

Hard requirements confirmed present in this plan: **`SEED_DATA_ENABLED=false`**
and no debug flag exists in this codebase to begin with (`app_env` is the
only mode switch; there is no separate `DEBUG` variable) — `APP_ENV=production`
itself is what disables the development conveniences (verbose errors, loopback
CORS fallback, etc.), enforced by `app/core/config.py`'s existing fail-closed
Pydantic validators (`tests/test_runtime_config.py`'s "production rejects
unsafe configuration" suite already covers every one of these rules — no new
validation code is needed for Sprint 030).

No production value is copied from staging's own secrets (`JWT_SECRET_KEY`,
`SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` must all be freshly generated,
distinct values) — reusing a staging secret in production is exactly the
kind of "copied ephemeral credential" this phase's contract forbids.

## Phase 9 — Domain / DNS plan

No custom domain is configured anywhere in this repository, Railway project,
or documentation — `git grep -i "simo-os\.\(com\|app\|io\)"` and a review of
every `docs/*.md` file found no claimed production hostname. **No domain is
invented here.** Per this phase's own instruction, Railway-generated
`*.up.railway.app` domains are used for launch verification, following the
exact same pattern already proven for staging
(`simo-api-staging-staging.up.railway.app`,
`simo-web-staging-staging.up.railway.app`): the production services will
receive their own generated domains
(`simo-api-production-production.up.railway.app`-shaped, exact string
determined at generation time in Phase 24/25) at deploy time. TLS is
Railway-managed automatically for every generated domain (same as staging,
already verified). `CORS_ALLOWED_ORIGINS` and `NEXT_PUBLIC_API_URL` are set
from these exact generated domains, per Phase 8. **Custom-domain
configuration remains an explicit post-launch follow-up**, not claimed as
done by this sprint.

## Phase 10 — Production security pre-flight (verified, not assumed)

Every one of these is already enforced by existing, already-tested code —
reconfirmed present, not re-implemented:

- HTTPS: Railway-terminated TLS on every generated domain (same mechanism
  already proven on staging).
- Security headers: `app/main.py`'s hardening middleware, environment-
  agnostic — same code path staging already uses (`tests/test_security_headers.py`).
- CORS: `CORSMiddleware` reads `cors_allowed_origins` from config; the
  production value will be the exact production web origin only, never a
  wildcard, never staging's.
- Debug disabled: no separate debug flag exists; `APP_ENV=production`
  disables loopback/development conveniences via `app/core/config.py`'s
  fail-closed validators.
- Sanitized errors: `tests/test_runtime_http.py::test_unhandled_exception_is_structured_redacted_and_keeps_safe_response` — already covers production error redaction, environment-agnostic.
- Auth enforcement / tenant isolation: the full RBAC/tenant stack
  (Sprints 009–012, verified again in Sprint 028's 72/72 matrix) is
  identical code, not environment-conditional.
- Non-root container: `Dockerfile`'s `useradd --uid 10001 simo` +
  `USER simo`, already the only container image this sprint deploys —
  unchanged from staging.
- No secrets in the client bundle: the frontend build only ever embeds
  `NEXT_PUBLIC_API_URL` (a public origin, not a secret) — verified by
  `apps/web/Dockerfile.test.mjs`'s existing "does not copy backend secrets"
  contract test.
- No seed mode: `SEED_DATA_ENABLED=false` (Phase 8, hard requirement).
- No exposed internal automation trigger: the follow-up job
  (`app/jobs/follow_up.py`) is a CLI-only entrypoint with no HTTP route —
  confirmed in Sprint 029's own smoke-gate documentation
  (`scripts/staging/smoke.py`'s `follow_up_notification` gate reason: "no
  HTTP trigger exists by design").
- Safe logging/redaction: `docs/PRODUCTION_RUNBOOK.md` §7, unchanged,
  environment-agnostic code.

**No PRODUCTION BLOCKER found in this pre-flight** — every control is
already shipped, tested, and proven on staging; production inherits it by
using the identical image and the identical (never-staging, never-default)
configuration values.

## Phase 11 — Production monitoring / operations (day one)

Using only capabilities already available (no new observability platform):

- **Deployment health:** Railway's own deployment status (`list-deployments`,
  `get-logs`) — already the tool used throughout Sprints 028/029.
- **`/health` / `/ready`:** the existing unauthenticated endpoints, polled
  manually at launch and by the existing `.github/workflows/staging-monitor.yml`-style
  mechanism if extended to production later (not required for this
  sprint's launch gate — manual polling during the launch window is
  sufficient and is what Phase 30 actually performs).
- **API errors / request IDs:** `X-Request-ID` on every response
  (`docs/PRODUCTION_RUNBOOK.md` §7), correlatable in `railway get-logs`.
- **Application logs:** structured JSON on stdout/stderr, same
  `railway get-logs --types build,deploy` mechanism already used all
  through Sprint 028/029.
- **Database availability:** `/ready`'s own bounded probe, plus direct
  `railway ssh ... alembic current` spot-checks.
- **Who/what to check during launch:** the operator (this agent, this
  session) watches Railway deployment status and `/health`/`/ready`
  continuously through the launch window (Phase 30); no external on-call
  system exists yet for this project, and none is invented here.

## Phase 12 — Follow-up automation production plan

Sprint 024 shipped `app/jobs/follow_up.py` as a CLI-only entrypoint,
deliberately with no persistent scheduler. Sprints 027 and 029 both
continued to list a persistent cron/scheduler as deferred, unreviewed scope.

**Decision: production launches with manual/operational execution of the
follow-up job, same as staging today.** This is not a new decision — it is
the existing, already-accepted contract carried forward unchanged. Adding
an unreviewed scheduler during a launch sprint would itself be exactly the
kind of silent scope expansion this phase's own instructions forbid.
Documented here as a **known operational limitation** (Phase 34), not
treated as a launch blocker: the follow-up feature still functions
correctly whenever the job is run (proven repeatedly, most recently in
Sprint 029's post-recovery check), it simply requires a human or an
external scheduler (e.g., a Railway cron service, GitHub Actions
`schedule:` trigger, or a manual runbook step) to invoke it — a decision
for a future sprint if operationally desired, not this one.

## Phase 13 — RC / main relationship (verified)

- RC tag: `v1.0.0-rc.1`.
- RC SHA: `a8f12776c548e91c0558fd43a05b84b7a6c2d1c7`.
- Current main (this sprint's baseline): `8b003533c85d7b61ef9cf4d0d19dd4c6c77d569e`.
- Reverified this session: `git rev-list -n 1 v1.0.0-rc.1` → still exactly
  `a8f1277...`; `git merge-base --is-ancestor v1.0.0-rc.1 HEAD` on this
  branch (based on current main) → true. **The tag has never moved.**

**Why the tag intentionally points at the pre-closeout candidate, not a
later commit:** Sprint 029's locked contract (§2) defines the candidate SHA
as "the exact commit ... at the moment Phase 12+13 both pass" — i.e., the
moment local verification and feature CI were both green. Everything after
that (the manifest artifact commit, the docs-closeout commit, the merge
commit) is process record-keeping *about* the already-frozen candidate, not
part of what was actually verified and deployed. Moving the tag forward to
include unreviewed later commits would silently expand what "the RC" means
after the fact — exactly what the immutability rule exists to prevent.

**Production candidate determination:** Sprint 030 itself will add real
configuration/documentation commits (this file, the launch contract, and
any genuine `LAUNCH-XXX` fixes Phase 15 finds). Per this sprint's own
instruction ("the preferred production candidate should be the final
reviewed Sprint 030 HEAD, not blindly the old RC SHA, if Sprint 030 contains
required launch configuration"): **the production candidate is the final
reviewed Sprint 030 commit** — determined once Phase 15/16/17 complete, not
assumed in advance to be `a8f1277` unchanged. If Sprint 030 turns out to add
zero code changes (only documentation), the production candidate may
coincide with `a8f1277`'s own application code, but the commit actually
tagged/deployed will still be Sprint 030's own reviewed HEAD, verified
through the complete Phase 16/17 gate again — no shortcut through
already-passed Sprint 029 verification is taken for granted.

---

## LOCKED PRODUCTION LAUNCH CONTRACT

This section is the sprint's frozen scope, committed separately from the
discovery draft above. Once committed, it is not renegotiated mid-sprint
except by explicitly re-opening discovery in a follow-up commit.

1. **Production candidate rule:** the exact commit on
   `sprint-030-production-launch` at the moment Phase 16 (full local
   verification) and Phase 17 (feature CI) both pass — the same discipline
   Sprint 029 used for the RC. If this sprint adds no code (docs only), the
   candidate's application code is byte-identical to `a8f1277`'s, but the
   candidate SHA, CI run, and staging rehearsal are still this sprint's own,
   never inherited without re-verification.
2. **Service topology:** exactly three new production services —
   `simo-api-production`, `simo-web-production`, `simo-postgres-production`
   — mirroring staging's proven shape. No additional service, no
   test/smoke-fixture service, no synthetic data generator, ever created in
   the `production` Railway environment under this contract.
3. **Database strategy:** production Postgres starts **empty**. No staging
   data, no synthetic business records, no seed rows beyond what
   `alembic upgrade head` itself creates (none — every migration in this
   repo's history is schema-only, confirmed via `grep -r "INSERT INTO"
   alembic/` finding no matches). Real data enters production only through
   the application itself, from real usage, after launch.
4. **Migration strategy:** `alembic upgrade head` runs only via the
   standard `preDeployCommand` (`python -m app.core.runtime_check &&
   alembic upgrade head && alembic current`) — never as a manual/ad-hoc
   step, never before the candidate commit is finalized. The migration head
   must be `2243d66f83da` unless this sprint's own candidate adds a new
   migration (permitted only as a genuine `LAUNCH-XXX` fix per Phase 15,
   never as unreviewed feature work).
5. **Config requirements (hard, no exception):** `APP_ENV=production`,
   `SEED_DATA_ENABLED=false`, every secret (`JWT_SECRET_KEY`,
   `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`) freshly generated and
   distinct from staging's and from the code's development defaults,
   `DATABASE_URL`/`CORS_ALLOWED_ORIGINS`/`NEXT_PUBLIC_API_URL` all wired as
   live Railway reference variables pointing at the new production
   services — never a copied static staging value, never a loopback/dev
   URL. `OPENAI_API_KEY` is omitted entirely (optional, never required).
6. **Domain strategy:** Railway-generated `*.up.railway.app` domains for
   launch, per Phase 9. Custom-domain configuration is explicitly
   out-of-scope follow-up, never claimed as live by this sprint.
7. **Smoke contract:** the same 27-gate `scripts/staging/smoke.py` suite,
   pointed at production's own generated domains once deployed — run
   **non-destructively first** (Phase 27: health/ready/homepage/security-
   headers/auth-rejection/CORS/runtime-config/DB-connectivity gates only)
   before any gate that creates data.
8. **Production UAT contract:** exactly one clearly-synthetic launch-
   verification workspace (Phase 28), exercising the minimal core journey
   (signup → login → Customer/Enquiry → Site Visit → Quote → approval →
   Project handoff → Project operation → portal → Command Centre) — no
   additional synthetic data beyond what that single journey needs, no real
   customer data, ever.
9. **Monitoring:** Railway deployment status + `/health`/`/ready` polling +
   `railway get-logs`, per Phase 11 — no new observability platform stood
   up for this launch.
10. **Rollback target/process:** for this **first-ever** production
    deployment, there is no previous production version to roll back to —
    "rollback" for this launch means taking the affected service offline
    (or leaving the previous, non-existent state, which is simply "no
    production service") rather than redeploying an older production
    commit that has never existed. Documented honestly per Phase 19, not
    invented. Post-launch, the Sprint 029 rollback procedure (redeploy the
    previous known-good clean export) becomes the standard mechanism for
    every subsequent production release.
11. **Backup requirement:** a first production database backup baseline is
    established immediately after schema initialization (Phase 23), using
    the exact Sprint 029-proven `pg_dump`/private-SSH-tunnel mechanism —
    never a new public database proxy on production, ever.
12. **Production GO criteria (Phase 20/21):** every checklist item in
    Phase 20 must be checked before the Phase 21 report is produced, and
    Phase 21's report is a **hard stop** — no production service is
    created, no production database is provisioned, no production API/Web
    is deployed, and no production migration runs, until the user
    explicitly authorizes crossing that gate. This holds regardless of how
    clean every preceding phase's evidence looks.

Locked by this commit. Execution (Phase 15 onward) begins next.

---

## Execution record (Phases 15–20)

### Phase 15 — required launch gaps

Reviewed the codebase for anything that would genuinely block launch:
`grep`ped `app/` and `apps/web/` for hardcoded `staging` references (found
only comments, no behavior); confirmed `deploy/railway/*.toml` are already
environment-agnostic (no hardcoded staging service names); confirmed the
security pre-flight (Phase 10) is already fully generic. **No genuine
launch-blocking defect found. No `LAUNCH-XXX` opened.** Manufacturing one
would violate this phase's own instruction.

### Phase 16 — full local release verification (candidate `e2f5a6f`)

- Backend (`pytest`): **556 passed, 1 skipped, 0 failed** — identical to
  Sprint 029's own baseline (no backend file changed this sprint).
- Frontend type-check/lint: clean. `pnpm --filter web test`: **69/69
  passed**. `test:runtime-config`: 7/7. `test:docker-contract`: 5/5.
  `pnpm build`: clean.
- Playwright (full suite): **13/13 passed**.
- `alembic heads`/`check`: single head `2243d66f83da`, no new upgrade
  operations detected.
- `git diff --check` (`8b00353..HEAD`): clean.

### Phase 17 — feature CI

Candidate `e2f5a6fc1d3215f02ebb1241c1adba238a2a5c58`: `backend`/`frontend`/
`e2e` all `completed`/`success`.

### Phase 18 — final staging rehearsal

The exact candidate `e2f5a6f` was deployed to staging (clean `git archive`
export, same procedure as every prior sprint) to rehearse against the
literal commit this sprint proposes for production — not merely inferred
from an earlier, code-identical deploy.

- API deployment `b9dc1a5f-60fa-4a68-8382-70bb716d196e`, web deployment
  `b194f073-3249-4b0c-8b07-7ba2bd07bdfb`, both SUCCESS.
- `/health` 200, `/ready` 200, web `/login` 200.
- `alembic current`: `2243d66f83da (head)` — matches heads.
- Smoke: **20 passed / 0 failed / 7 blocked** (of 27) — matches the
  established baseline exactly.
- Owner/Staff RBAC: a fresh synthetic Owner invited a fresh synthetic
  Staff member, who accepted and then correctly received **403** on an
  Owner-only action.
- Tenant isolation, portal token states, Command Centre: covered by the
  smoke run's own gates (`tenant_isolation`, `portal_token`,
  `command_centre`), all PASS.
- Follow-up job: `python -m app.jobs.follow_up` via `railway ssh` reached
  the real database and returned real results (`"examined": 33`).

**No BLOCKER/HIGH failure. Final dress rehearsal PASS.**

### Phase 19 — production backup/rollback prep

- The Sprint 029 rollback mechanism (clean `git archive <sha> | tar -x` +
  `railway up -c`) was itself just re-exercised for real in Phase 18 above
  — confirmed still valid, not merely re-read from documentation.
- Known-good candidate identity: `e2f5a6fc1d3215f02ebb1241c1adba238a2a5c58`
  (pending Phase 17's feature-CI confirmation above, which passed).
- Database backup capability: the Sprint 029-proven `pg_dump` (private SSH
  tunnel → disposable local Postgres) mechanism, unchanged, ready to run
  against production once real workspace data exists (Phase 23).
- Restore target/process: identical Sprint 029 mechanism, restore only into
  a disposable isolated target, never into production.
- **Realistic first-launch rollback behavior, stated honestly:** this is a
  first-ever production deployment — there is no previous production
  version to roll back to. If the first production deploy fails
  unacceptably, "rollback" means taking the affected service offline (or
  simply not promoting/continuing to use it) rather than redeploying an
  older production release that has never existed. No previous version is
  invented for the sake of having a rollback story.

### Phase 20 — pre-launch production checklist

| Item | Status |
|---|---|
| Sprint 029 GO verdict | ✅ confirmed |
| Sprint 030 discovery complete | ✅ Phases 2–13 |
| Staging credential issue resolved | ✅ Phase 3, rotated and verified |
| Production topology locked | ✅ Locked Contract §2 |
| Production DB plan locked | ✅ Locked Contract §3 |
| Production env config complete (plan, not yet provisioned) | ✅ Phase 8 / Locked Contract §5 |
| No staging/test secrets (as a rule for provisioning) | ✅ Locked Contract §5 |
| Debug disabled | ✅ no separate debug flag exists; `APP_ENV=production` is the mechanism |
| Seed disabled | ✅ `SEED_DATA_ENABLED=false` locked |
| CORS correct (plan) | ✅ production-origin-only, locked |
| Domains understood | ✅ Phase 9 — Railway-generated only; custom DNS honestly deferred |
| Local regression GREEN | ✅ Phase 16 |
| Feature CI GREEN | ✅ Phase 17 |
| Final staging rehearsal GREEN | ✅ Phase 18 |
| Rollback procedure ready | ✅ mechanism proven; first-launch reality documented honestly (Phase 19) |
| Backup procedure ready | ✅ Sprint 029-proven mechanism |
| Monitoring ready | ✅ Phase 11 |
| No unresolved LAUNCH BLOCKER | ✅ Phase 15 |
| Production environment verified | ✅ Phase 5 — zero services, clean slate, reverified |

**Every checklist item is satisfied. Proceeding to the Phase 21 hard gate.**
