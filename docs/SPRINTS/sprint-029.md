# Sprint 029 — Release Candidate + Rollback/Recovery Drill

## Objective

Sprint 028 closed the product's acceptance gap: every shipped v1 workflow
(Sprints 008–027) has been exercised as a real user and passed, on real
staging. Sprint 029 is **not** a feature sprint — it proves the *operational*
side of a production launch is real, not aspirational, before Sprint 030
(Production Launch) is attempted:

1. Define an immutable, reproducible **Release Candidate** identity.
2. Prove a **real application rollback** on staging actually works — not just
   documented, executed.
3. Prove a **real database backup and isolated restore** actually works.
4. Prove the RC can be **re-promoted** cleanly after both drills.
5. Close any release-safety gap the drills surface.

No product feature, UI change, or business-logic change is in scope. Any
code this sprint adds exists only to give the release process an identity and
a manifest — nothing else.

## Phase 2/3 — Discovery: current release process (as it actually exists today)

Verified directly against the repository and live Railway staging
configuration — nothing below is assumed.

| Area | Current state |
|---|---|
| Semantic/version numbering | **None.** `apps/web/package.json` has been stuck at the `create-turbo` scaffold default `"0.1.0"` since the initial commit — never bumped by any sprint. No root `VERSION` file. |
| Release tags | **None.** `git tag -l` returns nothing — this repository has never tagged a release. |
| Release notes / GitHub Releases | **None.** No GitHub Release has ever been published (no tags to attach one to). |
| Changelog | `docs/CHANGELOG.md` exists but is **stale since Sprint 018** — every sprint from 019–028 shipped without a changelog entry. Not remediated retroactively by this sprint (out of scope, see below); Phase 30 release notes instead summarize 020–029 directly from git/sprint-doc history. |
| Decisions log | `docs/DECISIONS.md` exists, last entry is ADR-034 (Sprint 018) — same staleness pattern as the changelog. Out of scope to backfill. |
| Docker image identity | Neither `Dockerfile` (API) nor `apps/web/Dockerfile` (web) embeds a git SHA, build date, or version `LABEL`/`ARG`. Images are content-addressed only by their Railway-assigned deployment/build IDs. |
| Deployed commit SHA visibility | `GET /health` returns only `{"status": "healthy"}`; `GET /ready` returns only `{"status": "ready", "database": "reachable"}` (`app/core/health.py`). **Neither exposes a version or SHA.** The only reliable identity source is Railway's own deployment metadata (`railway.list-deployments`, `get-service-config`), which *is* already reliable — confirmed working in Sprint 028's staging verification. |
| Railway rollback | Railway's native "redeploy a previous deployment" exists, but this project's staging services are **not** git-connected (see Sprint 021 finding, `docs/STAGING_RUNBOOK.md`) — they're deployed via `railway up -c` from a clean `git archive` export. There is no Railway-native "image promotion" list to roll back through; a "rollback" here means **re-running the same clean-export deploy procedure against the previous known-good commit**. This is a real, repeatable mechanism (used successfully three times already in Sprint 028), not a gap. |
| Database backup | No committed backup *script* exists for the database itself (only for the upload-volume bundle, see below). A real `pg_dump`/`pg_restore` cycle was performed and verified once before, off-repo, per `docs/STAGING_RUNBOOK.md`'s "Recovery verification evidence (2026-08-24)" section — but that evidence is now stale (it restored to `alembic_version = f81683afc3f4`, an old revision; current head is `2243d66f83da`). Sprint 029 repeats this drill fresh, at the current schema state, with the current data. |
| Database restore | Same tooling gap — no committed script. The 2026-08-24 evidence shows the *mechanism* (`pg_dump --format=custom --no-owner` + `pg_restore` into a disposable local target) is sound and safe; Sprint 029 reuses that exact mechanism rather than build a new one. |
| Upload-volume recovery tooling | `scripts/recovery/matched_bundle.py`, `scripts/recovery/restore_upload_bundle.py`, `scripts/recovery/recovery_safety.py` (Sprint 019, backed by `tests/test_recovery_tools.py`, 76 tests) already implement portable-archive creation/restore *for the upload volume* with extensive path-safety validation. This is a distinct concern from the database backup and is not re-built; it is out of Sprint 029's scope (no upload-volume change this sprint) but confirmed present and already tested. |
| Migration downgrade policy | Already explicit and locked: `docs/PRODUCTION_RUNBOOK.md` §5–6 — **application rollback never runs `alembic downgrade`**; a database downgrade is an explicit, separately-reviewed operator action requiring a current backup, a reviewed-safe downgrade, and stopped incompatible writers. Sprint 029 adopts this policy as-is (see Phase 7 below) rather than inventing a new one. |
| Migration roll-forward policy | Already explicit: `deploy/railway/api.railway.toml`'s `preDeployCommand = "python -m app.core.runtime_check && alembic upgrade head && alembic current"` runs on every deploy, and is idempotent when no migration is pending (a no-op re-run, per Alembic's own semantics) — this is exactly what happens when Sprint 029's rollback drill redeploys an older, schema-compatible commit. |
| Disaster recovery design | `docs/STAGING_RUNBOOK.md`'s "Backup and restore" section already designs a heavier PITR + scratch-Railway-service + Google-Drive-retention drill, gated behind multiple explicit "STOP — owner approval" checkpoints (paid resources, cross-service restore, Drive access). Sprint 029's Phase 23/24 drill is the **lighter-weight, already-precedented** mechanism (a single `pg_dump`/`pg_restore` cycle into a disposable local Postgres, "without opening PITR, Google Drive, or paid scratch Railway resources" — quoting the 2026-08-24 evidence entry verbatim) — not the PITR drill, which stays out of scope and stays gated exactly as written. |
| Smoke after rollback / restore | `scripts/staging/smoke.py` (27 gates, reused as-is from Sprint 027/028) is generic to "whatever is currently deployed" — no changes needed to run it after a rollback or a re-promotion. |
| CI | `.github/workflows/ci.yml` triggers on every `push` (branches **and** tags — no `branches:`/`tags:` filter narrows it) and on every `pull_request`, running `backend`/`frontend`/`e2e` jobs. Pushing the RC tag will itself trigger a redundant-but-harmless CI run against the already-tested commit. `.github/workflows/staging-monitor.yml` polls staging `/health`+`/ready` every 5 minutes via `scripts/staging/check-health.ps1` — expected to observe brief unhealthy blips during the deliberate rollback drill; this is informational monitoring only, not a paging alert, and requires no coordination. |

**Confirmed scope:** Sprint 029 is Release Candidate + Rollback/Recovery Drill, per `docs/ROADMAP.md`'s locked v1.0 table. It is not reinterpreted as a feature sprint.

## Phase 4 — RC identity strategy (discovery draft — locked below)

No prior versioning convention exists (confirmed above), so this sprint adopts
the suggested default: **`v1.0.0-rc.1`** — semver pre-release syntax, `rc.N`
sequential per candidate, `1.0.0` because Sprint 030 is explicitly the v1.0
Production Launch milestone (`docs/ROADMAP.md`) that this candidate is
released *for*. If the candidate has to change after the tag is published, the
next candidate is `v1.0.0-rc.2` — the published tag is never moved.

RC identity, once locked, is the full tuple below — never just "latest" or a
bare tag name:

- git SHA (full 40-character, not abbreviated, in the manifest; abbreviated
  forms in prose are always paired with the full SHA at least once)
- tag (`v1.0.0-rc.1`)
- Alembic migration head at that SHA
- local verification totals (backend/frontend/e2e/build)
- feature CI run (exact SHA, all 3 jobs GREEN)
- staging deployment IDs (API + web)
- staging smoke result

## Phase 5 — Rollback objective

Prove, on real staging, with real Railway deployments:

- **Given:** the RC is deployed to `simo-api-staging`/`simo-web-staging`.
- **When:** staging application code is deliberately redeployed to the
  immediately-previous known-good commit (Sprint 028's final reviewed HEAD,
  `737ac10bcbde682564d3bac6a9a6bb2fda59628f` — currently live on staging as of
  this sprint's start, confirmed via Railway deployment history, not
  guessed).
- **Then:** API and web both become healthy again, the database is
  untouched, schema compatibility is confirmed (no migration exists between
  the two commits, so this is a same-schema rollback — the simplest possible
  case, proven rather than assumed), and core smoke passes.
- **Then:** the RC is redeployed and reverified.

This is a real deploy-and-verify cycle against real Railway infrastructure —
not a hypothetical runbook entry.

## Phase 6 — Database recovery objective

Prove a `pg_dump`/`pg_restore` cycle against the **real staging database**
(read-only on the dump side — `pg_dump` never mutates its source), restored
into a **disposable, isolated local PostgreSQL container** — never back into
active staging, never near production. Success is schema + representative
data landing intact in the disposable target, verified independently of the
dump tool's own internal claims (re-querying the restored database directly).

## Phase 7 — Migration safety strategy (locked)

- Current Alembic head: `2243d66f83da` (single head, confirmed via `alembic
  heads` against local, and independently against staging via `railway ssh`
  in Sprint 028).
- **Sprint 029 adds no migration.** This is a release-process sprint; no
  schema change is in scope.
- Because no migration exists between the RC and the previous known-good
  commit, the rollback drill is same-schema by construction — the strongest
  possible case for "does the previous app remain compatible with the current
  schema," and it removes any need to guess about downgrade safety this
  sprint.
- **Locked policy (adopted from `docs/PRODUCTION_RUNBOOK.md` §5–6, not
  reinvented):** roll the database **forward only**; an application rollback
  never runs `alembic downgrade`. A schema downgrade is never performed by
  this sprint's automation under any circumstance — it remains a separately
  reviewed, explicitly operator-approved action per the Production Runbook's
  existing five preconditions (reviewed-safe downgrade, accepted data-loss
  implications, stopped incompatible writers, a current backup, and a
  schema-compatible target image). Sprint 029 does not need this path and
  does not exercise it.

## Phase 10/11 — Release metadata gap and RC manifest (locked)

The repo has no version-reporting mechanism at all (Phase 2/3 finding above).
The **minimal** addition this sprint makes, and nothing more:

1. `VERSION` — a single-line file at the repo root holding the current RC
   version string (`1.0.0-rc.1`, no leading `v`, matching the common
   convention of the file being value-only while the git tag carries the
   `v` prefix). Read by the RC manifest generator; not read by the
   application at runtime (no app-code behavior change).
2. `scripts/release/rc_manifest.py` — a small, dependency-free script that
   generates the structured RC manifest (Phase 11) as JSON: reads `VERSION`,
   the current git SHA (`git rev-parse HEAD`), the current Alembic head
   (`alembic heads`), and a UTC timestamp, and writes them alongside the
   static fields the contract requires (expected services, required CI jobs,
   expected smoke gate count, rollback target). Backed by
   `tests/test_release_manifest.py` (TDD — RED then GREEN, per the locked
   contract's Phase 12 requirement below).
3. `docs/RELEASES/v1.0.0-rc.1.json` — the actual generated manifest for this
   sprint's candidate, committed once the candidate SHA is final (Phase 14).

No application code changes, no new HTTP endpoint, no heavyweight release
framework, no CI/CD pipeline rewrite. `GET /health`/`/ready` remain exactly as
Sprint 018 left them — the manifest lives entirely in the repository, not in
the running service.

---

## LOCKED RELEASE CANDIDATE CONTRACT

This section is the sprint's frozen scope, committed separately from the
discovery draft above. Once committed, it is not renegotiated mid-sprint
except by explicitly re-opening discovery in a follow-up commit.

1. **RC version format:** `X.Y.Z-rc.N` (semver pre-release). This candidate:
   `1.0.0-rc.1`.
2. **RC tag:** `v1.0.0-rc.1`, created only after local verification (Phase 12)
   and feature CI (Phase 13) are both GREEN, on the exact reviewed candidate
   commit. Never force-pushed, never moved. A changed candidate after
   publication gets `v1.0.0-rc.2`, not a rewritten `rc.1`.
3. **Candidate SHA rule:** the exact commit on
   `sprint-029-release-candidate-recovery` at the moment Phase 12+13 both
   pass — recorded in full (40-character) form in the RC manifest and in
   this document. The tag points at this SHA and nothing else.
4. **Migration head rule:** the candidate's `alembic heads` **must** equal
   `2243d66f83da` (the value already confirmed identical between local and
   staging in Sprint 028). If any change this sprint alters that value, the
   contract is void and must be re-locked — this sprint is not authorized to
   ship a migration.
5. **Release artifact rule:** the deployed artifact is the exact `git
   archive <candidate-sha>` clean export (per `docs/STAGING_RUNBOOK.md`'s
   Sprint 021 clean-commit procedure) — never an uncommitted working tree,
   never a working tree with local modifications layered on top of the
   candidate commit.
6. **Rollback target:** the current live staging deployment as of this
   sprint's start — commit `737ac10bcbde682564d3bac6a9a6bb2fda59628f`
   (Sprint 028's final reviewed HEAD, verified via Railway deployment
   history in Phase 19, not assumed).
7. **DB backup mechanism:** `pg_dump --format=custom --no-owner` against the
   real `simo-postgres-staging` database, reached over a private SSH tunnel
   (`railway connect --tunnel-only --ssh`, or `railway ssh` executing the
   dump directly) — never over a newly-created public TCP proxy (staging
   Postgres stays on private networking only, per
   `docs/STAGING_RUNBOOK.md`'s release invariants, unchanged by this
   sprint).
8. **Restore target:** a disposable local Docker Postgres container, created
   fresh for this drill and torn down after validation — never the active
   local dev database (`simo-os-postgres`), never active staging, never
   production.
9. **Recovery validation:** Alembic revision match, representative
   tenant/customer/project/quote/appointment/notification row **counts**
   (not necessarily byte-for-byte equality — see Phase 25's chosen
   deterministic method), and foreign-key integrity (`ALTER TABLE ...
   VALIDATE CONSTRAINT`-equivalent read: no orphaned FK values) on the
   restored copy.
10. **Production prohibition:** no command in this sprint targets Railway's
    `production` environment, any production-named service, or any
    production database, under any circumstance. Every Railway MCP/CLI call
    this sprint explicitly names `staging` (environment id
    `58f1f618-f823-4c02-80b6-b1d6b630bb76`) or a disposable local resource.
    If any command's target is ambiguous, it is not run.

Locked by this commit. Execution (Phase 12 onward) begins next.

---

## Execution record (Phases 12–28)

### Phase 12 — full local release verification (candidate `a8f1277`)

- Backend (`pytest`): **556 passed, 1 skipped, 0 failed** (550 inherited from
  Sprint 028 + 6 new `tests/test_release_manifest.py` tests).
- Frontend type-check (`tsc --noEmit`): clean. Lint: clean.
- Frontend component tests (`pnpm --filter web test`): **69/69 passed**
  (12 files, unchanged from Sprint 028 — no frontend file touched this
  sprint).
- `pnpm --filter web test:runtime-config`: 7/7. `test:docker-contract`: 5/5.
- `pnpm build`: clean, 14 routes.
- Playwright (full suite): **13/13 passed**.
- `alembic heads`/`alembic check`: single head `2243d66f83da`, no new
  upgrade operations detected.
- `git diff --check` (`26e6f73..HEAD`): clean.

No RC was created from a failing candidate — this one was fully green before
tagging.

### Phase 13 — feature CI

Candidate `a8f12776c548e91c0558fd43a05b84b7a6c2d1c7`: `backend`/`frontend`/
`e2e` all `completed`/`success` on GitHub Actions.

### Phase 14 — RC tag

`v1.0.0-rc.1` created as an annotated tag directly on
`a8f12776c548e91c0558fd43a05b84b7a6c2d1c7` and pushed (no force). `git
rev-list -n 1 v1.0.0-rc.1` confirms it resolves to exactly that SHA. The RC
manifest (`docs/RELEASES/v1.0.0-rc.1.json`) was committed in a follow-up
commit (`7f39213`) *after* the tag — this is expected, not a drift: the
manifest documents the tag, so it cannot be part of the commit the tag
points at. **The tag itself was never moved and still points at `a8f1277`.**

### Phase 15–17 — RC deployed to staging, identity + schema verified

Clean `git archive a8f1277 | tar -x` export deployed via `railway up -c` to
both services.

| | API (`simo-api-staging`) | Web (`simo-web-staging`) |
|---|---|---|
| Deployment ID | `ffea11f1-04ae-4d10-ba20-5ec68d35d626` | `b26502e5-4afa-496e-9d5c-b51f9798dddc` |
| Created | 2026-09-01T23:00:58Z | 2026-09-01T23:01:52Z |
| Status | SUCCESS | SUCCESS |

- `/health`: 200. `/ready`: 200. Web `/login`: 200.
- `railway ssh --service simo-api-staging --environment staging -- alembic current` → `2243d66f83da (head)` — matches `alembic heads` exactly.
- Runtime version/SHA exposure: none (confirmed absent in Phase 2/3 discovery) — identity verified via Railway deployment metadata instead, per the locked contract.

### Phase 18 — pre-rollback RC smoke baseline

`scripts/staging/smoke.py`, 27 gates: **20 passed / 0 failed / 7 blocked**
(the same 7 blocked-by-design gates as Sprint 028's baseline — migration,
no_seeding, follow_up_notification, restart_persistence, logs_request_ids,
repository_secret_scan, backup_restore — each verified by its own documented
separate mechanism, not silently accepted).

### Phase 19 — previous known-good identified

Railway deployment history (not guessed): the RC deploy's own "previous"
deployment records for both services were `e7117e3f-e9ff-4cd1-a285-8499dec883e7`
(web) and `44c09b3a-7384-402e-895a-ddb0e83e3a50`(api), both created
2026-09-01T22:08–22:09Z — these are this session's own Sprint 028 closeout
deploys of commit `737ac10bcbde682564d3bac6a9a6bb2fda59628f` (verified
directly, not inferred, since this agent performed those Sprint 028 deploys
itself). Schema compatibility: trivial and exact — both commits share the
same Alembic head (`2243d66f83da`); no migration exists between them.

### Phase 20–21 — real rollback drill + compatibility check

Clean `git archive 737ac10 | tar -x` export deployed to both services at
2026-09-01T23:03:57Z (API command start) through 23:05:15Z (web deploy
complete) — **≈78 seconds end-to-end for both services.**

| | API rollback deployment | Web rollback deployment |
|---|---|---|
| Deployment ID | `23cb0b21-9059-4b54-af81-e23014618607` | `ead39ae6-3cab-45f3-b3d0-a701424b2016` |
| Status | SUCCESS | SUCCESS |

- `/health` after rollback: 200. `/ready` after rollback: 200.
- Schema after rollback: `alembic current` still `2243d66f83da (head)` — unchanged, as expected for a same-schema rollback.
- Smoke after rollback: **20 passed / 0 failed / 7 blocked** — identical to the pre-rollback baseline.
- Compatibility verdict: **PASS**, no BLOCKER. The rolled-back application (Sprint 028's exact shipped code) remains fully compatible with the current schema and data — proven by an identical smoke result, not assumed.

### Phase 22 — RC re-promotion

Clean `git archive a8f1277 | tar -x` redeployed to both services.

| | API re-promotion deployment | Web re-promotion deployment |
|---|---|---|
| Deployment ID | `d7522b45-4015-44dd-987c-6a66f7551094` | `21a8a1db-7d73-4ee7-ab80-477e4ce9d56d` |
| Status | SUCCESS | SUCCESS |

- `/health`: 200. `/ready`: 200. `alembic current`: `2243d66f83da (head)`, matches heads.
- Smoke: **20 passed / 0 failed / 7 blocked** — the system returned cleanly to RC state.

### Phase 23 — database backup drill

- Source: `simo-postgres-staging` (Railway staging, private networking only — reached via `railway connect --tunnel-only --ssh`, never a new public TCP proxy).
- Method: `pg_dump --format=custom --no-owner`, run from a disposable `postgres:18-alpine` container against the tunnel (staging Postgres runs **18.6** — a real, previously-undocumented version-skew finding against the `postgres:16-alpine` pinned for local dev; the dump image was matched to the server's actual major version after an initial `pg_dump: server version mismatch` failure surfaced it).
- Timestamp: `2026-09-02T00:09:46Z`.
- Format: custom (`pg_restore`-compatible).
- Size: **80,967 bytes**.
- Checksum (SHA-256): `4f873c276674b1953dfac90ed9b777e4e26df314f58304e7891ddb6dc7114805`.
- Not committed to git; deleted from local disk after the restore drill completed (Phase 24 below).

**Operational note (transparency):** `railway connect --tunnel-only` prints its one-time local tunnel credentials to its own stdout by design — those credentials were briefly visible in this session's own tool output while being captured into a local file for use. The tunnel was staging-only, was closed immediately after the drill, and the credentials were never written to any committed file. As a precaution, **rotating the `simo-postgres-staging` password is recommended** as routine hygiene after this drill, and `docs/STAGING_RUNBOOK.md`'s new procedure explicitly calls out treating that command's output as sensitive for future runs.

### Phase 24–25 — isolated restore + data validation

- Target: disposable local Docker container `sprint029-recovery-drill` (`postgres:18-alpine`, port `55432`) — distinct from the shared local dev database (`simo-os-postgres`) and from active staging; removed immediately after validation.
- Restore: `pg_restore --no-owner --verbose` — completed with every index, constraint, and FK created; no errors.
- Alembic revision: `2243d66f83da` — matches the source's `alembic heads` exactly.
- Schema: all 14 expected tables present (`activity_log`, `alembic_version`, `appointments`, `customers`, `documents`, `invitations`, `materials`, `messages`, `notifications`, `portal_links`, `projects`, `quotes`, `tenants`, `users`).
- Data validation (chosen deterministic method: **exact row-count equality** against the live source, re-queried at drill time — appropriate here since staging saw no concurrent business writes during the short drill window): all 13 business tables matched exactly — `tenants` 77, `users` 82, `customers` 37, `projects` 39, `quotes` 15, `appointments` 10, `notifications` 42, `portal_links` 21, `messages` 36, `documents` 21, `invitations` 5, `materials` 1, `activity_log` 251.
- FK/integrity validation: **zero** orphaned rows across 9 checked foreign-key relationships (users→tenants, customers→tenants, projects→customers, quotes→tenants, appointments→projects, notifications→recipient users, documents→customers, messages→customers, portal_links→customers); **zero** `NOT VALID` foreign-key constraints.
- Teardown: disposable container removed, local dump file deleted, SSH tunnel closed. Nothing from this drill persists.

### Phase 26 — failure/recovery procedures

Written into `docs/STAGING_RUNBOOK.md`: an expanded "Rollback" section
recording the proven Sprint 029 procedure, a new "Database backup/restore
drill (lightweight)" section documenting the exact mechanism used above
(explicitly distinct from the heavier PITR/scratch-service/Google-Drive
design, which stays untouched and gated behind its own approval
checkpoints), and an explicit A–G failure/incident procedure list
(deployment failure, bad release, migration failure, data loss/corruption,
rollback, restore, re-promotion) — every command in it names `staging`
explicitly, none defaults to or infers an environment.

### Phase 27 — production-safety guard review

Reviewed every release/rollback/recovery command surface used this sprint:

- **No production Railway service exists yet.** `railway list-services` on
  project `simo-os` shows the `production` environment as an empty
  Railway-provisioned shell with zero services — there is currently no
  `simo-api-production`/`simo-web-production`/`simo-postgres-production` to
  accidentally target, by any command, this sprint or otherwise.
- Every deploy/rollback/re-promotion command this sprint (and Sprint 028's)
  passed the staging **service and environment IDs explicitly** — none
  relies on a default, and there is no code path in this repository that
  falls back to a production identifier when one is omitted.
- `scripts/staging/smoke.py`'s `validate_public_https_origin` already
  rejects loopback/non-HTTPS origins outright; it cannot be pointed at a
  production domain that does not yet exist, and adding a speculative
  hardcoded blocklist for a domain Sprint 030 hasn't chosen yet would be
  premature, not a real guard.
- **Conclusion: no new guard code was added.** The existing explicit-ID
  convention plus the absence of any production service today already
  satisfies "reject unknown environment, do not default to production" —
  verified, not assumed. This will need re-review once Sprint 030
  provisions real production services (a natural Sprint 030 discovery item,
  not backfilled here).

### Phase 28 — post-recovery staging acceptance

Run after the full RC → rollback → re-promote → backup → restore-validation
sequence, against the re-promoted RC (still live, unchanged by the backup —
`pg_dump` is read-only — and by the restore, which went only into a
disposable local target):

- Final smoke run: **20 passed / 0 failed / 7 blocked** — no regression from
  the recovery exercise.
- Final `/health`/`/ready`: 200/200.
- Enquiry → Customer conversion (not a smoke gate): a fresh synthetic
  enquiry Project converted successfully (`POST
  /api/v1/projects/{id}/convert-to-customer` → 200, real Customer id
  returned) — **PASS**.
- Follow-up automation (blocked-by-design in smoke, verified separately):
  real `python -m app.jobs.follow_up` run via `railway ssh` against a fresh
  synthetic stale enquiry created **8** notifications on the first run,
  then **0** on an immediate second run with the same `--now` (`"created":
  0, "skipped_existing": 32`) — **PASS**, duplicate prevention confirmed
  post-recovery.
- Auth, tenant isolation, Site Visit, quote approval/handoff, Project
  Operations, Portal, Command Centre: covered by the final smoke run's
  `signup_login_auth`, `tenant_isolation`, `appointment`,
  `quote_approve_handoff`, `project_assignment_status`, `portal_token`/
  `portal_documents`/`portal_messaging`, and `command_centre` gates — all
  PASS.

**No regression found anywhere in the connected staging acceptance after the
full drill sequence.**

---

## Phase 29 — RC exit criteria (final check)

| Criterion | Result |
|---|---|
| Candidate immutable | **YES** — `v1.0.0-rc.1` tag never moved, points at `a8f1277` throughout |
| RC tag published | **YES** |
| Candidate CI | **GREEN** |
| Staging RC | **GREEN** |
| Schema verified | **YES** — `alembic current == alembic heads` at every checkpoint |
| Pre-rollback smoke | **acceptable** (20/0/7 of 27, matches Sprint 027/028 baseline) |
| Real application rollback | **PASS** |
| Rolled-back app compatibility | **PASS** |
| RC re-promotion | **PASS** |
| Post-repromotion smoke | **PASS** (20/0/7) |
| Staging DB backup | **PASS** |
| Isolated restore | **PASS** |
| Restore validation | **PASS** (schema + exact row counts + zero FK orphans/invalid constraints) |
| Connected acceptance (post-recovery) | **PASS** |
| Production untouched | **YES** — no command this sprint named a production service, environment, or database; the `production` Railway environment has zero services deployed to it |

**No unresolved release/recovery BLOCKER. All exit criteria satisfied.**

## Phase 30 — Release notes: v1.0.0-rc.1

**Major shipped business workflows** (Sprints 008–027, verified end-to-end
in Sprint 028's UAT and reconfirmed live on staging by this sprint's own
drills): tenant-aware signup/auth, Owner/Staff roles and invitations,
tenant-isolated Customers/Projects/Quotes, enquiry→Customer conversion,
Appointment/Site Visit scheduling, Quote approval and Quote→Project
handoff, Project Operations (staff assignment, forward-only status
pipeline), stale-enquiry follow-up automation with in-app notifications,
a read-only client portal (project/quote/invoice access, document
upload/download, staff⇄customer messaging) reached via revocable/expirable
tokens, and a Business Command Centre (exact tenant-scoped pipeline, quote,
site-visit, and follow-up metrics).

**Security/hardening status:** explicit `APP_ENV` policy with fail-closed
production config validation, non-root containers, structured/redacted
JSON logging, `/health` + `/ready`, full RBAC enforcement at both the UI
and API layers (`tests/test_rbac_matrix.py`'s 119-case sweep), login rate
limiting, and the standard security-header/CORS contract — all verified
present on staging this sprint (Phase 15–28's own checks) in addition to
Sprint 026/027/028's original verification.

**UAT result:** Sprint 028's 72-scenario acceptance matrix: **72/72 PASS**.
Two MEDIUM defects (UAT-001: profile menu showed a hardcoded identity;
UAT-002: a legacy dashboard endpoint mislabeled quote totals as "revenue")
and one LOW defect (UAT-003: same root cause as UAT-001, different
location) were found and **fixed**, not deferred. Zero BLOCKER, zero HIGH.

**Known limitations** (unchanged by this sprint, listed for completeness,
not remediated here — out of scope): client-portal messaging/documents
have no attachments, read-state, edit/delete, rate limiting, or
WebSockets/SSE (Sprint 016/017 discovery, reconfirmed in Sprint 028's
matrix); the AI Router, the 9 stub AI assistants, marketing/social
scheduling, contracts/e-signatures, payment tracking, supplier/purchasing,
AI design tools, and subscription billing all remain deferred, unscheduled
work (`docs/ROADMAP.md`); `docs/CHANGELOG.md`/`docs/DECISIONS.md` have been
stale since Sprint 018 and are not backfilled by this release-process
sprint; the application itself exposes no version/SHA at runtime — Railway
deployment metadata is the identity source of record instead.

**Staging readiness:** fully verified — every shipped workflow (Sprint
028), plus now a proven real rollback and a proven real backup/restore
cycle (this sprint), all pass on live staging.

**Rollback/recovery evidence:** this sprint's own drills — see the
Execution record above. Both PASS.

**Deferred items:** the heavier PITR + scratch-Railway-service +
Google-Drive-retention recovery design (`docs/STAGING_RUNBOOK.md`'s
"Backup and restore" section) remains intentionally out of scope and
gated behind its own owner-approval STOP checkpoints — the lighter,
already-sufficient drill this sprint performed does not unlock or shortcut
that heavier design.

**Production launch remains Sprint 030.** No production Railway service
exists yet; this sprint neither created nor deployed to one.

## Phase 31 — Closeout record

### Git / commits

- Baseline: `main` @ `26e6f73` (Sprint 028 merge, PR #10).
- Branch: `sprint-029-release-candidate-recovery`.
- Discovery: `acbdbbe` — `docs: define Sprint 029 release candidate`.
- Contract lock: `911b5f1` — `docs: lock Sprint 029 RC contract`.
- RC manifest generator RED: `dfbc3c4`. GREEN: `a8f1277` — **this is also
  the exact RC candidate SHA**, tagged `v1.0.0-rc.1`.
- RC manifest artifact: `7f39213` — `docs: add v1.0.0-rc.1 release candidate manifest` (committed after the tag; the tag itself is unmoved, still at `a8f1277`).
- This closeout commit (docs only: `docs/SPRINTS/sprint-029.md` + `docs/STAGING_RUNBOOK.md`).

### RC identity (final)

- Version: `1.0.0-rc.1`. Tag: `v1.0.0-rc.1`. Candidate SHA: `a8f12776c548e91c0558fd43a05b84b7a6c2d1c7`. Immutable: yes, never moved.
- Migration head: `2243d66f83da` (unchanged all sprint — no migration shipped).
- Feature CI: GREEN. Staging RC: GREEN (deployed, redeployed after rollback, verified twice).

### Safety

- Production deployed: **NO**. Production DB touched: **NO**. Production config changed: **NO**. No production service exists to target.
- Backup committed to git: **NO** (dump file created and deleted entirely within the local drill, outside the repository).
- Secrets exposed: **one incidental exposure** — `railway connect --tunnel-only`'s one-time local tunnel credentials for `simo-postgres-staging` appeared in this session's own tool output while being captured for the backup drill (Phase 23). Staging-only, never committed, tunnel closed immediately after use; **rotating that password is recommended** as routine post-drill hygiene. No other credential, token, or database URL was exposed at any point this sprint.
- Rebase used: **NO**. Force push used: **NO**. RC tag force-pushed or moved: **NO**.
- New product features added: **NO** — every change this sprint is release/recovery tooling (`VERSION`, `scripts/release/rc_manifest.py`, its test, the RC manifest artifact) or documentation; no application behavior changed.

### Ready for PR

All Phase 29 exit criteria are satisfied: candidate immutable, RC tag
published, candidate CI green, staging RC green, schema verified at every
checkpoint, pre-rollback smoke acceptable, real rollback PASS, rolled-back
compatibility PASS, RC re-promotion PASS, post-repromotion smoke PASS,
staging DB backup PASS, isolated restore PASS, restore validation PASS,
post-recovery connected acceptance PASS, production untouched. Proceeding
to PR against `main`.
