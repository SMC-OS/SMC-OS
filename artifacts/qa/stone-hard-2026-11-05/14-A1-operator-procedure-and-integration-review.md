# 14 — A1 operator procedure, barrier v2, and integration review (8 November 2026)

> **Status: A1 BLOCKED (not executed). A2 BLOCKED. Release HARD NO-GO.**
> The proposed window **10 November 2026, 10:00–10:30 UTC is UNAPPROVED.** Nothing here approves it. No staging action was taken.
> "Local" below means a throwaway PostgreSQL 16 cluster inside the agent container. It is not staging evidence.

## 1. Integration review: the 7 commits against `qa/geocore-closure-20261105`

| Commit | From | What it is | Effect on QA code |
|---|---|---|---|
| `806dc38` Merge PR #50 | `main` | Stone-Hard remediation merge | Already in QA's history via its own commits |
| `2879dbf` Security alignment (#64) | `main` | Next.js 16.4.1 / Sharp 0.35.5 and Python pins | `requirements.txt`, `package.json`, root `pnpm-lock.yaml`, `ci.yml` are **byte-identical** to QA's. The only net difference is that `main` deleted the stale `apps/web/pnpm-lock.yaml` (4,145 lines) |
| `1d1a388` Merge of QA into this branch | this branch | Clean merge, no conflicts, both histories kept | none |
| `02fef54`, `62e0511`, `4923c06`, `6cba31c` | this branch | Barrier, capture tool, rehearsal, docs | Additive: `scripts/recovery/`, `tests/`, `artifacts/qa/` only |

**Checks done**

- CI is green on the merged head `6cba31c` (run 42486257832; run 42486218982 on the commit before it), i.e. QA plus `main` together pass. That predates the barrier-v2 commit made after, which has not yet had a CI run.
- No build depends on the deleted per-app lockfile: both the web Dockerfile and CI run `pnpm install --frozen-lockfile` at the workspace root.
- The API image copies only `requirements.txt`, `app/`, `alembic/` and `alembic.ini` (Dockerfile `COPY` lines), so none of the new tooling enters a runtime image.
- Fresh dependency audit today (8 Nov): `pip-audit` on `requirements.txt` and `pnpm audit --prod --audit-level high` both report **no known vulnerabilities** (same commands as CI). This is a local run, not a new CI run.
- The A2 candidate is unaffected: `740b6b4` stays pinned. None of this integration flows into `staging/stone-gate-acceptance`.

**Integration path that cannot deploy**

1. Review only: `git diff origin/qa/geocore-closure-20261105...ccr-12966459-skf9q0` (three dots shows this branch's changes since the common ancestor).
2. When the owner wants it in QA: open a **draft** PR with base `qa/geocore-closure-20261105` and head `ccr-12966459-skf9q0`. Never base it on `main` or a `fix/*` branch.
3. Before opening it, the owner should confirm in Railway that `qa/geocore-closure-20261105` is not a watched branch for any staging service. The repository records show the staging API and web bound to `fix/billing-invoice-parent-20261103` and `fix/launch-quote-repeat-save-20261031`, and PR #69's title warns that *its base* auto-deploys staging web. **This session cannot read Railway, so that is unverified.**
4. I have not opened a PR. Say the word and I will open the draft one.

## 2. Barrier v2: the two risks, and what actually fences them

| Risk | Fence | What it does *not* do |
|---|---|---|
| **A request crossing the freeze boundary can be half-applied** (row saved, follow-up write refused) | **Refusal, not prevention.** `db-engage` refuses (exit 6) unless the database has been idle for `--quiet-seconds` (default 60): no counted writes, no open transaction. After the cutoff it re-checks the counters; a write that landed in between marks the barrier `engaged-dirty` (exit 7), and A1 capture refuses it. | No lock can undo a commit that happened before the cutoff. A write landing in the last instant is *detected*, not stopped; you then release and retry when idle. |
| **A session can override read-only** (`SET default_transaction_read_only = off`, even as superuser) | **Write fence:** a detached holder keeps `SHARE` locks on every user table. They block every writer, including an overriding superuser (`INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `ALTER`, `DROP` all failed in rehearsal) but not readers or `pg_dump`. No schema change; not in a dump. A database-level `lock_timeout` makes ordinary writers fail in about a second instead of hanging. | An override session can still `CREATE` a **new** table, and a superuser can terminate the holder. Both are detected within one monitor sample (table count, holder locks), and the T1 fingerprint catches them. |

Also new: `--allow-busy` exists for local rehearsal only (refused on staging), and **A1 capture refuses any barrier engaged without a verified quiet period or without recorded fence locks.**

### Local rehearsal results (117 checks, 0 failed, two consecutive full passes)

| Requirement | Result (local) |
|---|---|
| Safe drain | In-flight transaction waited for and committed intact; undrainable one → exit 3, **not killed**, barrier left engaged, releasable |
| Refusal | Engage under live write load → exit 6, nothing changed, 102 user writes after the refusal (final run) all succeeded; open transaction → refused; unknown pre-existing settings → refused; wrong cluster / production flag / record in repo → refused |
| Straddling request | Detected as `engaged-dirty` (exit 7), refused by capture, released cleanly, clean retry engages |
| Override fenced | Superuser override: all six write forms rejected; content fingerprint identical; non-mutating `--override-probe` proves it (safe on staging) |
| Monitoring | Clean state reports clean; new table, lost holder, moved counters each reported |
| Emergency release | Works with the record **destroyed**; leaves no holder; writes work again |
| Recovery | Undrained and dirty barriers release; capture STOPs when the holder is killed mid-run |
| Approval gate | Eight incomplete/wrong approvals each refused (exit 2) with nothing changed; a complete one lets the rehearsal proceed |

Costs the owner should know: during the window, **writes fail after ~1 s (HTTP 500)** and reads work; login still worked in rehearsal because it does not write.

## 3. The owner-approval gate (technical, not procedural)

`db-engage --confirm-environment staging` and `a1_capture.py --confirm-environment staging` are **refused** unless `--approval-file` holds a complete, in-window approval: exact window (≤ 30 minutes, currently open), approval recorded before the window, **users notified ≥ 24 hours before it opens**, named operator matching `--operator`, private storage approved *and* encryption attested, barrier procedure approved, staging-only scope, historical backups and production untouched. The all-null template is `a1-owner-approval.TEMPLATE.json`; **only the owner fills it, and the completed copy stays outside the repository.** The proposed 10:00–10:30 UTC window is shown in the template as a proposal only.

Limit: the container-side `uploads-freeze` runs piped over `railway ssh` and cannot read the operator's file; the gate sits on `db-engage` (always first) and on capture (which refuses unfrozen uploads).

## 4. Operator preflight (run before the window; read-only)

```bash
# WSL2, on an ext4 path under the Linux home (not /mnt/c); venv with psycopg[binary]
install -d -m 700 ~/geocore-a1/RUN1 ~/geocore-a1/reports
export BARRIER_ADMIN_DSN=...   # from the runbook tunnel; type it via `read -s`, never on a command line
python3 scripts/recovery/operator_preflight.py \
  --out-dir ~/geocore-a1/RUN1 --report ~/geocore-a1/reports/preflight-$(date -u +%Y%m%dT%H%M%SZ).json \
  --remote-prefix "railway ssh --service simo-api-staging --environment staging --" \
  --pg-dump "$(command -v pg_dump)" --pg-restore "$(command -v pg_restore)" \
  --require-wsl2 --require-railway --attest-encrypted-volume \
  --timing-seconds 60 --transfer-budget-seconds 480 \
  --pgbackrest-json ~/geocore-a1/reports/pgbackrest-info.json --failures-explained-by "<log reference>" \
  --approval-file ~/geocore-a1/owner-approval.json
```

It checks, and reports each as PASS / FAIL / WARN / INFO / UNVERIFIED (exit 8 and `BLOCKED` on any FAIL):

| Area | Checks |
|---|---|
| Workstation | WSL2; Python ≥ 3.10; psycopg; `sha256sum`, `tar`, Railway CLI; **`pg_dump` and `pg_restore` major ≥ server major (PG 18)** |
| Private storage | Directory outside the repo; real filesystem (ext4, not `9p`/`drvfs`/`/mnt/c`); not in OneDrive/Dropbox/etc.; 0700 dirs and 0400 files honoured; **encryption attested by the operator (never assumed)**; free disk ≥ max(3 × (database + uploads), 3 GiB) |
| Container | Non-root user (root would bypass the freeze); uploads owned by that user; `/tmp` writable for the freeze state; inventory (files, bytes, digest); mount type; 0 entries writable until frozen; **timed read-only transfer with extrapolation against the budget** |
| Database | System identifier to put in the approval; version; superuser or not; relevant timeouts; no barrier already set; size, tables, Alembic revision; quiet probe; tunnel latency |
| Recovery | `pg_stat_archiver` decision rule; pgBackRest JSON continuity if supplied; **PITR stays UNVERIFIED without pgBackRest evidence**; the two historic failures stay UNEXPLAINED unless `--failures-explained-by` names the log evidence |
| Approval | The owner's approval file, validated; otherwise `UNAPPROVED` |

PITR evidence is collected on the Postgres service: `pgbackrest info --output=json > pgbackrest-info.json` and `pgbackrest check`, plus the archive-push log around 2026-11-04 10:40 UTC; the SQL form of the archiver check is `scripts/recovery/pitr_diagnostics.sql`. **The pgBackRest parser was tested on synthetic JSON that follows the documented shape; confirm it against the real output.**

Local run of the preflight (real code, local cluster and a local "container" as UID 10001): BLOCKED, with exactly two FAILs, *owner approval file* and *WAL archiver state* (the throwaway cluster has no archiving), and PITR UNVERIFIED. With a complete approval file the approval check turns PASS. A cloud-synced output directory, an unattested volume, and a PG16 client against a claimed PG18 server are each FAIL. **No real PG18 client or server was available here (the PostgreSQL apt repository is blocked from this environment), so the PG18 rule was exercised with the real PG16 binaries, not a real PG18 one.**

## 5. Window procedure (only after every prerequisite is met and the exact window is approved)

All times UTC. Stop at the first failure; `E` = emergency path in section 6.

| Step | Command (abbreviated) | Expect |
|---|---|---|
| 0 | Re-run the preflight; **require no FAIL and approval PASS** | exit 0 |
| 1 | `writer_barrier.py db-engage --confirm-environment staging --expect-system-identifier <id> --operator <name> --approval-file … --record <private>/a1-barrier.json --quiet-seconds 60` | exit 0, status `engaged`. Exit 6 = not quiet (wait/retry), 7 = dirty (release, retry), 3 = drain timeout |
| 2 | `railway ssh … -- python3 - uploads-freeze --dir /var/lib/simo-os/uploads --state /tmp/a1-uploads-state.json < writer_barrier.py` then `uploads-probe`; copy the state file off the container | probe exit 0 |
| 3 | `writer_barrier.py db-probe --override-probe` (no-op writes only) | exit 0 |
| 4 | `a1_capture.py --confirm-environment staging --approval-file … --remote-prefix "railway ssh … --" …` | `capture_verified: true`, four hashes, T0 = T1 |
| 5 | Operator retains the out-of-band hash record separately from the bundle | — |
| 6 | `uploads-thaw`, then `db-release`; confirm normal writes, check API error logs | no drift reported; writes work |

Do not restart, redeploy or change variables on `simo-api-staging` during steps 1–6 (production start-up crash-loops on a read-only uploads directory; thaw first).

## 6. Stop and emergency

| Situation | Action |
|---|---|
| Any STOP in capture | Partial artifacts are in `quarantine-*` (never deleted). Do not mark A1 PASS. Release, then plan a new window |
| Exit 6 / 7 / 3 from `db-engage` | Nothing is verified. `db-release` (safe if nothing was set), retry only inside the window |
| Record lost, holder stuck, anything unclear | `db-release --emergency` (stops holders by name, removes settings, evicts sessions) and `uploads-thaw --emergency` (restores the owner write bit) |
| Window expires | STOP. A1 is not verified. Release. A new window needs a new approval |

## 7. What A1 PASS means, and what it does not

**A1 capture verified** needs: the four hashes agreeing between two implementations, T0 = T1 on complete content, an uninterrupted barrier, a readable dump covering every table, and an archive identical to the live manifest. It still **does not prove restore usability or RPO/RTO**; that is the separate scratch restore (B4/B5). Existing daily backups are not accepted as a substitute. PITR/WAL health (B1) is its own gate and is **unverified**.

## 8. Status table

| Item | Local PASS | Staging PASS | State |
|---|---|---|---|
| Barrier v2 (refusal, fence, monitor, release, recovery) | Yes (117 checks) | No | **BLOCKED** on window, operator, storage, notice, procedure approval |
| Capture tool + approval gate | Yes | No | **BLOCKED** |
| Operator preflight | Yes (ran locally) | No | **BLOCKED**: needs Railway CLI, tunnel, a PG18 client |
| PITR/WAL health, 2 historic failures | n/a | No | **UNVERIFIED / UNEXPLAINED** |
| Uploads transfer timing | Local disk only | No | **UNMEASURED** on Railway |
| Staging identity, deployed SHAs, `alembic current` | n/a | No | **UNVERIFIED** (no Railway access here) |
| A1 matched recovery point | n/a | No | **NOT EXECUTED** |
| A2 deploy of `740b6b4`, eight staging Playwright tests, STONE-GATE g1–g5, DEF-003 d1–d9 | Dry run only (earlier) | No | **BLOCKED** until A1 is verified |
| Dependency audit (today) | Yes | n/a | Clean |
| CI on `740b6b4` and on merged head | n/a | n/a | Green (GitHub) |
