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
