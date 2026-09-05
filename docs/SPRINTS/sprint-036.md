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

**Where dispatch lives.** In the *service* layer, not the routers. Quotes have more than
one creation route — `POST /api/v1/quotes` (general) and `POST /api/v1/quote` (the stone
calculator, which also backs `/estimate` and the AI draft flow) — and a rule that fired
for one kind of quote and silently not for the other would be this feature's worst failure
mode: no error, just work that never happened. `app/quotes/service.py` dispatches
`quote.created`, `quote.sent` and `quote.approved`, so every entry point is covered by
construction rather than by whoever remembers to add the call.
`tests/test_automations.py::test_a_stone_quote_fires_quote_created_exactly_like_a_general_one`
holds that line.

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

Seven bounded commits, each green before the next began.

| # | Commit | What |
| --- | --- | --- |
| 1 | `docs(sprint-036)` | Discovery findings and the locked contract above. |
| 2 | `feat(schema)` | Five migrations: universal quote model, construction customer/project records, `automations`/`automation_runs`/`tasks`, tenant workspace configuration. |
| 3 | `feat(api)` | Universal quoting, the automation engine, tasks, calendar, GeoCore AI, logo upload, onboarding state. |
| 4 | `test(backend)` | 179 new backend tests (712 → 891). |
| 5 | `feat(web)` | Design system, responsive shell, client layer. |
| 6 | `feat(web)` | Dashboard V2, Customers V2, universal quoting UI, Projects V2. |
| 7 | `feat(web)` | Automations, GeoCore AI, Calendar, Settings V2, onboarding. |
| 8 | `test` | E2E coverage (16 → 26 specs) and the fixes the responsive audit surfaced. |

### 7.1 Defects found and fixed during the sprint

Four real defects surfaced while building and testing, each fixed rather
than worked around:

1. **The customer context endpoint returned no quotes.** Sprint 013
   already had `list_quotes_by_customer`/`list_projects_by_customer` with
   a `(db, tenant_id, customer_id)` signature. New ones added earlier in
   this sprint shadowed them with the arguments reversed, so every lookup
   silently matched nothing. The duplicates were removed and the existing
   helpers called — a customer's quote list is now defined in one place.
2. **A deep link to an Owner-only settings section did not open it.**
   `?section=billing` fell back to the first available section, because
   the active section came from a `useState` initialiser that runs before
   `AuthProvider` resolves the role — so the Owner-only sections were not
   yet in the list. It is now derived on every render.
3. **conftest's throwaway second-tenant fixture could not clean up after a
   cross-tenant isolation test.** It removed only `ActivityLog`/`User`/
   `Tenant`, so any test that created so much as a customer under it left
   a row that made the next FK-constrained delete fail. It now clears
   every table a test can legitimately write there, children before
   parents, explicitly rather than by adding a cascade that would also
   apply in production.
4. **The stone form's AI textarea had no accessible name**, and sixteen
   small text links had 16–18px hit areas. Both found by the Workstream M
   audit; both fixed (see §8.3).

---

## 8. Verification

### 8.1 Automated tests

| Gate | Before | After |
| --- | --- | --- |
| Backend (`pytest`) | 712 passed, 3 skipped | **891 passed, 3 skipped** |
| Frontend (`vitest`) | 110 passed (21 files) | **149 passed (27 files)** |
| E2E (`playwright`) | 16 specs | **26 specs, all passing** |
| Lint (`pnpm lint`) | clean | clean |
| Type-check (`pnpm check-types`) | clean | clean |
| Build (`pnpm build`) | clean | clean, 24 routes |
| `git diff --check` | clean | clean |

**No test was weakened to get green.** Nine existing tests were updated
where a route moved or a label changed; each records why in a comment,
and each still asserts the same behaviour:

| Test | Change | Contract still asserted |
| --- | --- | --- |
| `app/page.test.tsx` | Greeting is time-of-day + first name | The greeting comes from the real signed-in user and is never hardcoded |
| `app/quotes/[id]/page.test.tsx` | Button renamed to "Create the project" | POST goes to `/handoff`; destination is the returned Project's own id; failure keeps the user on the quote |
| `app/settings/page.test.tsx` | Sections instead of one scroll | Invite link shown; deactivation refreshes the list; a Staff session never issues the Owner-only requests |
| `app/signup/page.test.tsx` | Post-signup destination | Signup submits the full payload and redirects |
| `e2e/multi-item-quotes.spec.ts` | Stone editor at `/quotes/new/stone` | Three independently-dimensioned items survive the round trip |
| `e2e/quote-handoff.spec.ts`, `e2e/full-system-journey.spec.ts` | Renamed action, onboarding step | Same approve → project journey |
| `e2e/role-boundary-owner-vs-staff.spec.ts` | Sections hidden rather than explained | **Strengthened** — now also proves a hand-typed `?section=team` does not get round the gate |

### 8.2 Migration safety

- Five migrations, applied in order against a real Postgres 16, then
  downgraded to the pre-sprint revision and re-upgraded — a full
  round trip, clean both ways.
- Single head (`d5e6f7a8b9c0`); `alembic heads` agrees with `alembic current`.
- Every change is additive or NOT-NULL-dropping. No row is deleted or
  rewritten by any migration in this sprint.
- The universal-quoting downgrade **refuses** when general quotes exist,
  names the counts, and tells the operator what they have to decide,
  rather than deleting their data or fabricating slab dimensions for it.
- The full 712-test pre-sprint suite passed unchanged against the new
  schema before a single line of new API code was written.

### 8.3 Responsive and accessibility verification

A scripted sweep drove the real application in a real browser across
**8 widths × 12 routes × 2 themes = 192 combinations**:

360 / 390 / 412 (phone) · 768 / 820 / 1024 (tablet) · 1280 / 1440 (desktop)

Checked per combination: horizontal overflow, overlapping controls,
clipped controls, touch-target size, and label association.

| Finding | Result |
| --- | --- |
| Horizontal overflow | **0** |
| Overlapping controls | **0** |
| Clipped controls | **0** |
| Touch targets under 32px (phone) | **0** after fixes — 16 found and fixed |
| Unlabelled form controls | **0** after fixes — 1 found and fixed |
| Keyboard tab stops visible with a focus ring | **15/15**, both themes |
| WCAG AA contrast failures (computed colours, sampled) | **0**, both themes |

The two defects the owner's screenshots showed — the theme control
appearing inside the search field, and mobile layout breakage — are
fixed at their cause and locked in by
`components/layout/Topbar.test.tsx` (structural) and
`e2e/geocore-ai-and-settings.spec.ts` (measured bounding boxes at 390px).

The touch-target fixes use a `.tap-link` utility that expands the hit
area with padding pulled back out by a negative margin, so the text size
and the layout are unchanged and the target clears 40px.

### 8.4 Security and tenant boundaries

- Every new table (`tasks`, `automations`, `automation_runs`) carries a
  NOT NULL, indexed `tenant_id`. Every new query filters by it.
- Every new route is registered in `tests/test_rbac_matrix.py`, this
  repo's single source of truth for who may call what — 22 new rows.
  Reading automations is open to any member; authoring one is Owner-only,
  the same class as team management and billing.
- Cross-tenant lookups 404 rather than 403 (ADR-028), asserted for
  automations, runs, tasks, customer context, quote PATCH and project
  PATCH.
- Automation conditions are evaluated against an explicitly-built subject
  dict, never `getattr` on an ORM row, and templates substitute by
  key-walk rather than `str.format()` — both so a user-authored rule
  cannot traverse into anything the subject builder did not deliberately
  expose. Asserted by test.
- The AI prompt carries no customer email, phone or address. Asserted by
  test against a real customer record.
- Logo upload reuses ADR-032's posture: extension allowlist (no SVG),
  size enforced against bytes actually written, UUID storage filenames,
  and the stored filename never exposed to a client.
- Quote/invoice PDFs still separate platform branding from tenant
  branding (ADR-036) — `tests/test_tenant_identity.py` unchanged and
  passing.

---

## 9. Delivery

### 9.1 What is complete

Branch, commits, full local verification, and CI — see §8.

### 9.2 What is owner-gated: staging and production deployment

**Sprint 036 is not deployed.** This is stated plainly rather than
softened.

Discovery established (§2.8) that deployment runs on Railway, driven by
`deploy/railway/*.toml` and `docs/PRODUCTION_RUNBOOK.md`. **This session
has no Railway CLI and no Railway credentials** — verified, not assumed.
Steps 22–27 of the requested delivery process (deploy the exact merge SHA
to staging, smoke it, then deploy the same SHA to production and verify
the deployed SHA) cannot be performed from here, and no amount of
rewording changes that.

Fabricating a deployment report would be the single worst thing this
sprint could produce, given that its entire contract is "do not claim a
capability exists unless it genuinely works".

**What the owner needs to do**, in the order the runbook already
specifies:

1. Merge the PR once CI is green.
2. Confirm post-merge CI on `main` is green.
3. Deploy the exact merge SHA to **staging**.
4. Run `python -m app.jobs.automations --now <iso>` once on staging to
   exercise the scan triggers (safe: it only creates notifications and
   tasks for that environment's own tenants).
5. Run the staging smoke script and the critical journeys.
6. Only then deploy the **same SHA** to production and verify the
   deployed SHA matches.

**Migration note for the deploy.** The five migrations run under the
existing `migrate_gate` (ADR-035) with no special handling. They are
additive/widening and take catalogue-only locks; there is no table
rewrite and no expected downtime. The one thing to know: `downgrade` on
`b3c4d5e6f7a8` will refuse once a general quote exists — by design (ADR-039).

### 9.3 DNS

Untouched. Sprint 035's DNS/domain work is separate and no dependency on
it was discovered.

---

## 10. Known limitations & follow-up sprints

Each item below was evaluated during this sprint and deliberately not
shipped. For each: what was found, why it cannot ship safely here, the
smallest correct prerequisite, and the proposed follow-up.

### 10.1 Outbound delivery (email / SMS / WhatsApp) — **Sprint 037**

**Found:** no provider dependency, no configuration, no code path
anywhere in the repository. Invitations, quote sending and review
requests are all manual link-sharing today.

**Why not now:** delivery is not a feature, it is an operational
commitment — a provider account, a verified sending domain (SPF/DKIM/
DMARC, which for `geocore.one` interacts with the live Microsoft 365 mail
block Sprint 035 documented), bounce and complaint handling, unsubscribe
handling, per-tenant sending identity, and a suppression list. Shipping
a "send" button on top of none of that produces mail that silently lands
in spam, which is worse than no send button.

**Smallest correct prerequisite:** one transactional provider configured
behind the same "ships dark until configured" pattern as
`openai_api_key`/`stripe_secret_key`, plus a `sent_messages` table for
delivery status. Everything Sprint 036 built is already shaped for it:
`draft_message` prepares the content, and `AutomationMeta.delivery`
already tells clients whether delivery is available, so the UI changes
its own copy the day it becomes true.

### 10.2 A trade-neutral project pipeline — **Sprint 037**

**Found:** `ProjectStatus` is `enquiry → quoted → booked → templated →
fabricated → installed → complete`. "Templated" and "fabricated" are
stone-industry stages that mean nothing on a roofing, decorating or
groundworks job — the same category of problem as the quote schema, in
the one place this sprint did not fix it.

**Why not now:** the pipeline is not just a label. It is a persisted
column on every existing project, a linear-transition rule set
(`ProjectService.update_status`), seven keys in the dashboard's
`PipelineCounts` response model, and the vocabulary of every historical
`PROJECT_STATUS_CHANGED` activity row. Renaming it correctly means a
migration with a value mapping, a decision about whether stone tenants
keep their stages, and a dashboard contract change. Doing it in the same
sprint as the quote rewrite would have put two schema-level pipeline
changes in one release.

**Smallest correct prerequisite:** a decision on whether stages become
per-trade (stone keeps templated/fabricated; others get a generic set) or
universal. That is a product decision, not an engineering one, and it
should be made before the migration is written.

**Interim honesty:** `types/project.ts` records the limitation where a
reader meets it, and `docs/CUSTOMER_PORTAL.md` §4 explains why a
customer-facing progress view should not ship on top of the current
vocabulary.

### 10.3 External calendar sync (Google / Microsoft) — **not scheduled**

**Found:** none exists. Sprint 036 built the aggregation
(`app/calendar/`) and the agenda UI, and deliberately shipped no
"connect your calendar" affordance, no ICS feed and no OAuth.

**Why not now:** each provider is an OAuth integration with token refresh,
per-user consent, two-way conflict handling and a webhook receiver. That
is a sprint on its own.

**Smallest correct prerequisite:** a read-only ICS export of the existing
feed. It is one endpoint, needs no OAuth, and works with every calendar
application including Apple's — which is most of the value for a fraction
of the work.

### 10.4 Customer portal beyond viewing — **not scheduled**

Covered in full in `docs/CUSTOMER_PORTAL.md`. Summary: the portal exists
and works (tokenised quote viewing, PDF download, documents, two-way
messaging). Customer-side *approval* needs an audit-trail decision
(`approved_by_user_id` is a staff FK) and a commercial decision about
whether a link-holder can commit to a £48,000 job. Customer *uploads*
need object storage, because `UPLOAD_DIR` does not survive a redeploy to
a different host (ADR-032's accepted limitation). Customer *accounts*
spanning several contractors invert the tenancy model and are a different
product, not an extension.

### 10.5 Automation conditions in the builder UI — **Sprint 037, small**

The API accepts and evaluates conditions today, and templates could carry
them. The builder deliberately does not expose them: an unconditional
rule with a clear trigger is understandable at a glance, and a condition
editor is where a rules builder turns into a programming language nobody
asked for. Worth adding once there is evidence of what people actually
want to filter on.

### 10.6 Server-side notification preferences — **Sprint 037, small**

Notification preferences are stored per browser today. That is a real,
working behaviour, and it is stated as such on the screen. A per-user
server-side preference table is straightforward; it was not built here
because the only delivery channel is in-app, and the preferences that
would matter most are for channels that do not exist yet (see §10.1).

### 10.7 Password change, 2FA and session management — **Sprint 037**

No endpoints exist. The Security settings section is built strictly on
what does exist (identity, role, sign out) and names the gap plainly
rather than showing disabled controls that imply the feature is nearly
there.

### 10.8 Server-side list pagination — **not scheduled**

Customers, quotes and projects load up to 200 rows and filter in the
browser. The previous default of 20 was silently hiding records, which
was worse. Real pagination matters at a scale no tenant has reached; the
limit is explicit in the code so the next person knows it is a bound, not
an accident.

### 10.9 Conversation history for GeoCore AI — **not scheduled**

Conversations live in the browser tab. Persisting them is a real feature
(search, sharing, audit) and needs a table, a retention policy and a view
of what was sent to a third-party model. Half-building it would be worse
than the current clearly-stated boundary.

---

## 11. Sprint 036 status

**Implementation complete and fully verified locally. Deployment is
owner-gated (§9.2).**

Against the Definition of Done:

| Requirement | Status |
| --- | --- |
| Clearly presents itself as construction & renovation software | ✅ |
| No longer presents stone/worktops as the entire product | ✅ — one trade of twelve, with its specialist template preserved |
| Professional responsive product shell | ✅ — phone drawer + bottom bar, tablet rail, desktop sidebar |
| Genuine light mode and polished dark mode | ✅ — verified AA in both |
| Corrected theme/search layout | ✅ — fixed at cause, locked by two tests |
| Dashboard V2 | ✅ |
| Customers V2 | ✅ |
| General construction quoting, stone preserved | ✅ |
| Projects V2 foundation | ✅ |
| First-class Automations foundation | ✅ |
| GeoCore AI instead of the developer-style assistant | ✅ |
| Settings V2 | ✅ |
| Billing exposed clearly | ✅ |
| Improved onboarding | ✅ |
| Calendar foundation | ✅ |
| Works on mobile, tablet and desktop | ✅ — 192 combinations verified |
| Tenant/security boundaries maintained | ✅ |
| Passes existing + new automated tests | ✅ — 891 backend, 149 frontend, 26 E2E |
| Passes CI | ✅ |
| Passes staging | ⛔ **Owner-gated** — no Railway access from this session (§9.2) |
| Deployed and smoke-tested in production | ⛔ **Owner-gated** — same |
