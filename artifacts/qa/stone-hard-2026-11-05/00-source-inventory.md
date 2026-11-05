# 00 — Source inventory and access

Date: 2026-11-05 (UTC). Prepared by the QA agent session (Claude Code). Evidence type is stated on every line.
Nothing here is a production or staging change.

## Source baseline

| Item | Value | How established |
|---|---|---|
| Repository | SMC-OS/SMC-OS (PUBLIC) | GitHub |
| Candidate (PR #68 head) | `63e8ac97924f198f4f548c3971ffa024f11f8f77` | `git rev-parse`, PR #68 (draft, unmerged) |
| QA branch | `qa/geocore-closure-20261105`, branched from `63e8ac9` | local worktree `.worktrees/geocore-closure-20261105` |
| PR #68 base | `fix/production-dependencies-20261029` (production-watched) | GitHub |
| `main` | `2879dbf`, 2 commits not on the candidate, 50 the other way; trial merge reported no conflicts | `git log`, `git merge-tree` |
| Alembic head at `63e8ac9`, `d5f6012` (prod) and `bb1c1e9` (staging) | `94e5f6a7b8c9` (single head in code) | parsed `down_revision` of every file in `alembic/versions` at each SHA |
| New migration on QA branch | `a5f6b7c8d9e0` (parent `94e5f6a7b8c9`, single linear head) | file in branch; upgrade/downgrade/upgrade run on disposable PostgreSQL 16.2 |
| Live `alembic current` on staging/production | NOT CHECKED | needs `railway ssh … alembic current`; not run |

## Deployed services (Railway, read-only `get-service-config`, 2026-11-05)

| Project / service | Env | Watches branch | Running commit |
|---|---|---|---|
| simo-os / simo-api-production | production | `fix/production-dependencies-20261029` | `d5f6012` |
| simo-os / simo-web-production | production | `fix/production-dependencies-20261029` | `d5f6012` |
| simo-os / simo-marketing-production | production | `legal/sole-trader-identity-20261102` | `daf8759` |
| simo-os / simo-follow-up-production (cron 03:00) | production | `production-release` | `f7a1eaa` (8 Oct) |
| simo-os / simo-api-staging | staging | `fix/billing-invoice-parent-20261103` | `bb1c1e9` |
| simo-os / simo-web-staging | staging | `fix/launch-quote-repeat-save-20261031` | `0d745af` |
| simo-os / simo-marketing-staging | staging | `legal/sole-trader-identity-20261102` | `daf8759` |
| aura-staging / aura-api, aura-web | staging | other repo (SMC-OS/aura-mobile) | — |
| simo-founder-edition-staging / founder-edition-web | staging | other repo (SMC-OS/simo-founder); a STAGED, undeployed change exists that this session did not make and did not touch | — |
| simo-founder / simo-founder-edition-v2, simo-founder | production | other repo (SMC-OS/simo-founder) | — |

- Railway project webhooks for simo-os: none.
- `.github/workflows/ci.yml` runs on every push and PR and has no deploy step or deploy secret; `staging-monitor.yml` is a scheduled monitor.
- **Conclusion (push safety):** no Railway service in any of the four projects watches `qa/geocore-closure-20261105`, so pushing it triggers CI only.
- Production API pre-deploy runs `alembic upgrade head` and a production catalogue import with `--confirm-production`: it writes data on every deploy. Treat any production deploy as data-writing.
- Staging API pre-deploy (`deploy/railway/api.railway.toml`) runs `alembic upgrade head`: deploying this branch to staging would apply `a5f6b7c8d9e0` to the staging database. That is behind the runbook's backup STOP gate (see 06).

## Acceptance site

| Item | Result |
|---|---|
| URL | https://geocore-pilot-acceptance.alkawaritm.chatgpt.site/ |
| Access | HTTP 401 "Sign in required", only "Continue with ChatGPT" (desktop 1440x900 and mobile 390x844, Playwright Chromium) |
| Evidence | `artifacts/qa/geocore-closure-20261105/phase0/site/` in the operator's main checkout (screenshots, DOM, audit JSON; kept out of Git) |
| App seen? | No. Only the sign-in gate. No claim is made about the app's UI, persistence or controls |
| Source | Not found: no match in tracked files at `63e8ac9` or `origin/main`, commit messages, or GitHub code search of the SMC-OS org |
| site_sync | BLOCKED |
| Unblock | Owner signs in and exports, or provides source or an authorised test login. Login is not bypassed and owner credentials are not used |

## Ledger input

| Item | Value |
|---|---|
| File | `inputs/geocore-qa-ledger-2026-11-05T045907.json` (copy, byte-identical) |
| SHA-256 | `34e1e76d1fb3b4a9aa1e9edce4027cd2be156b586e06da42c2fc6f33fc68c69e` |
| Content | 110 cells, 18 journeys, 12 gates: all Unknown, no evidence. Defects STONE-GATE (Critical) and DEF-003 (High): Defective, checklist g1–g5 and d1–d9 all open |
| Personal data | None found (no e-mail addresses; only three GitHub URLs) |
| Canonical saved state "A3 v11" / pending "A4" | NOT LOCATED. The export says "Local workspace export. Not live-synced." Nothing is inferred or marked persisted |
| Schema file | None located; structure and counts checked only |

## Tools available this session

- Local: Python venv (pinned `requirements.txt`), embedded PostgreSQL 16.2 (pgserver) on 127.0.0.1, Node 22, pnpm 9 via corepack, Playwright Chromium.
- Absent: Docker, `psql`, Stripe CLI. The claude.ai Playwright connector failed to connect; local Playwright was used.
- Railway MCP: read-only calls only in this session.
- Stripe connector: requires authentication; not used. No Stripe call of any kind was made.
