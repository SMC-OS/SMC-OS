# Sprint 036 — GeoCore Product Experience, Automation Foundation & Responsive Platform

**Status:** Closed — Production Verified
**Branch:** `claude/sprint-036-geocore-product-eoqkqb`
**Baseline:** `3ec7353` (merge of Sprint 035, `main`)
**Merge SHA:** `83fe964424e0208cf499166951290fb3896aa028` (PR #22)

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
| 4 | `test(backend)` | 179 new backend tests (712 → 891); one more added at review (§7.1). |
| 5 | `feat(web)` | Design system, responsive shell, client layer. |
| 6 | `feat(web)` | Dashboard V2, Customers V2, universal quoting UI, Projects V2. |
| 7 | `feat(web)` | Automations, GeoCore AI, Calendar, Settings V2, onboarding. |
| 8 | `test` | E2E coverage (16 → 26 specs) and the fixes the responsive audit surfaced. |

### 7.1 Defects found and fixed during the sprint

Five real defects surfaced while building, testing and reviewing, each
fixed rather than worked around:

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
5. **A stone quote did not fire `quote.created`.** Found reading the diff
   back at the end of the sprint. Dispatch had been wired into the
   routers, and only `POST /api/v1/quotes` (the general builder) called
   it — so `POST /api/v1/quote`, the stone calculator that also backs
   `/estimate` and the AI draft flow, created a quote and announced
   nothing. A builder with a "new quote → chase task" rule would have
   seen it work for extensions and silently not for worktops: no error,
   no failed run, no trace in the run history. Dispatch for `created`,
   `sent` and `approved` now lives in `app/quotes/service.py`, so every
   entry point is covered by construction rather than by whoever
   remembers to add the call at the next route. The regression test fails
   against the commit before the fix. `dispatch_quote_approved`'s
   `actor_user_id` parameter went with it: it was accepted and discarded,
   and a name suggesting per-actor attribution that does not exist is a
   trap for the next reader.

---

## 8. Verification

### 8.1 Automated tests

| Gate | Before | After |
| --- | --- | --- |
| Backend (`pytest`) | 712 passed, 3 skipped | **892 passed, 3 skipped** |
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

### 9.2 Deployment — staging and production, both complete and verified

**This section originally stated Sprint 036 was not deployed, because the
implementation session had no Railway CLI and no Railway credentials —
true at that time (§9.2 history below). A later continuation session had
genuine Railway access (CLI logged in, MCP server authenticated, outbound
network unrestricted) and completed the deployment end to end. That work
is recorded here in place of the original owner-instructions text.**

#### Staging

Deployed from a clean `git archive 83fe964424e0208cf499166951290fb3896aa028`
export (Sprint 021's clean-commit procedure), one service at a time:

| Service | Deployment ID | Result |
| --- | --- | --- |
| `simo-api-staging` | `65bfb324-9a4e-47af-abe3-17d0179eeda3` | ✅ SUCCESS |
| `simo-web-staging` | `b4b5c415-4abf-4033-a473-859e90c95f0d` | ✅ SUCCESS |

Verified after deploy, per the Sprint 020/021 migration-verification rule
(never inferred from `/health` alone):

- `alembic current` on `simo-api-staging` = `d5e6f7a8b9c0`, matching
  `alembic heads` exactly — the sole head at `83fe964`. No drift.
- `/health` → `{"status":"healthy"}` (200); `/ready` → `{"status":"ready","database":"reachable"}` (200).
- PID 1 runs as `uvicorn`, UID/GID `10001` (non-root, per §8/production
  runbook convention) — checked via `/proc/1/status`, not `railway ssh …
  whoami` (Production Runbook §10 explains why that check is wrong).
- `simo-web-staging` security headers present (`strict-transport-security`,
  `x-frame-options: DENY`, `x-content-type-options: nosniff`,
  `content-security-policy: frame-ancestors 'none'`).
- The Sprint 019 22-gate `scripts/staging/smoke.py` run against the fresh
  deploy: **16 PASS / 0 FAIL / 11 BLOCKED** (blocked gates are the ones
  that require extra flags not supplied this run — `--quote-material`/
  `--quote-thickness`, `--allow-restart` — or are explicitly
  owner/manual-only by design, e.g. `backup_restore`,
  `repository_secret_scan`, `follow_up_notification`'s CLI-only trigger.
  Zero failures.).
- A full authenticated UI sweep (fresh synthetic tenant, isolated
  Playwright context per Sprint 021's browser-isolation rule) covering
  every Sprint 036 surface — signup/onboarding, Dashboard V2 (currency
  formatting, quick actions, attention panel, GeoCore AI widget),
  Customers V2, Projects V2, the general-construction quote builder
  (free-text line items, Type/Quantity/Unit/Rate, VAT rate, discount),
  the stone/worktop specialist quote (still at `/quotes/new/stone`, cross
  -linked from the general builder), Automations (template activation —
  "Follow up unanswered quotes" turned on and confirmed persisted),
  GeoCore AI (no terminal/developer language; explicitly states it can't
  create, edit or send anything), Calendar, all six Settings sections
  including Billing & Subscription (real "no plan yet" state, no fake
  Stripe success shown), light mode, dark mode, and the 390/820/1440
  responsive sweep (zero horizontal overflow, no header icon overlap at
  any width, mobile bottom nav + drawer, tablet icon rail, desktop
  sidebar). Screenshots and a JSON pass/fail log were captured for the
  record. One incidental `401` console entry was observed (a
  pre-authentication probe before the token was attached) and is not a
  functional defect — every subsequent authenticated call succeeded.
  **No regressions found.**

#### Production

Investigation before deploying found `simo-api-production`'s `alembic
current` already at `d5e6f7a8b9c0` and both `simo-api-production` and
`simo-web-production` last successfully deployed on 2026-09-05/06 —
hours after the `83fe964` merge and after an earlier session's own
"blocked, not deployed" note. The most likely explanation is that the
owner (or another operator) deployed the merge manually in between agent
sessions. Rather than leave that inferred, the exact clean
`83fe964` archive was redeployed to production directly — safe and
idempotent, since the schema was already at the target head — to convert
an inference into a hard exact-SHA guarantee:

| Service | Deployment ID | Result |
| --- | --- | --- |
| `simo-api-production` | `dd82a1d4-e74a-4726-8e2b-02c7773b39f9` | ✅ SUCCESS |
| `simo-web-production` | `0ace5aef-e38d-4e3d-bd36-890ca0f453bb` | ✅ SUCCESS |

(For the record, the earlier, presumed-manual deploys this superseded
were `simo-api-production` deployment `4551966a-6eee-4b8e-8b5c-ed274795af95`
and `simo-web-production` deployment `6d982487-393b-4019-8346-ceee3cc413f9`,
both now `REMOVED` by Railway in favour of the redeploy above.)

Verified after deploy:

- `alembic current` = `d5e6f7a8b9c0` = `alembic heads`. No drift.
- `/health` and `/ready` both 200, re-checked twice across the session.
- PID 1 non-root, UID `10001`, confirmed the same way as staging.
- Every Sprint 036 route resolves on the live app (`/`, `/login`,
  `/signup`, `/customers`, `/projects`, `/quotes/new`,
  `/quotes/new/stone`, `/automations`, `/ai`, `/calendar`, `/settings` —
  all 200), and the production web build log lists the identical static
  route set staging's build produced, from the identical source archive.
- `geocore.one` (marketing, apex) 200 with `Allow: /` + sitemap;
  `app.geocore.one/robots.txt` still `Disallow: /` (app stays out of
  search, per §11.3 of the Production Runbook).
- **Production-safe verification deliberately stopped short of an
  authenticated click-through.** The Production Runbook is explicit that
  production is not the place to create synthetic test data the way
  staging's smoke script does. Confidence that the authenticated surfaces
  (Dashboard V2, Customers V2, both quote builders, Projects V2,
  Automations, GeoCore AI, Calendar, Settings V2, Billing, light/dark,
  mobile nav) work in production rests on: identical application images
  built from the identical `83fe964` source already fully exercised,
  screenshotted and found regression-free on staging; identical build
  output (the same prerendered route list) on both deploys; and passing
  health/readiness/migration gates on the production database itself.
  This is a deliberate scope boundary, not an oversight.
- **Existing production data.** This deploy replaced only the application
  containers; it never touched `simo-postgres-production` or its volume,
  and the additive-only migrations were already applied (by the earlier,
  presumed-manual deploy) before this session ever connected. No
  destructive operation was run against production at any point in this
  sprint.
- **Tenant/company identity (the Simo Marble & Construction concern).**
  `app/tenants/identity.py` (the `CompanyIdentity` class invoice PDFs
  render from) is **not** in Sprint 036's changed-file list (§8.4 already
  records `tests/test_tenant_identity.py` unchanged and passing). The
  `app/quotes/pdf.py` diff that *was* touched explicitly preserves the
  per-tenant `company.registration_lines` letterhead and goes out of its
  way to keep an existing stone quote's rendering byte-for-byte
  unchanged (see the `_describe_stone_item` docstring in that file). Read
  as code, not re-verified by generating a live production PDF, for the
  same reason as above — no synthetic production data.
- **No regressions found during either deployment.**

**Migration note.** The five migrations run under the existing
`migrate_gate` (ADR-035) with no special handling. They are
additive/widening and take catalogue-only locks; there is no table
rewrite and no expected downtime. `downgrade` on `b3c4d5e6f7a8` will
refuse once a general quote exists — by design (ADR-039).

**Remaining operational limitation.** `follow_up_notification`'s
scan-trigger exercise (`python -m app.jobs.automations`) was not manually
re-run this session — the newly-activated staging automation template had
no matching trigger condition yet (a synthetic tenant created seconds
earlier has no quote nearing expiry), so there is nothing to observe in
its run history yet. This does not block closure: the activation itself
persisted correctly and the underlying job is unchanged from its Sprint
024/027 form, already covered by the automated suite in §8.

#### 9.2 history — original owner-gated note (implementation session)

At the point Sprint 036's implementation was merged, that session
genuinely had no Railway CLI, no Railway credentials, and (separately)
no outbound network path to `api`/`app`/`www.geocore.one` — verified, not
assumed, and left here rather than deleted because it was an accurate
account of that session's environment. It does not describe this
project's actual deployment capability, which the continuation session
above demonstrates.

### 9.3 DNS and domain verification

DNS itself is untouched — Sprint 035's domain cutover is separate and no
dependency on it was discovered or exercised this sprint. What *was*
checked this sprint, as a byproduct of production verification, is
runtime domain health for all three `geocore.one` hosts:

| Check | Result |
| --- | --- |
| `https://geocore.one/` | 200 (marketing apex, not a login redirect) |
| `https://geocore.one/robots.txt` | `Allow: /` + `Sitemap:` line |
| `https://app.geocore.one/robots.txt` | `Disallow: /` (app excluded from search) |
| `https://www.geocore.one/` | 200 |
| `https://api.geocore.one/health`, `/ready` | 200 / 200 |

One deviation from Production Runbook §11.3 is noted for the record, not
fixed here (Sprint 035/034 domain-cutover territory, out of this sprint's
scope): `www.geocore.one` returns `200` with the marketing site's own
`x-nextjs-prerender` headers rather than the documented `301` redirect to
the apex. This predates Sprint 036 — no marketing-service files are in
this sprint's diff (§8) and neither Railway deploy touched
`simo-marketing-production` — so it is recorded as a pre-existing
observation for whoever next touches the domain/marketing configuration,
not a Sprint 036 regression.

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

**Implementation complete, deployed, and verified in both staging and
production (§9.2). Closed.**

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
| Passes existing + new automated tests | ✅ — 892 backend, 149 frontend, 26 E2E |
| Passes CI | ✅ |
| Passes staging | ✅ — deployed `83fe964`, migration head `d5e6f7a8b9c0` confirmed, 16/16 non-blocked smoke gates pass, full authenticated UI sweep clean (§9.2) |
| Deployed and smoke-tested in production | ✅ — deployed `83fe964`, migration head confirmed, health/readiness/route checks clean; authenticated click-through deliberately not performed against production data (§9.2) |
