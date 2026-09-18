# Sprint 041 — GeoCore Premium OS Plan 02: Public Homepage + Request Demo + 14-Day Trial Funnel

**Branch:** `sprint-041-public-homepage-demo-trial-funnel`
**Base:** `origin/main` @ `79350a082bc8f88b1946f9df25423d3a2b9de091` (Plan 01 merge, PR #42)
**Alembic head at branch point (verified, not assumed):** `0f93d11b04a4`
**Status:** CODE-COMPLETE — not deployed, not merged

---

## 1. Mission

Build the public-facing GeoCore experience a prospective customer sees before
creating an account: a premium homepage that explains what GeoCore is, who it is
for, and what is inside it; a public pricing page with an honest, card-required
14-day trial disclosure; a public Request Demo path that needs neither account nor
card; and the handoff into the existing, unmodified Sprint 032/039 signup + Stripe
Checkout flow. No second billing system, no unauthenticated trial activation, no
"no card required" claim anywhere near the trial.

Authoritative sources, in priority order: the Master Spec
(`2026-09-17-geocore-premium-os-design-v3.md`), the Implementation Roadmap
(`2026-09-17-geocore-premium-os-implementation-roadmap.md`). Plan 01 (Adaptive
Workflows + Project 360) is complete and merged (PR #42). Plan 03 and every later
roadmap phase are explicitly out of scope for this sprint.

---

## 2. What was built, commit by commit

1. **`feat(billing): expose trial_days on GET /billing/plans`** — `PlanOut.trial_days`,
   computed from the existing `TRIAL_LENGTH_DAYS` constant (`app/billing/plans.py`),
   null for Enterprise. The single source the new public trial-disclosure component
   reads its trial length from, rather than a second, hard-coded marketing figure.
2. **`feat(demo): add public demo request capture`** — the standalone, platform-owned
   `demo_requests` table (migration `bfed99c6fa8c`) and `POST /api/v1/demo-requests`
   (`app/demo_requests/`): public, rate-limited per email via a `CooldownLimiter`
   matching the existing password-reset/verification-resend pattern, server-validated
   trades (canonical catalogue), team size, phone, email and message length, a
   honeypot that silently discards bot submissions, and no client-supplied
   status/source. No list/admin endpoint. Also opens the API's dev CORS origins to
   `apps/marketing`'s dev server (port 3001).
3. **`feat(marketing): build GeoCore premium public homepage`** — replaces the
   Sprint 034 interim holding page with the full 17-section homepage (see §3), a
   shared `Nav`/`Footer` used by every public page, and the positioning change to
   the Master Spec's explicit "GeoCore — The Operating System for Stone &
   Construction" (ADR-043, `docs/DECISIONS.md`).
4. **`feat(marketing): add pricing and trial disclosure`** — a public `/pricing`
   page fetching the live plan catalogue from `GET /billing/plans` (the same
   contract `apps/web/app/pricing` already uses), and the reusable
   `TrialDisclosure` component.
5. **`feat(marketing): add public demo request form`** — `/request-demo`, posting to
   the new backend endpoint, with the specified success copy exactly.
6. **`test(marketing): cover public trial and demo journeys`** — a third Playwright
   webServer (apps/marketing's own dev server) and four E2E journeys.
7. **`test(marketing): guard the card-required trial copy contract`** — a static
   source-text test guarding the single hardest commercial-copy rule ("no card
   required" must never appear near the trial).

---

## 3. Homepage sections implemented (18, per the Master Spec §2.2 IA)

Hero · Trust/Product Summary · What GeoCore Does (Task 2, honestly labelled
Available/Planned/Coming) · Command Center · Project 360 · Quotes & Customers ·
Trade Workflows (with real per-trade example sequences from
`app/workflows/catalogue.py`) · Stone Specialist Tools · Construction Operations ·
Scheduling/Tasks/Team · Automations · Financial & Operational Visibility ·
Supported Trades (27, from the canonical `app/trades/catalogue.py`) · Pricing
(teaser, links to `/pricing`) · 14-Day Trial Explanation · Request Demo · Final CTA
· Footer.

Nothing not yet built is presented as live: the Master Stone Catalogue (Plan 03)
and deeper Financials/Materials are explicitly labelled "Coming in GeoCore Premium
OS" or "Planned," never advertised as available today.

---

## 4. Demo form behaviour

`/request-demo` collects first/last name, work email, phone (optional), company
name, team size (closed set), primary trade(s) (multi-select, canonical catalogue),
current software (optional), message (optional), preferred contact method
(optional) — plus a CSS-hidden honeypot field. No account or card is required or
implied anywhere in this flow. On submit, `POST /api/v1/demo-requests` persists a
`demo_requests` row (server-assigned `status="new"`, `source="marketing_homepage"`)
and the page shows "Demo request received. We'll contact you using the details you
provided." with **Explore GeoCore** / **View Pricing** follow-ons — no promised
response time, per the plan's own instruction not to invent one.

---

## 5. Trial flow behaviour

`/pricing` shows each self-service plan's real price and, via `TrialDisclosure`,
states plainly: the trial length (from `plan.trial_days`), **£0 due today**, that a
payment method is required to activate the trial, and the first billing
date/amount — the date computed client-side as "today + trial_days" (the same real
constant Stripe's own `trial_period_days` uses), the amount read directly from the
plan. The phrase "no card required" never appears near the trial (enforced by
`trial-and-demo-contract.test.mjs`). Each self-service CTA links to
`{APP_URL}/signup?plan=<id>&billing_period=<period>` — the existing, unmodified
Sprint 032/039 signup → email verification → `/pricing` → Stripe Checkout flow.
Nothing in this plan bypasses email verification, the password policy, the
billing-access gate, or Stripe/webhook authority; nothing manually activates a
trial from the browser.

**Known limitation:** the `plan`/`billing_period` query params are not yet
threaded through `apps/web/app/signup` to pre-select the plan on `/pricing` after
verification — the visitor lands on `/pricing` and chooses explicitly, which is
correct per the Master Spec (trial/plan choice must be explicit) but is a less
seamless handoff than pre-selecting. Deliberately deferred rather than touching
`apps/web`'s signup/pricing logic under this plan's time budget; flagged here as a
real, scoped-out follow-up, not a silent gap.

---

## 6. Pricing verified

Starter £29/mo (1 user) · Team £59/mo (3 users) · Pro £99/mo (10 users) · Business
£199/mo (25 users) · Enterprise custom (Request a Demo). Sourced live from
`GET /billing/plans` (`app/billing/plans.py`'s `PRICING_GBP`) — no second,
hard-coded copy on the marketing site. Annual pricing (10× monthly, 2 months free)
is shown because it is the same already-verified production billing model
`apps/web/app/pricing` uses — not invented for this plan.

---

## 7. Full verification

- **Backend:** `pytest tests/ -q` — **1162 passed, 3 skipped, 0 failed**
- **Frontend (apps/web):** `npm test -- --run` — **193 passed, 0 failed**; root
  `pnpm check-types`/`pnpm lint`/`pnpm build` — all clean (covers both apps/web and
  apps/marketing via Turbo)
- **Marketing (apps/marketing):** `test:indexability` (9), `test:logo-quality` (1),
  `test:positioning` (4, rewritten — ADR-043), `test:trial-and-demo-contract` (7,
  new) — **21 passed, 0 failed**; `check-types`/`lint`/`build` clean
- **E2E:** `npx playwright test` — **45 passed, 0 failed** (41 pre-existing + 4 new
  Plan 02 journeys, against a real third webServer for apps/marketing)
- **Migration:** single clean head `bfed99c6fa8c`; `alembic upgrade head` is a no-op
  from this branch's own head
- **Repo hygiene:** `git diff --check` clean; no `.env`/secret files in the diff;
  Sprint 039 auth/billing invariants (password policy, email verification, Stripe
  webhook authority, billing-access gate, tenant isolation) untouched — their own
  regression suites pass unmodified

---

## 8. Known limitations

- Plan/period pre-selection isn't threaded through apps/web's signup (see §5).
- No internal demo-request admin/review UI — persistence plus the documented
  `status` lifecycle (`new → contacted → qualified → booked → closed`) is what this
  plan's own scope asked for; a review surface is a later, explicit follow-up.
- `apps/marketing` has no component-rendering test framework (no Vitest/RTL) —
  frontend coverage here follows the app's own established convention (cheap,
  source-text `node --test` contract tests, same pattern as
  `indexability.test.mjs`/`positioning.test.mjs`), backed by real-browser
  Playwright journeys for actual behaviour.
- Responsive quality was verified at 390px via an automated E2E check (no
  horizontal overflow) and CSS Grid's `auto-fit`/`minmax` inherently reflows at
  every width; 820px/1440px were not individually screenshot-audited.
- The CORS/production config note: `apps/marketing`'s production origin needs to be
  present in the deployed API's `CORS_ALLOWED_ORIGINS` for `/pricing` and
  `/request-demo` to work cross-origin in production — an operator/deployment
  config step, not a code change, and out of this plan's "no production changes"
  boundary.

---

## 9. Not deployed, not merged

No Railway deployment was performed, no production database was modified, and this
branch has not been merged to `main`. PR opened against `main`, not merged.
