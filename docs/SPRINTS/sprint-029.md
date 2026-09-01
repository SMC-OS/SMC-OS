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

