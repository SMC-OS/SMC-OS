# Sprint 036 — GeoCore Product Experience, Automation Foundation & Responsive Platform

**Status:** In progress
**Branch:** `claude/sprint-036-geocore-product-eoqkqb`
**Baseline:** `3ec7353` (merge of Sprint 035, `main`)

---

## 1. Mission

Turn the production GeoCore MVP into the first genuinely product-grade version of
*"GeoCore — the AI operating system for construction & renovation businesses."*

GeoCore must stop presenting itself as a stone/worktop quoting tool with some CRUD
around it, and start behaving like an operating system for the whole job lifecycle:

```
Lead / Customer → Quote → Follow-up → Approval → Project → Tasks / Schedule → Completion → Review / Aftercare
```

Stone, marble, quartz, granite and worktops stay fully supported as a **specialist
workflow**, but must no longer define the data model, quote system, UI copy,
onboarding, AI or project architecture.

---

## 2. Discovery — what actually exists today

Discovery was performed against the real repository at `3ec7353`, not against
assumptions. Every finding below was verified by reading the code or running it.

### 2.1 Verified green baseline

| Gate | Command | Result at `3ec7353` |
| --- | --- | --- |
| Backend tests | `pytest` (Python 3.12, Postgres 16) | **712 passed, 3 skipped** in 156s |
| Frontend tests | `pnpm --filter web test` | **110 passed** (21 files) |
| Lint | `pnpm lint` | 3/3 tasks pass |
| Type-check | `pnpm check-types` | 3/3 tasks pass |
| Migrations | `alembic upgrade head` | 21 revisions, single head `e2c7b41d9a53` |

Everything below is built on top of a suite that was already green.

### 2.2 Backend architecture (as found)

- FastAPI, SQLAlchemy 2 typed models, Alembic, Postgres. All routes under `/api/v1`
  (ADR-012) except `/` and `/health`.
- **Tenant isolation is real and enforced** (ADR-029): every `crud.*` read/write takes an
  explicit `tenant_id`; cross-tenant lookups 404 rather than 403 (ADR-028 precedent).
- **RBAC** via `require_role(...)` — `Owner` / `Staff`.
- Modules present: `activity`, `appointments`, `assistant`, `auth`, `billing`, `brain`,
  `core`, `customers`, `dashboard`, `documents`, `invitations`, `jobs`, `materials`,
  `messages`, `notifications`, `portal`, `projects`, `quotes`, `tenants`, `users`.
- **No `updated_at` on any domain table** — mutations are recorded through `ActivityLog`.
  This is an explicit repo convention, honoured by everything added this sprint except
  where a row is genuinely edited repeatedly (`automations`).
- **No native Postgres enums** — status-like columns are plain `String`, validated at the
  Pydantic boundary. Honoured.
- **No `relationship()`** except `Quote.items` — FKs are plain columns resolved by
  explicit `crud` lookups. Honoured.

### 2.3 The stone-specific quote model (the central problem)

`quotes` is not a general quote table. Its NOT NULL columns are
`material`, `thickness`, `kitchen_length`, `length_mm` — a quote *cannot physically be
inserted* without stone dimensions. `quote_items` (Sprint 033) is genuinely multi-line,
but every line is a slab: `material`/`thickness`/`length_mm`/`width_mm` NOT NULL, priced
through `QuoteCalculator` → `SlabCalculator` (area ÷ slab area × slab price).

There is **no** notion of a labour line, a unit price, a description-only line, a scope of
works, a site address, a validity date, a discount, or a trade. `POST /api/v1/quote` is
deliberately public (ADR-023) and always runs the slab calculator.

**This is the single biggest blocker to GeoCore being construction software rather than
worktop software**, and Workstream E is the largest change in this sprint.

### 2.4 Customers and projects (as found)

- `customers`: `name`, `email`, `phone`. Nothing else. No address, no company/individual
  distinction, no notes.
- `projects`: `name`, `notes`, `status`, `customer_id`, `quote_id`, `assigned_user_id`.
  No site address, no dates, no type, no value. `ProjectStatus` is a **stone fabrication
  pipeline**: `enquiry → quoted → booked → templated → fabricated → installed → complete`.
  "Templated" and "fabricated" are stone-industry terms that make no sense for a roofing
  or decorating job.

### 2.5 Automation (as found)

There is exactly one automation: `app/notifications/follow_up_service.py` (Sprint 024) —
stale-enquiry follow-up, run by `app/jobs/follow_up.py`. It is a good pattern and this
sprint generalises it rather than replacing it:

- takes an explicit `now`, does no I/O beyond the given session — fully unit-testable;
- idempotent through `NotificationRecord.dedupe_key` (UNIQUE), with the DB constraint as
  a hard backstop behind the pre-check, and `IntegrityError` → rollback → skip;
- resolves a recipient (assigned user → earliest Owner → skip), never crashes.

There is **no** user-visible automation concept, no trigger/condition/action model, no run
history, no enable/disable. There is **no email, SMS or WhatsApp delivery infrastructure
of any kind** — confirmed by reading `requirements.txt`, `app/core/config.py` and every
module. Anything claiming to "send" to a customer would be a lie.

### 2.6 AI (as found)

Two genuinely different things share the word "AI":

1. **`POST /api/v1/process` → `BrainManager`** — a *keyword* router
   (`app/brain/router.py`, an ordered list of substrings) dispatching to
   `SalesAssistant` / `SearchAssistant`. No LLM. Returns raw JSON.
   The `/ai-assistant` page renders `JSON.stringify(response, null, 2)` in a `<pre>` and
   its own body copy names `POST /process`, `BrainManager` and "Sprint 008" — developer
   internals shipped as production UI.
2. **`POST /api/v1/quotes/ai-draft` → `AIDraftService`** — a **real** OpenAI call
   (structured outputs, lazily constructed, `503` when `OPENAI_API_KEY` is unset).
   Extraction only; the schema has no price-shaped field by construction (ADR-024).

So: real LLM infrastructure exists, is optional, and degrades honestly. GeoCore AI can be
built on it truthfully.

### 2.7 Frontend (as found)

- Next.js App Router, Tailwind **v4** (`@theme inline`), `apps/web`.
- **The design system is already fully tokenised.** A repo-wide grep for
  `blue-`, `indigo-`, `sky-` across `app/`, `components/`, `lib/` returns **0 hits**; the
  only blue in the codebase is the value of `--accent`/`--info` in `globals.css`
  (`#2563eb` light, `#3b82f6` dark). Re-palletting is therefore a token change plus
  component polish, not a search-and-replace.
- Navigation is a single flat `NAV_ITEMS` list: Dashboard, Customers, Quotes, Projects,
  AI Assistant, Settings. Sidebar on `lg+`, overlay drawer below. **No tablet treatment
  at all** — 768–1023px gets the phone drawer.
- **Theme/search overlap bug — root cause found.** `Topbar` is
  `flex … justify-between`; the left group is `flex min-w-0 items-center gap-3` but the
  search button inside it is `w-full max-w-xs` with no `min-w-0` on itself and no
  `flex-1` on the group. At 360–412px the intrinsic width of the left group
  (36px menu + 12px gap + up-to-320px search) exceeds the space left by the right-hand
  `shrink-0` control cluster, so the search field renders *under* the theme/notification
  controls. It is a flex-sizing bug, not a z-index or absolute-positioning bug.
- `settings/page.tsx` is one 483-line page rendering five stacked cards, including the
  copy *"There's no email delivery yet — copy the generated link and send it yourself."*
- `signup/page.tsx` placeholders: "Acme Stoneworks", "jane@acmestoneworks.com".
- Currency: `formatCurrencyGBP` is hard-coded to `en-GB`/`GBP` at every call site, and
  `StatGrid` draws its own hand-rolled `GBPIcon` SVG path.
- Upload infrastructure **does** exist (`app/documents/`, multipart, 20MB cap, extension
  allowlist, UUID storage filenames, path-traversal-safe by construction) but is
  customer-scoped. A tenant logo needs its own endpoint; the validation is reusable.
- A **customer portal already exists and works** (`portal_links`, tokenised, revocable,
  quote viewing + invoice PDF + documents + two-way messaging). Workstream L is therefore
  largely a documentation and boundary exercise, not new construction.

### 2.8 Deployment reality

`deploy/railway/*.toml` + `docs/PRODUCTION_RUNBOOK.md` describe a Railway deployment with
a `preDeployCommand` of `runtime_check && alembic upgrade head && alembic current`.
**This session has no Railway CLI and no Railway credentials** (verified: no `railway`
binary, no Railway token in the environment). Staging and production promotion are
therefore owner-gated — see §9.

---

## 3. Sprint 036 contract (locked)

### 3.1 Principles binding every workstream

1. **No fabricated capability.** If the backend cannot do it, the UI does not claim it.
   No fake analytics, no fake email/SMS delivery, no fake calendar sync, no fake Stripe.
2. **No destroyed history.** Every existing quote, customer, project and API response
   stays valid and readable. Widening only: new columns are nullable or carry a
   server default; NOT NULL is only ever *dropped*, never added to an existing column.
3. **Stone is preserved as a specialist workflow**, never deleted, never demoted to a bug.
4. **Tenant isolation and RBAC are invariants**, not features. Every new table carries a
   NOT NULL `tenant_id`; every new query is tenant-filtered; every new route is
   role-gated at least as strictly as its nearest existing neighbour.
5. **Responsive is part of the definition of done**, not a follow-up.
6. **Repo conventions win over personal preference**: plain-String statuses, no native
   enums, `crud`-mediated access, `ActivityLog` instead of `updated_at`, no new runtime
   dependencies without a stated reason.

### 3.2 What ships (committed)

| WS | Deliverable | Ships |
| --- | --- | --- |
| A | 7-area product IA + Settings sections; phone drawer + bottom bar, tablet rail, desktop sidebar | ✅ |
| B | GeoCore palette (forest/sage/cream/champagne), real light mode, Topbar overlap fix | ✅ |
| C | Dashboard V2 command centre over real endpoints only | ✅ |
| D | Customers V2 — address/company/notes + context-rich detail page | ✅ |
| E | **Universal quoting** — general construction quotes + stone preserved as a template | ✅ |
| F | Projects V2 — site address, type, dates, value, description + tasks foundation | ✅ |
| G | Automation engine — triggers/conditions/actions, templates, runs, failure visibility | ✅ |
| H | GeoCore AI — conversational UI, developer language removed, honest capability model | ✅ |
| I | Settings V2 — sectioned; Company / Branding (real logo upload) / Team / Billing / Notifications / Security | ✅ |
| J | Onboarding V2 — neutral copy, trade selection, workspace configuration | ✅ |
| K | Calendar — one aggregated tenant-scoped dated-item feed + month/agenda UI | ✅ |
| L | Customer portal foundation — documented boundary; no new customer-facing claims | ✅ (docs) |
| M | Responsive/a11y verification at 360/390/412/768/820/1024/1280/1440 | ✅ |
| N | Backend + frontend + E2E coverage; full regression suite | ✅ |
| O | Bounded commits, CI green, PR | ✅ |

### 3.3 Explicitly out of scope (with reasons, not silence)

These were evaluated during discovery and deliberately **not** shipped. Each records what
was found, why it cannot ship safely in Sprint 036, the smallest correct prerequisite, and
the proposed follow-up. See §10 for the full write-ups.

1. **Outbound email / SMS / WhatsApp delivery** (invitations, quote sending, review
   requests, customer notifications).
2. **Renaming the stone fabrication pipeline** (`templated`/`fabricated`) to a
   trade-neutral project lifecycle.
3. **External calendar sync** (Google / Microsoft).
4. **A customer-facing portal account system** (portal today is tokenised link-based).
5. **Automation actions that mutate customer-facing state without a human** beyond the
   already-audited approved-quote → project handoff.
6. **Per-user notification delivery preferences** beyond in-app.

---

## 4. Schema changes

Five migrations, all additive or NOT-NULL-dropping. No data is deleted or rewritten.

| Rev | Table(s) | Change |
| --- | --- | --- |
| `f1a2b3c4d5e6` | `customers` | + `customer_type`, `company_name`, `address_line1`, `address_line2`, `city`, `postcode`, `notes` (all nullable / defaulted) |
| `a2b3c4d5e6f7` | `projects` | + `project_type`, `description`, `site_address_line1/2`, `site_city`, `site_postcode`, `start_date`, `target_completion_date`, `estimated_value` |
| `b3c4d5e6f7a8` | `quotes`, `quote_items` | **Universal quoting** — see §4.1 |
| `c4d5e6f7a8b9` | `automations`, `automation_runs`, `tasks` | New tables |
| `d5e6f7a8b9c0` | `tenants` | + `currency`, `trades`, `onboarding_completed_at`, `logo_storage_filename` |

### 4.1 Universal quoting migration (the risky one)

**Added to `quotes`:** `quote_kind` (NOT NULL, server default `'stone'` — every existing
row becomes a stone quote, which is what it is), `title`, `trade`, `site_address_line1`,
`site_address_line2`, `site_city`, `site_postcode`, `scope_of_works`, `notes`,
`exclusions`, `terms`, `valid_until`, `currency` (NOT NULL default `'GBP'`),
`discount_amount`, `vat_rate` (NOT NULL default `0.20`), `subtotal`.

**NOT NULL dropped on `quotes`:** `material`, `thickness`, `kitchen_length`, `length_mm`.
A general quote has no slab. Existing rows keep their values untouched; this is a pure
widening and is reversible in `downgrade()` only because no general quote may exist when
downgrading (the downgrade deletes `quote_kind='general'` rows first — documented in the
migration and never run against production without an owner decision).

**Added to `quote_items`:** `line_kind` (NOT NULL, server default `'stone'`),
`description`, `unit`, `unit_price`.

**NOT NULL dropped on `quote_items`:** `material`, `thickness`, `length_mm`, `width_mm`.

**`quote_items.quantity` widened** `INTEGER → DOUBLE PRECISION`. A stone item is 2 slabs;
a labour line is 2.5 days. Postgres widens in place with no rewrite risk and no precision
loss. JSON output changes from `1` to `1.0`, which is the *same number* to both
`==` in Python and `===` in JavaScript — verified against every existing assertion.

### 4.2 Why `tasks` exists

Workstream G needs "create an internal follow-up/task", Workstream F needs a task
foundation, Workstream C needs "tasks requiring attention" and Workstream K needs dated
items. One `tasks` table serves all four honestly. It carries the same `dedupe_key UNIQUE`
idempotency invariant as `notifications`, so an automation cannot create the same task
twice.

---

## 5. Automation model

```
trigger  →  conditions (all must hold)  →  actions (in order)
```

**Triggers (9).** Event-dispatched, synchronously after commit, inside the request:
`customer.created`, `quote.created`, `quote.sent`, `quote.approved`, `project.created`,
`project.status_changed`, `project.completed`. Scan-evaluated by
`app/jobs/automations.py` (same shape as the existing follow-up job):
`quote.expiring`, `project.starting`.

**Conditions.** `{field, op, value}` with ops `eq|ne|in|gt|gte|lt|lte|contains`, evaluated
against a flat, explicitly-built subject dict — never `getattr` on an ORM row, so no
condition can reach a column the model didn't deliberately expose.

**Actions (4), all internal, none customer-facing:**
`create_notification`, `create_task`, `create_project_from_quote` (delegates to the
already-audited, already-idempotent `quote_service.handoff`), and `draft_message` — which
creates a task carrying a *prepared* message body for a human to review and send. Nothing
in this sprint transmits anything to a customer.

**Idempotency.** Every run computes a `dedupe_key` of
`{automation_id}:{trigger}:{subject_id}[:{discriminator}]`, pre-checked and then enforced
by a UNIQUE constraint on `automation_runs.dedupe_key`. Action side effects carry their
own dedupe keys too, so a partially-failed run cannot double-create on retry.

**Failure visibility.** Every attempt writes an `automation_runs` row with
`succeeded | failed | skipped` and a human-readable detail. A failing automation can never
break the user action that triggered it: dispatch is wrapped so an exception is recorded
as a failed run and swallowed.

**Templates (5), seeded as selectable definitions, never as silently-created rows:**
"Follow up unanswered quotes", "Approved quote → project", "Project starts tomorrow",
"Project completed → prepare review request", "New customer → welcome task".

---

## 6. Currency architecture

`tenants.currency` (NOT NULL, default `'GBP'`) is the single source of truth, mirrored
onto each quote at creation (`quotes.currency`) so a historical document never re-prices
if the tenant later changes currency. The frontend gains
`formatCurrency(value, currency)`; `formatCurrencyGBP` stays as a thin wrapper so no
existing call site breaks. The hand-drawn `GBPIcon` is replaced by a real typographic
currency glyph derived from the active currency, so a future EUR tenant does not see a £.

VAT stays 20% by default and is now a per-quote `vat_rate` column rather than a constant,
which is the same "don't hard-code the UK forever" argument.

---

## 7. Implementation log

_(appended per commit — see §7.1 onwards below)_

## 8. Verification

_(filled in during verification)_

## 9. Delivery

_(filled in during delivery)_

## 10. Known limitations & follow-up sprints

_(filled in at closeout)_
