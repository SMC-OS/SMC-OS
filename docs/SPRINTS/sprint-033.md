# Sprint 033 — Stripe Activation, Deployment Hardening & Multi-Line Quotes

Direct continuation of Sprint 032 (`v1.1.0`, merged `edc13a7`, deployed and verified). Three workstreams, sequenced A → B → C per owner priority.

## 1. Discovery

### 1.1 Workstream A — Stripe

No Stripe credentials exist anywhere — repo `.env`, `.env.example`, or Railway's `simo-api-production` variables (`variableNames` still has no `STRIPE_*` entry; confirmed by direct inspection at the start of this sprint). Nothing has changed since Sprint 032's audit. The billing architecture itself (`app/billing/`) is unchanged and its 21 mocked tests (`tests/test_billing.py`) still pass. No live/test-mode Stripe API round trip is possible this sprint either — the owner activation boundary from Sprint 032 §5 stands unmodified.

### 1.2 Workstream B — Railway migration root cause

`railway service get-service-config` on `simo-api-production` shows the service's actual, applied config already correctly carries:

```
preDeployCommand: ["python -m app.core.runtime_check && alembic upgrade head && alembic current"]
```

— matching `deploy/railway/api.railway.toml` exactly. So the config-as-code wiring itself is *not* broken, contradicting the working hypothesis at the end of Sprint 032.

Pulling build+deploy logs for that exact deployment (`get-logs`, filtered on "alembic") shows the build phase installing the `alembic` *package* (from `pip install -r requirements.txt`) but **zero invocation of the `alembic` command** anywhere in the deploy-phase logs — not a failure, not an error, simply absent. `alembic current` via `railway ssh` immediately after confirmed the DB was still on the pre-Sprint-032 revision.

Both Sprint 032 production/staging deploys used `railway up --ci` ("stream build logs only, then exit" per the CLI's own help text). The evidence is consistent with `--ci` returning control before Railway's server-side deploy lifecycle — where `preDeployCommand` actually runs — has executed, rather than the config being missing or malformed. This can't be fully confirmed from outside Railway's internals, so the fix is designed to not depend on the answer: move the migration gate into the container's own entrypoint, so it runs on every start regardless of which Railway hook fires, which CLI flags are used, or whether a future deploy comes from the dashboard or `railway up`.

### 1.3 Workstream C — quote domain today

`Quote` (app/database/models.py) is a single-job header: one `material`/`thickness`/`quantity`/`length_mm`/`width_mm`/`thickness_mm` plus boolean `island`/`waterfall` count/`splashback`+`splashback_length_mm`/`upstands`+`upstands_length_mm` — Sprint 032's structured-dimension fix, but still fundamentally one job per quote, exactly as Sprint 032 §4 flagged for deferral. `QuoteCalculator`/`SlabCalculator` compute one price for the whole quote using bespoke per-feature constants (island extra run, fixed waterfall panel area, splashback/upstand height constants).

## 2. Approved design (see conversation record for full rationale)

### 2.1 Workstream B

A migration-gate entrypoint (`app/core/migrate_gate.py`) runs `runtime_check` then `alembic upgrade head` under a Postgres advisory lock, before `uvicorn` ever binds its port — wired into the Dockerfile's `CMD`. Fails closed (non-zero exit, container never starts, health check never passes, Railway's existing rolling-deploy semantics keep the previous revision serving). `deploy/railway/api.railway.toml`'s `preDeployCommand` is kept as a harmless, idempotent redundant safety net, not removed.

### 2.2 Workstream C

New `QuoteItem` child table: `item_type` (worktop/island/splashback/upstand/sill/waterfall_panel/other), `material`, `thickness`, `quantity`, `length_mm`, `width_mm`, `notes`, computed per-item price fields, `position` for ordering. `Quote` becomes a header (customer/status/postcode/approval/totals — totals now a sum over items). Every item type uses identical area math (quantity × length × width × wastage ÷ slab area) — no more bespoke per-feature constants — with a couple of small flat per-type surcharges (island install fee, waterfall panel fee) preserved for pricing continuity. Migration backfills exactly one `QuoteItem` per existing Sprint-032-and-earlier quote from its own scalar columns — no separate "legacy" flag, no data loss. Cross-item slab-sharing/nesting optimization is explicitly out of scope (same boundary Sprint 005 already drew for single items).

AI quote generation is extended to produce a list of independently-resolved item drafts (material + dimensions per item, via the same canonical `MaterialSearchService`/`dimension_parser` as Sprint 032), each shown to the user before creation, never fabricating a missing material or dimension.

## 3. Execution log

See closeout section at the end of this document.

## CLOSEOUT — Execution Evidence (2026-09-04)

### Workstream A — Stripe

No credentials appeared during this sprint. Architecture re-verified sound: `tests/test_billing.py` (21 tests) and `tests/test_rbac_matrix.py` (140 tests) re-run clean, no changes needed. Owner activation boundary is unchanged from Sprint 032 §5 — no live/test-mode Stripe API round trip was possible or attempted.

### Workstream B — Railway migration hardening: verified in production

The fix was verified empirically, not just by design review: both the staging and production deploys in this sprint ran `python -m alembic current` **immediately after `railway up`, with no manual migration step in between**, and both reported `d1a4f9c8b632 (head)` — the new Sprint 033 migration had already applied automatically. This is the first deploy in this project's history where that has been true. `tests/test_migrate_gate.py` (7 tests, including a real two-thread advisory-lock race proof against local Postgres) and the updated `tests/test_runtime_startup.py`/`tests/test_railway_contract.py` all pass.

### Workstream C — multi-line-item quotes

Migration backfill verified against a synthetic quote exercising every legacy flag simultaneously (island/waterfall/splashback/upstands) before merge — produced exactly the 5 expected item rows with correct dimensions in every case (see conversation record; not re-derived here to avoid duplicating evidence already gathered pre-merge).

### Tests

- Backend (`pytest`, real local Postgres): **685 passed, 1 skipped, 0 failed** (baseline before this sprint: 668 passed — 17 net new tests; several existing quote-related tests were rewritten, not just added, to match the new architecture, per the sprint's own instruction not to weaken coverage while evolving it).
- Frontend (`vitest run`, serial to avoid this session's own worker-pool contention — see "Known limitations"): **94 passed**, 0 failed. `eslint`: clean. `tsc --noEmit`: clean. `next build`: succeeds (17 routes).
- Playwright E2E: **16/16 passed** (13 pre-existing + 3 new: a manually-created 3-item quote whose independent dimensions round-trip correctly, an AI-generated 3-item quote via a mocked `/quotes/ai-draft` response, and item removal). A real bug was found and fixed during this work: the new spec's 3 tests originally shared one hardcoded signup email, causing a 409 conflict on the second/third signup — fixed with a per-test unique identity, matching this repo's own established RUN_ID convention.
- `git diff --check`: clean. Single alembic head (`d1a4f9c8b632`) confirmed both locally and (per Workstream B above) in staging and production.

### CI

All 6 checks green on PR #16 (backend/frontend/e2e × push+PR) and on post-merge `main` (run `33836003728`).

### Release

1. Branch `sprint-033-stripe-railway-multiline-quotes`, two commits: `894022a` (Workstream B) and `aac8b19` (Workstream C).
2. PR #16 opened to `main`, all 6 CI checks green.
3. Merged with an **explicit merge commit** `cbc17c2bc3c8be7a5e23b134b1197f9db5810ba0` (parents: `91d6da5e7906e5a01403eb14d6e278b99ee63cd6` = prior `main`/v1.1.0, `aac8b19ed1da27c43cd06f71d0fa6419da2285b1` = Sprint 033 branch HEAD). No squash, no rebase, no force push.
4. Tagged `v1.2.0` on the merge commit.

### Production deployment

Staging first (this repo's established convention), then production — both via `railway up` from a clean `git archive` export of the exact merge commit. **Migrations applied automatically on both environments** (see Workstream B above) — no `railway ssh` step was needed for the first time.

### Production verification (read-only — no test data created against real business data)

- `/health` → healthy, `/ready` → database reachable, on both staging and production.
- `alembic current` → `d1a4f9c8b632 (head)` on both staging and production, verified immediately post-deploy with no intervening manual step.
- AI retrieval, billing plans, multi-item dimension validation (`length_mm: 0` → 400), malformed `item_type` (→ 422), and the legacy `kitchen_length` alias all verified live on production.
- Existing auth/RBAC surfaces unaffected: bad-credential login, unauthenticated `/dashboard`/`/quotes` all correctly 401.
- Frontend: `/`, `/pricing`, `/quotes/new` all return 200 on production.
- `environment-status` (production): **0 issues / 0 failures across all 4 services** after deployment.
- Existing quote/customer/project workflows were not re-verified against real production data (no owner credentials used, by design — see Sprint 032's own precedent); confidence instead comes from the full local test suite (685 backend + 94 frontend) and 16/16 E2E specs, including the pre-existing `quote-handoff` spec exercising the exact same approve/handoff code paths against the new multi-item architecture.

### Known limitations

1. **Stripe still not configured** — unchanged from Sprint 032 §5.
2. **This session's own tooling contention.** Unrelated processes on this development machine (other coding-assistant tool installations — OpenAI Codex runtimes, MCP servers, Railway CLI proxies; ~286 stray Node processes observed at one point) caused transient `vitest`/`eslint` worker-spawn timeouts and occasional cross-test flakiness during this sprint's own verification — not caused by, or related to, the SIMO OS codebase. Every affected file was re-verified in isolation/serially and passed cleanly; this is a note about the development environment, not a product defect.
3. **Cross-item slab-sharing/nesting optimization** remains explicitly out of scope (each item computes its own slab requirement independently), matching the boundary Sprint 005 already drew.
4. **AI multi-item segmentation quality** depends on the LLM correctly isolating each item's own text span; this is not verifiable without real OPENAI_API_KEY access (none exists), so it's covered by mocked tests only, same limitation the Sprint 032 single-item AI flow already had.

### Recommended Sprint 034

Wire real Stripe test/live credentials once available and complete the full billing verification checklist from Sprint 032/033 §5; consider cross-item slab-sharing optimization if real job-cost feedback shows it matters; extend the quote editor with inline post-creation editing (currently create-only, matching every prior sprint's scope).

### Final status

**SPRINT 033 CLOSED.**
