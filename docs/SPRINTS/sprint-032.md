# Sprint 032 — Subscriptions, AI Product Retrieval & Quote Dimensions

First post-launch feature sprint after Sprint 031's "SIMO OS CORE DEVELOPMENT SPRINT PROGRAM COMPLETE" / `v1.0.1` close. Three independent workstreams, sequenced B → C → A per owner priority (production fixes first, commercial foundation second).

## 1. Discovery

### 1.1 Architecture

FastAPI + SQLAlchemy/Alembic backend (`app/`), Next.js 16 frontend (`apps/web`), Postgres, deployed to Railway (project `simo-os`: `simo-api-production`, `simo-web-production`, `simo-postgres-production`, `simo-follow-up-production`). Multi-tenant: `users`/`quotes`/`customers`/`projects` all key off `tenant_id`; `Tenant` (`app/tenants/`) is the only real account/business boundary in the schema — confirms Workstream A's subscription ownership belongs on `Tenant`, not `User`.

`materials` is intentionally **not** tenant-scoped (ADR-029: "shared reference catalogue, not tenant-owned data"), unlike every other domain table. Workstream B's search service respects this — it is a pure read over the shared catalogue and never touches tenant-owned tables, so tenant isolation is preserved by construction (nothing to leak).

No Stripe/billing code exists anywhere in the repo. No Stripe keys in `.env`, `.env.example`, or Railway service variables — confirmed by direct inspection before Workstream A began.

### 1.2 Workstream B — AI product/material retrieval: root cause

Two independent, uncoordinated matching implementations, both broken for natural-language queries:

1. `app/materials/service.py::get_by_name_and_thickness` (`app/database/crud.py::get_material_by_name_and_thickness`) — used by the quote calculator (`app/quotes/calculator.py`) — requires an **exact**, case-insensitive match on **both** `name` and `thickness` simultaneously via `func.lower(...) ==`. No thickness supplied → no match, regardless of how exact the name is. No partial name → no match.
2. `app/assistant/search.py::SearchAssistant.search` — used by `BrainManager`/`POST /process` — scores `material.name.lower() in text`, i.e. it requires the *full* catalogue name to appear verbatim as a substring of the user's sentence. "Do we have Carrara?" never matches "Carrara White"/"Carrara Mist" because neither full name is a substring of the query. There is no tokenization, no fuzzy matching, no alias support. The schema (`app/database/models.py::Material`) has no SKU/code or availability/status column.

Neither path can distinguish "not found" from "found nothing because the query didn't happen to contain the exact string" — both silently return empty results, and nothing upstream stops an LLM from then guessing.

### 1.3 Workstream C — quote dimension entry: root cause

There is no per-item dimension model. A whole `Quote` is one hardcoded "kitchen run" shape (`app/quotes/models.py::QuoteRequest`, `app/database/models.py::Quote`): a single `kitchen_length: float` (metres, unit implied and never stored), a fixed `DEPTH_M = 0.65` constant (`app/quotes/slab_calculator.py`), and boolean/int flags (`island`, `waterfall`, `splashback`, `upstands`) whose area math all reuses the *same* `kitchen_length` — a splashback or upstand cannot have its own length. `AIDraftService` (`app/quotes/ai_draft.py`) only ever fills that one ambiguous field via an OpenAI structured-output call with no unit/multi-piece/compound-dimension understanding (`"2400 x 600"`, `"2.4m by 600mm"`, quantities). The legacy `/estimate` path (`app/assistant/estimator.py`) is cruder still — hardcoded material-name string matches and "first number in the text is the kitchen length," with no unit awareness at all.

### 1.4 Workstream A — subscriptions: greenfield

No existing billing abstraction to extend. Confirmed ownership boundary: **Tenant**. Confirmed no Stripe credentials exist anywhere (repo, `.env`, Railway) — genuine external blocker for live/test-mode Stripe API verification, not for building or testing the integration code itself.

## 2. Approved design (locked by owner, see conversation record)

### 2.1 Workstream B

One canonical `MaterialSearchService` (`app/materials/search.py`) used by every assistant/quote path — `SearchAssistant`, the AI quote draft flow, and any future tool. No competing implementations. Normalizes case/whitespace/punctuation; matches across name, category, thickness, finish via exact → substring → token-overlap → fuzzy (`difflib`) tiers; returns an explicit `FOUND` / `MULTIPLE` / `NOT_FOUND` result object. Deterministic retrieval only — never a generative guess. Tenant isolation preserved by construction (materials are the shared catalogue; the service never queries tenant-owned tables).

### 2.2 Workstream C

Pragmatic structured-dimensions approach, **not** a full multi-line-item quote rewrite (explicitly deferred — see §6). Canonical internal unit: **millimetres**. New `Dimensions` value: `quantity`, `length_mm`, `width_mm`, `thickness_mm` (where relevant), plus input-unit metadata for traceability. Replaces `kitchen_length` as the source of truth; `kitchen_length` is preserved as a derived/backfilled column via migration — no existing quote data destroyed. Upstand/splashback get their own optional linear-length fields instead of silently reusing the worktop run length. AI/natural-language parser understands mm/cm/m, `"2400 x 600"`, `"2.4m by 600mm"`, multi-piece quantities; normalizes to mm; never silently invents a missing critical dimension (surfaces it as a warning requiring manual entry instead); interpreted dimensions are always shown back to the user before the quote is created.

### 2.3 Workstream A

Tenant-owned `Subscription`. Plans: **Pro** (£79/mo, £790/yr), **Business** (£149/mo, £1,490/yr), **Enterprise** (custom, contact-sales only, no self-service checkout). Annual visually presented as recommended/best-value ("2 months free"). Config-driven entitlement map keyed by plan (seats/AI usage/automation/integrations/analytics) — no usage-metering tables yet (YAGNI, per owner instruction). Stripe Checkout + Customer Portal, webhook handler with signature verification and an idempotency table (processed event IDs), server-side entitlement enforcement dependency. Stripe Price IDs from environment variables only, never hardcoded, never sent to the browser.

## 3. Genuine external blocker (disclosed up front, per owner's own contingency instruction)

No Stripe account/credentials exist. All Workstream A code, migrations, and mocked/integration tests will be completed and verified without them. E2E items requiring a live Stripe test-mode round trip (checkout session creation against Stripe's real API, webhook signature verification against a real signing secret, live cancel-at-period-end) cannot be executed by this sprint — they are documented as exact owner activation steps in the closeout report instead of fabricated as passing evidence.

## 4. Deferred (explicitly out of scope for Sprint 032)

A true multi-line-item quote architecture (many `QuoteItem` rows per `Quote`, each with independent type/dimensions/material) is **not** built this sprint. Today's single-job-per-quote shape is extended with structured dimensions, not replaced. Recommended as the next quote-domain evolution (see closeout §"Recommended Sprint 033").

## 5. Stripe setup — exact owner activation steps

No Stripe account/keys exist anywhere in this repo or in Railway's `simo-api-production` variables today (confirmed by direct inspection — only `APP_ENV, CORS_ALLOWED_ORIGINS, DATABASE_URL, JWT_*, SEED_*, UPLOAD_DIR` are set). Every step below is what the account owner needs to do; nothing in this list has been faked or assumed complete.

### 5.1 Stripe Dashboard — one-time setup

1. Create/sign in to a Stripe account (test mode first — the toggle is in the Dashboard's top-left).
2. **Products & Prices** → create two Products: "SIMO OS Pro" and "SIMO OS Business".
3. On **SIMO OS Pro**, add two recurring Prices: £79.00/month (GBP, recurring monthly) and £790.00/year (GBP, recurring yearly).
4. On **SIMO OS Business**, add two recurring Prices: £149.00/month and £1,490.00/year.
5. Do **not** create a Price for Enterprise — it stays contact-sales only, no self-service checkout by design.
6. Enable the **Customer Portal** (Settings → Billing → Customer portal) — turn on "Customers can cancel subscriptions" and "Customers can switch plans" if you want self-service plan switching through the portal as well as through SIMO OS's own UI.
7. **Developers → Webhooks** → add an endpoint:
   - URL: `https://simo-api-production-production.up.railway.app/api/v1/billing/webhook`
   - Events to send: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`, `invoice.paid`
   - Copy the endpoint's **Signing secret** (`whsec_...`) — this is `STRIPE_WEBHOOK_SECRET` below.
8. **Developers → API keys** → copy the **Secret key** (`sk_test_...` in test mode) — this is `STRIPE_SECRET_KEY` below. Never the publishable key for this — SIMO OS never sends a Stripe key to the browser at all (Checkout/Portal are server-created, redirect-only).

### 5.2 Environment variables — set on `simo-api-production` (Railway → that service → Variables)

| Variable | Value |
|---|---|
| `STRIPE_SECRET_KEY` | the Secret key from 5.1.8 |
| `STRIPE_WEBHOOK_SECRET` | the signing secret from 5.1.7 |
| `STRIPE_PRICE_PRO_MONTHLY` | Price ID for Pro £79/mo |
| `STRIPE_PRICE_PRO_ANNUAL` | Price ID for Pro £790/yr |
| `STRIPE_PRICE_BUSINESS_MONTHLY` | Price ID for Business £149/mo |
| `STRIPE_PRICE_BUSINESS_ANNUAL` | Price ID for Business £1,490/yr |
| `FRONTEND_BASE_URL` | `https://simo-web-production-production.up.railway.app` |

None of these are required for SIMO OS to run — every route that needs Stripe returns a clean 503 ("Billing is not configured") until they're set, same pattern as `OPENAI_API_KEY`.

### 5.3 Verifying test mode

1. Set the four `STRIPE_PRICE_*` + `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` variables using **test-mode** keys/prices.
2. As an Owner in SIMO OS, open `/pricing`, choose a plan → should redirect to a real `checkout.stripe.com` URL.
3. Complete checkout with Stripe's test card `4242 4242 4242 4242`, any future expiry/CVC.
4. Confirm the webhook fired in Stripe Dashboard → Developers → Webhooks → your endpoint → recent deliveries (should show `checkout.session.completed` with a 200 response).
5. Confirm `/settings` now shows the subscription as "active" with the correct plan/period.
6. Test cancellation via `/settings` → Cancel → confirm `cancel_at_period_end` shows in the UI and in the Stripe Dashboard.
7. Test the Customer Portal via `/settings` → Manage billing → confirm it opens Stripe's hosted portal for the right customer.

### 5.4 Going live

1. Repeat 5.1–5.2 in Stripe's **live mode** (separate Products/Prices/webhook/keys — test and live are fully separate in Stripe).
2. Replace the four `STRIPE_PRICE_*` variables and `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` with the live-mode values.
3. Re-run 5.3's checklist once against live mode with a real card before announcing pricing publicly.

## 6. Execution log

See closeout section at the end of this document for full evidence (migrations, tests, CI, production verification, SHAs).
