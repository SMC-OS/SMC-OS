# Sprint 039 — Communications Experience, AI Drafting & Trade-Neutral Project Pipeline

**Branch:** `sprint-039-communications-ai-pipeline`
**Base:** `origin/main` @ `8e40039` (Sprint 038 production closeout, PR #27)
**Alembic head at branch point (verified, not assumed):** `b2c3d4e5f6a7`
**Status:** CONTRACT LOCKED — implementation in progress

---

## 1. Mission

Turn the communication, AI and automation foundations Sprints 036–038 built into a
polished end-to-end operating workflow, and make the core project experience genuinely
trade-neutral.

GeoCore remains **"the AI operating system for construction & renovation businesses."**

Sprint 038 closed with two phases explicitly deferred rather than dropped
(`docs/SPRINTS/sprint-038.md` §9, §15):

> Phase 4 (history UI, notification preferences, AI drafting) and Phase 5
> (trade-neutral pipeline) remain explicitly out of scope for this closeout —
> recorded in §9 as deliberate follow-up work, not silently dropped.

Sprint 039 is that follow-up, plus the automation UX gap Sprint 038's backend work
opened (§2.5 below).

---

## 2. Discovery — what actually exists today

Performed against `origin/main` @ `8e40039` before any code was written. Every
statement below was read out of the tree, not recalled.

### 2.1 Communications (Sprint 038) — backend complete, frontend absent

| Thing | Where | State |
|---|---|---|
| `Communication` ORM row | `app/database/models.py:911` | Built, production-verified |
| `EmailSuppression`, `ProcessedEmailEvent` | `app/database/models.py:1018`, `:1053` | Built |
| `DeliveryService` (send/retry/suppress/webhook) | `app/communications/service.py` | Built |
| `GET /api/v1/communications` (filterable history) | `app/communications/router.py:33` | Built since Phase 1 |
| `POST /api/v1/communications/webhook` (Svix-verified) | `app/communications/router.py:56` | Built, verified in production |
| `POST /api/v1/quotes/{id}/send-email` | `app/quotes/router.py:265` | Built |
| **Any frontend communications code** | `apps/web/` | **None.** Searching `apps/web/lib/api.ts` for "communication" returns zero hits |
| **Quote detail send button** | `apps/web/app/quotes/[id]/page.tsx:212` | Still calls `api.sendQuote` → `POST /quotes/{id}/send`, the endpoint whose own docstring says *"This transmits NOTHING"* |

So the real gap is not the ledger — it is that **no user can see it, and the product's
own send button does not use the delivery path Sprint 038 shipped.**

### 2.2 Communication states — what a provider can actually establish

`CommunicationStatus` (`app/communications/models.py:19`):
`draft | queued | sending | sent | delivered | failed | bounced | suppressed`.

**There is no `complained` status, and adding one would be wrong.** A complaint means
the message *did* reach the inbox; Sprint 038 deliberately leaves the row's status
alone and records the complaint as an `EmailSuppression` with `reason="complaint"` and
`source_communication_id` pointing back at the row
(`app/communications/service.py`, the `_COMPLAINED_EVENTS` branch). That is
production-verified behaviour and this sprint preserves it exactly — see §4 Decision 1
for how "complained" is nevertheless surfaced to users.

### 2.3 Notification preferences — client-only mock

`apps/web/components/settings/NotificationsCard.tsx` stores four preference keys in
`localStorage` and says so honestly in its own docstring:

> a per-user server-side preference table is genuine follow-up work (see
> `docs/SPRINTS/sprint-036.md` §10), and shipping a server-backed setting that nothing
> reads would be worse than shipping a local one that something does.

There is **no** preferences table, model, service or endpoint in `app/notifications/`.
The card's banner copy — *"It doesn't send email, SMS or push notifications yet"* — has
been false since Sprint 038 shipped.

### 2.4 GeoCore AI — read-only, and its prompt is now stale

`app/ai/service.py` has no tools and cannot write; `app/ai/context.py` builds a
bounded, tenant-scoped, PII-free summary (counts and titles only, explicitly no emails,
phones, addresses or message bodies).

`_SYSTEM_PROMPT` currently instructs the model:

> "You cannot take actions... and GeoCore cannot send email, SMS or messages to
> customers."

Also false since Sprint 038. `app/quotes/ai_draft.py` is the established precedent for
a *bounded* LLM feature in this codebase: structured outputs, lazy client construction,
server-side re-validation of everything the model produced, and a schema that makes the
dangerous output shape structurally impossible.

### 2.5 Automation UX — the backend moved, the UI did not

Sprint 038 added the first customer-facing action and served the distinction from the
API (`app/automations/router.py`'s `/meta` returns `customer_facing_actions`), but:

- `apps/web/types/automation.ts`'s `ACTION_LABELS` has **four** entries; the backend
  has **five** `ACTION_TYPES`. `send_quote_follow_up` renders with no label.
- `AutomationMeta` (TS) has no `customer_facing_actions` field, so the UI cannot
  distinguish an internal action from one that reaches a customer's inbox.
- That file's own header still asserts *"GeoCore has no outbound email, SMS or
  messaging infrastructure, so nothing here contacts a customer."*

### 2.6 Project pipeline — stone-shaped, and known to be

`ProjectStatus` (`app/projects/models.py:10`):
`enquiry → quoted → booked → templated → fabricated → installed → complete`.

`templated` and `fabricated` are stone-industry stages. `ProjectService.update_status`
enforces a **strictly linear** walk (`_STATUS_SEQUENCE`, only the exact next value is
accepted), `complete` is terminal, and there is no hold or cancel state at all.

`apps/web/types/project.ts` already carries the note:

> "templated" and "fabricated" are stone-industry stages and make no sense for a
> roofing or decorating job. Renaming the pipeline... is real work — it touches the
> status column, the linear-transition rules, every existing project's history and the
> dashboard — and it is deliberately deferred rather than half-done here.

**Full backend blast radius (enumerated, not estimated):**

| File | Coupling |
|---|---|
| `app/projects/models.py` | `ProjectStatus` enum, `ProjectStatusUpdate` |
| `app/projects/service.py` | `_STATUS_SEQUENCE`, `update_status`, `convert_to_customer`'s enquiry gate |
| `app/projects/router.py` | status endpoint, "Only enquiry projects can be converted" |
| `app/dashboard/models.py:9-14` | `PipelineCounts` — **seven hardcoded keys**, one per stone stage |
| `app/dashboard/service.py:30` | iterates `ProjectStatus` to build those counts |
| `app/quotes/service.py:153` | `handoff()` creates the project at `BOOKED` |
| `app/notifications/follow_up_service.py:44` | scans `ProjectStatus.ENQUIRY` for stale enquiries |
| `app/ai/context.py:44` | groups projects by raw status string |
| `app/automations/subjects.py` | `project_subject` exposes raw `status`/`previous_status` to rule authors |

**Frontend:** `apps/web/types/project.ts`, `apps/web/lib/projects.ts`,
`apps/web/types/command-centre.ts`,
`apps/web/components/dashboard/command-centre/CommandCentrePanel.tsx`,
`apps/web/app/projects/[id]/page.tsx`, plus E2E specs
`project-operations.spec.ts`, `business-command-centre.spec.ts`, `quote-handoff.spec.ts`.

### 2.7 Sprint number and branch availability

No branch, worktree, tracked file or pull request referencing 039 exists. The highest
merged PR is #27 (Sprint 038 closeout). **039 is unclaimed.**

### 2.8 Boundaries confirmed with the sibling sprint

`sprint-037-commercial-security-ai` exists as a branch **and** a separate worktree at
`../SMC-OS-sprint-037` @ `dd07d3e`. It is not read, modified, rebased, merged,
cherry-picked from or deleted by this sprint. There is no `docs/SPRINTS/sprint-037.md`
on `main` — Sprint 037 is open and reconciles separately.

The locked future RBAC model (Owner → Admin → Member, with last-owner protection and
ownership transfer) belongs to Sprint 037. Sprint 039 **must not** implement or
interfere with it. Today's model is `UserRole.OWNER | STAFF` and Sprint 039 uses it
exactly as-is: every new Owner-only surface uses the existing
`require_role(UserRole.OWNER)` dependency and adds no new role, no new role-check shape,
and no migration touching `users.role`.

---

## 3. Locked contract

### A — Communications Centre
1. Communication history is surfaced from the **Customer**, **Quote** and **Project**
   experiences, plus a central `/communications` view. The read API
   (`GET /api/v1/communications`) already supports every filter this needs; the central
   view adds an unfiltered tenant-scoped listing.
2. Each entry shows recipient, message type, related entity, delivery state, timestamps,
   attempt count, and — where present — a user-appropriate failure reason.
3. All real Sprint 038 states are represented: `queued`, `sending`, `sent`, `delivered`,
   `failed`, `bounced`, `suppressed`, plus **complained** (derived — §4 Decision 1).
4. **No provider internals ever cross the API boundary.** `CommunicationOut` already
   excludes `body_html`/`body_text`/`provider_message_id`/`sender_identity`, and
   `failure_detail` is sanitised at write time. That contract is preserved, not widened.
5. A failed communication with a retryable `failure_category` can be retried by a user;
   retry reuses `DeliveryService.retry()` (same row, same `dedupe_key`) — it never
   creates a second row and never re-sends a delivered message.

### B — Server-side notification preferences
1. A real per-user, per-tenant preferences table replaces the `localStorage` mock.
2. Categories: quote activity, project activity, task assignment, automation outcomes,
   communication failures.
3. Channels: **in-app** and **email**. No SMS or push toggle is offered, because
   neither exists — the Sprint 036 honesty rule holds.
4. **Enforcement is server-side**, at the point notifications are created
   (`app/notifications/`), not by hiding rows in the client.
5. Defaults are opt-in for every category (matching today's `DEFAULTS` in the card), so
   no existing user's experience silently changes.
6. The stale "GeoCore doesn't send email" banner is corrected.

### C — GeoCore AI drafting
1. New capability: draft a contextual customer communication. Supported kinds —
   quote delivery, quote follow-up, project update, appointment/scheduling update,
   payment reminder, general customer message.
2. **Grounded only in tenant-authorised GeoCore data.** The draft context builder is
   tenant-scoped by construction, exactly like `app/ai/context.py`, and every entity it
   reads is re-fetched with the caller's `tenant_id`. A draft request naming an entity
   the caller's tenant does not own returns 404, never a cross-tenant read.
3. **AI never sends.** The drafting endpoint returns text. It has no delivery call, no
   `DeliveryService` import, and no side effect on any record.
4. Sending requires an explicit human action on a reviewed body, and goes through
   **Sprint 038's `DeliveryService` and the existing communications ledger**. No second
   email/delivery architecture is created.
5. Rewrite / shorten / adjust-tone operate on a supplied draft and are subject to the
   same rules.
6. With no LLM configured the feature reports itself unavailable honestly via
   `AICapabilities` — it does not fall back to a fabricated draft.
7. `_SYSTEM_PROMPT` is corrected to reflect that GeoCore can now email customers, and
   that the assistant still may not send anything itself.

### D — Trade-neutral project pipeline V2
1. The trade-neutral vocabulary is a set of **semantic stage roles**:
   `lead → quoted → approved → scheduled → in_progress → completed`,
   with `on_hold` and `cancelled` as universal side-states.
2. Every consumer (Dashboard, Projects, Quotes, Customers, Tasks, Calendar,
   Automations, AI context) interprets **roles**, never raw stage keys.
3. A tenant's actual stages are **configuration**, seeded from a named template.
   `standard` (trade-neutral, stage key == role key) is the default for new tenants.
   `stone` is a specialist template that keeps `templated`/`fabricated`/`installed`.
4. Stone/worktop workflows remain fully supported — as a template, not as GeoCore's core
   identity.
5. Transitions become **graph-based**, not strictly linear: forward along the active
   stage order, plus hold/resume and cancel from any non-terminal stage.
6. **No existing project's `status` value is rewritten by the migration** — see
   §4 Decision 2.

### E — Automation UX
1. Each action is labelled with what it actually does, and classified visibly as
   *internal notification*, *internal task*, *customer communication*, or
   *AI-generated draft*. The classification is served from the backend, extending the
   existing `/automations/meta` `customer_facing_actions`.
2. Before enabling an automation a user sees: its trigger, its conditions, every action
   in plain language, and — for a customer-facing action — an explicit confirmation that
   real email will be sent to real customers.
3. Run history and outcomes are surfaced per automation (the `AutomationRunsPanel`
   already exists; it gains outcome detail and communication linkage).
4. **Idempotency, retry and suppression behaviour from Sprint 038 are preserved
   unchanged.** No dedupe key derivation is altered.

### F — Responsive product polish
1. Everything introduced or materially changed works at **390px / 820px / 1440px**.
2. GeoCore's production design system and the tenant-vs-platform branding separation
   are preserved. No new colour tokens, no new type scale.
3. Loading, empty, error, disabled, permission-denied and success states are built and
   verified — not just happy paths.

### G — Required E2E journeys
1. `Customer → Quote → AI Draft → Human Review → Send → Communications History → Delivered`
2. `Project → Status Transition → Automation Trigger → Task / Notification / Communication Outcome`

Both run against the real FastAPI app and real Postgres via the existing Playwright
harness (`apps/web/playwright.config.ts` boots `app.main:app` plus the Next.js dev
server). **No external provider interaction is faked and then reported as real.** Where
a journey needs a delivery outcome the provider would supply, the test drives the real
signature-verified webhook endpoint with a locally-signed payload and says so — it does
not claim Resend sent anything.

### Explicitly out of scope
- Sprint 037's RBAC migration (Owner → Admin → Member, last-owner protection,
  ownership transfer) — locked, and not this sprint's to build or disturb.
- Password recovery (Sprint 038 §9 assigned it to Sprint 037).
- Open/click analytics. Sprint 038 declined `email.opened`/`email.clicked` as a separate
  product decision; that stands.
- Inbound email / reply threading.
- SMS, push, or any second delivery channel.
- Persisted AI conversation history (Sprint 036's stated v1 boundary).

---

## 4. Decisions

### Decision 1 — "Complained" is derived, never a status

**Locked:** `CommunicationStatus` gains no `complained` member. The API exposes a
`complained: bool` on the read model, derived from an `EmailSuppression` row with
`reason="complaint"` whose `source_communication_id` is this communication.

**Why:** a complaint is proof of *delivery*, not of failure — overwriting a `delivered`
row with `complained` would destroy the one fact the row exists to record, and would
change behaviour that has been verified in production. Deriving it is additive, exposes
the same truth, and leaves Sprint 038's webhook handler untouched.

### Decision 2 — The pipeline migration rewrites zero project rows

**Locked:** the migration creates per-tenant pipeline stage configuration. Every
**existing** tenant is seeded with a pipeline whose stage keys are *exactly* today's
seven values, each annotated with its semantic role:

| Legacy stage | Role |
|---|---|
| `enquiry` | `lead` |
| `quoted` | `quoted` |
| `booked` | `approved` |
| `templated` | `in_progress` |
| `fabricated` | `in_progress` |
| `installed` | `in_progress` |
| `complete` | `completed` |

`on_hold` and `cancelled` are appended to every pipeline as side-states.

**Consequences, stated plainly:**
- `UPDATE projects SET status = ...` never runs. No in-flight job changes stage, no
  history is reinterpreted, and the downgrade is a pure table drop.
- The product becomes trade-neutral **immediately** anyway, because Dashboard,
  automations, AI and Calendar switch to counting and reasoning by *role*.
- New tenants get the `standard` trade-neutral pipeline, so `enquiry`/`templated`/
  `fabricated` stop being GeoCore's default vocabulary from this sprint onward.
- An existing tenant that wants the neutral vocabulary switches template through an
  explicit, previewed, Owner-only action — a user decision with a visible mapping, not a
  silent overnight rewrite of their jobs.

**Owner note:** this is the one architectural call in Sprint 039 that a reasonable
person could make differently — the alternative is a hard `UPDATE` remapping every
existing project onto the neutral seven. That was rejected as unnecessary data risk for
zero product benefit, given the role layer delivers trade-neutrality without it. It is
also fully reversible: a later sprint can add the bulk remap as its own migration, and
nothing here forecloses it.

### Decision 3 — `PipelineCounts` becomes role-keyed

`app/dashboard/models.py`'s seven stone-named integer fields are replaced with the
eight role keys. This is a **breaking API-shape change** to
`GET /api/v1/dashboard/command-centre`, made deliberately and in one place, with the
frontend contract type (`apps/web/types/command-centre.ts`) and its tests changed in the
same commit. There is no external consumer of this endpoint — it is read only by
`CommandCentrePanel`.

### Decision 4 — AI drafting reuses `ai_draft.py`'s trust posture, not `chat`'s

Drafting is a *generation* feature, not a conversation. It follows
`app/quotes/ai_draft.py`: bounded input, lazy client, no tool access, and — critically —
a return shape with **no delivery field of any kind**, so "the AI sent it" is
structurally impossible rather than merely prohibited by instruction.

### Decision 5 — Transitions become graph-based, and `convert_to_customer` keys off role

`ProjectService.update_status`'s strict `_STATUS_SEQUENCE` walk cannot express hold,
resume or cancel. It is replaced by a stage-graph check driven by the tenant's pipeline:
forward one active stage, or into/out of `on_hold`, or into `cancelled`, from any
non-terminal stage. `convert_to_customer`'s gate changes from `status == "enquiry"` to
`role == "lead"`, preserving its meaning across both templates.

---

## 5. Migration plan

Two migrations, applied in sequence, both linear from the **verified** head
`b2c3d4e5f6a7`. One per phase rather than one combined migration, so no phase ships a
table nothing yet reads:

- **`c5d6e7f8a9b0`** (Phase 1, built) — `pipeline_stages`, tenant-scoped stage
  configuration (key, label, role, position, `template_key`).
- Phase 3 — `notification_preferences`, per-user, per-tenant, per-category channel
  flags.

Both are new tables. No column on an existing table is altered, dropped or retyped, and
no existing row's data is rewritten. Each downgrade drops its own table and is
genuinely safe.

### 5.1 Decision 6 — `pipeline_stages.tenant_id` cascades, alone in this schema

Every other tenant FK in this schema deliberately **blocks** a tenant delete, because
those tables hold business records (quotes, projects, customers, communications) and the
constraint exists so nobody removes them by accident. `pipeline_stages` holds none: a
stage row is regenerable configuration, and deleting every one of them leaves
`pipeline_config.resolve()` returning the default template unchanged.

Discovered concretely: adding the table with the schema's usual blocking FK broke **87
tests** across 17 different cleanup helpers, each of which deletes a throwaway tenant.
Patching all 17 would have preserved a safety property that protects nothing here, and
obliged every future test author to know this table exists. `ON DELETE CASCADE` is the
honest answer, and it is documented on the model itself so the exception cannot be
mistaken for an oversight.

---

## 6. Phased delivery

| Phase | Scope |
|---|---|
| **1** | Migration plus pipeline domain (roles, templates, stage config, graph transitions), all consumers switched to roles, `PipelineCounts` reshaped. Backend, frontend contract types, tests. |
| **2** | Communications Centre — API additions (central listing, derived `complained`, user-initiated retry), frontend client, central view, and the Customer/Quote/Project timelines. Quote detail switched to the real `send-email` path. |
| **3** | Server-side notification preferences — table, service, enforcement at creation, settings UI replacing the mock. |
| **4** | GeoCore AI drafting — draft/rewrite/shorten/tone endpoints, review-and-send UI wired to `DeliveryService`, `_SYSTEM_PROMPT` corrected. |
| **5** | Automation UX — action classification, pre-enable clarity, run outcomes. |
| **6** | Responsive sweep at 390/820/1440, state audit, both required E2E journeys, full regression. |

Phases land as coherent, separately reviewable commits on one branch, opened as one or
more PRs requiring green CI.

---

## 7. Evidence rules for this sprint

Restating Sprint 038's own standard, because this sprint inherits its provider
integration:

- No feature, test, CI result, provider interaction or deployment is claimed without
  actual evidence in this document.
- No secret value is requested, printed, logged or committed.
- Staging verification is performed against the **exact merged SHA**.
- **Production deployment is gated on explicit owner approval and does not happen
  without it.**

---

## 8. What Phase 1 actually built

**Trade-neutral project pipeline V2 — complete, backend and frontend.**

### Backend
- `app/projects/pipeline.py` — the pure domain: eight roles, two named templates
  (`standard`, `stone`), and the transition graph. No database, no I/O.
- `app/projects/pipeline_config.py` — resolution (falling back to `standard` for a
  tenant with no rows), idempotent seeding, `plan_template_change` (pure, previewable)
  and `apply_template` (the one place that rewrites `projects.status`, and only on an
  explicit request).
- `PipelineStage` ORM model + migration `c5d6e7f8a9b0`, seeding every pre-existing
  tenant with the legacy stone stages. **Verified: `alembic downgrade`/`upgrade`
  round-trips cleanly.**
- `ProjectService` — graph transitions replace the linear walk; `create` opens at the
  tenant's own first stage; `convert_to_customer` gates on the `lead` role.
- `GET /api/v1/projects/meta/pipeline` — the tenant's stages and each one's
  `allowed_transitions`, served so no client can offer a move the engine would refuse.
- `ProjectOut.status_role` — the neutral meaning alongside the tenant-specific key,
  attached through one shared helper (`pipeline_config.attach_role`) used by both
  `app/projects` and `app/quotes`'s handoff.
- Every consumer switched to roles: dashboard `PipelineCounts` (now eight role keys),
  quote handoff, the stale-lead scan (`crud.list_projects_in_role`, a per-tenant join
  rather than one shared literal), GeoCore AI's workspace context, the automation
  dispatcher's "project completed" trigger, the automation scan's terminal check, and
  the customer context panel's open-project count — which, as a side effect of being
  expressed as roles, stopped counting cancelled jobs as open.
- Portal and customer-context payloads carry `status_label`/`status_role` resolved
  server-side (the portal has no session and cannot fetch a pipeline itself).

### Frontend
- `types/project.ts` — no hardcoded status list at all any more; `PipelineRole` plus a
  fetched `PipelineStage[]`.
- `lib/projects.ts` — tone by role, label from the stage the tenant configured.
- Projects list: stage filters are the tenant's own stages; "Live" now excludes
  cancelled work as well as completed, which the old `status !== "complete"` check could
  not express.
- Project detail: the single "Advance to X" button became the real graph — forward
  moves, plus put-on-hold and cancel as visually distinct secondary actions, plus a
  resume picker when a job is on hold. Terminal and permission-denied states are stated
  rather than rendered as an empty space.

### Evidence
| Check | Result |
|---|---|
| Backend suite, baseline before any change | **959 passed, 1 skipped** (18m54s) |
| Backend suite, after Phase 1 | **1005 passed, 1 skipped, exit 0** (13m44s) |
| `alembic downgrade -1` then `upgrade head` | clean both ways |
| `pnpm lint` (web, marketing, @repo/ui) | 3 successful, 0 warnings |
| `pnpm --filter web check-types` | clean |

**Pre-existing local flakiness, not caused by this sprint:** on this Windows
development machine `app/quotes/new/stone/page.test.tsx`,
`components/quotes/GeneralQuoteBuilder.test.tsx` and
`app/projects/[id]/page.test.tsx` intermittently fail with
`Test timed out in 5000ms`, and the failure count varies between identical runs.
Verified by running the same files against **pristine `origin/main`** in the other
worktree, where they flake identically. CI is the arbiter for these.

---

## 9. What Phase 2 actually built

**Communications Centre (Workstream A) — and a send button that sends.**

The discovery finding that mattered most: the quote page's send button called
`POST /quotes/{id}/send`, the endpoint whose own docstring says *"This transmits
NOTHING"*. Sprint 038's real delivery path existed and nothing in the product used it.

### Backend
- `GET /communications` gains `offset` paging and a **stable secondary sort**. Two
  communications written in one transaction share a `created_at`, and an unstable order
  makes offset paging drop or repeat rows between pages.
- `CommunicationOut` gains two derived, never-stored fields:
  `complained` (read from the complaint's `EmailSuppression`, one query per page rather
  than one per row) and `retryable`.
- `POST /communications/{id}/retry` — tenant-scoped via a new
  `crud.get_communication_by_id`, delegating to the same `DeliveryService.retry()` the
  scheduled sweep uses. It **cannot** create a second row, re-send a delivered message
  or push past a suppression — not because the route checks, but because the path
  underneath it never could. A non-retryable message is refused with 409 rather than
  silently no-opping.

### Frontend
- A Communications entry in the primary nav, and **one** `CommunicationTimeline`
  component behind five screens (central view, customer, quote, project, invitations) —
  they differ only by which filter they pass.
- The vocabulary problem solved once, in `lib/communications.ts`: `queued`,
  `suppressed` and `unavailable` are the right words for a database and the wrong ones
  for someone running a building firm at 8am. Each maps to plain English plus, where a
  failure is actionable, what to do about it — without softening what happened.
- **"Sent" is never rendered as "arrived."** The card on the Communications page says
  so explicitly, and `STATUS_TONE` gives `sent` an `info` tone rather than `success`.
- The quote page's primary action is now **Email to customer**, through
  `DeliveryService`. "Mark as sent" stays beside it, because a business that posts the
  PDF or hands it over on site still needs to record that it went.

### One honest limitation, recorded rather than papered over
Retrying over HTTP runs through the *application's own* configured provider. In an
environment with no `RESEND_API_KEY` that is a truthful `failed`/`unavailable` outcome,
not a send. The test suite asserts exactly that, and proves a *successful* retry reaches
`sent` separately at the service level against an injected provider — because nothing in
this sprint may imply a provider accepted a message when no provider was called.

---

## 10. What Phase 3 actually built

**Server-side notification preferences (Workstream B).**

Sprint 036 shipped this screen as four `localStorage` keys and said so in its own
docstring. The replacement had to be more than a table:

- `notification_preferences` (migration `d6e7f8a9b0c1`) — per user, per tenant, per
  category. **Nothing is backfilled.** A user with no row gets in-app on / email off,
  which is exactly today's behaviour, so the upgrade changes nobody's experience and
  starts no unexpected email.
- **Enforcement is at the write path, not the render path.** A muted notification is
  never created. The old version created the row and hid it, which left the unread count
  still counting it and any second client still showing it.
- Three rules, each a test: defaults preserve today's behaviour; a tenant-wide broadcast
  has no addressee so no preference applies; an unrecognised category **fails open**,
  because silence is the one thing a notification system must not produce by accident.

### The honesty rule, applied to the category list
A preference that controls nothing is a mock with a database table behind it. So each
of the six categories had to name something GeoCore genuinely produces — and three of
them did not yet, so Phase 3 built them:

| Category | What now produces it |
|---|---|
| `quote_activity` / `project_activity` / `customer_activity` | automation notifications, routed through the preference gate; the stale-lead follow-up scan |
| `task_assignment` | **new** — an automated task now notifies the person whose name is on it. Sprint 036's card already promised this ("when something an automation created is waiting on you") and nothing produced it |
| `automation_outcome` | **new** — `app/notifications/automation_alerts.py`. Sprint 036 built `AutomationRun` because "an automation that quietly stopped working is the failure mode this feature has to defend against", then made that failure visible only in a panel nobody opens until they already suspect a problem. Deduped per rule per day, so a week-long breakage is one unread item, not four hundred |
| `communication_failure` | **new** — `app/notifications/delivery_alerts.py`. Sprint 038 recorded delivery failures faithfully and told nobody; a bounced quote looks exactly like a quote the customer is still thinking about |

Muting a task notification still creates the task. The notification is a courtesy; the
task is the record of what has to happen.

### The email channel
Real, through Sprint 038's `DeliveryService` and a new `WORKSPACE_ALERT` message type —
the first template in `app/communications/templates.py` addressed to a colleague rather
than a customer, and it says so. **Off by default for every category**, so no upgrade
ever starts mailing a person. Sent only after the in-app record exists, and never able
to break the automation that triggered it.

---

## 11. What Phase 4 actually built

**GeoCore AI drafting (Workstream C) — and the human gate in front of it.**

### "AI never sends" is structural, not a promise
`app/ai/drafting.py` has **no delivery import**, and `DraftResult` has no field that
could hold a delivery outcome — no `sent`, no `recipient`, no `communication_id`, no
`status`. A response shape with nowhere to put "sent" cannot claim to have sent
anything, which is a far stronger guarantee than a system prompt asking a model not to.
Two tests enforce it: one asserts the exact field set, the other parses the module's
real import graph (deliberately not its source text, so the docstring explaining *why*
it cannot send does not fail the test proving it cannot).

### Authorisation before capability
The first version checked "is an AI provider configured?" before resolving the entities
a draft is about — which meant a cross-tenant id returned 503 instead of 404 in an
unconfigured environment. That is backwards: whether this workspace has AI connected has
no bearing on whether the caller may see a record. **Tenant resolution now runs first**,
so an id belonging to another tenant answers 404 either way, and is never read.

### The human gate
`MessageComposer` is where review actually happens. There is deliberately **no "draft
and send" shortcut**: the moment one exists, review becomes optional and a model's guess
about a date or a price is in a customer's inbox. Sending posts the text that is on
screen — including every edit the reviewer made — to
`POST /communications/send`, which:

- **has no recipient field.** The address is resolved from a `Customer` row the caller's
  tenant owns. That is the property stopping this being a general-purpose mailer wearing
  a CRM's clothes.
- goes through Sprint 038's `DeliveryService` into the same ledger as every other send.
- takes an idempotency key the composer generates on the first Send press, so a
  double-click resolves to the same communication.

`_SYSTEM_PROMPT` was also corrected: it told users "GeoCore cannot send email, SMS or
messages to customers", which had been false since Sprint 038 shipped.

---

## 12. What Phase 5 actually built

**Automation UX (Workstream E) — by taking the descriptions away from the frontend.**

The concrete bug: `apps/web/types/automation.ts` had a hardcoded map of four action
labels for five action types, so Sprint 038's `send_quote_follow_up` — the one action
that emails a real customer — rendered with **no label at all**. The same file's header
still asserted that nothing in automations contacts a customer.

Adding a fifth label would have fixed the symptom. Instead the backend now serves an
`action_catalogue`: each action's label, description, and which of four classes it
belongs to (`internal_notification`, `internal_task`, `customer_communication`,
`ai_draft`). A UI that is *served* the catalogue cannot describe an action wrongly,
because it no longer describes actions.

`CUSTOMER_FACING_ACTION_TYPES` is now **derived** from that catalogue rather than
maintained beside it — two sources of the same truth eventually disagree, and the
direction this one would fail in is "sends email nobody expected".

The `ai_draft` class needed something real to name, so Phase 5 added
`draft_message_with_ai`: GeoCore AI drafts from the triggering record and leaves the
result in a task for a person to review and send. Internal, not customer-facing — which
`tests/test_automations.py`'s existing action-set lock forced us to state deliberately,
exactly as that test was designed to.

In the builder, choosing an action now shows what it does *before* the rule is saved,
and a customer-facing action gets the loudest treatment on the screen.

---

## 13. Status

**PHASES 1–5 COMPLETE.** Contract locked; discovery recorded; branch and worktree
created from `origin/main` @ `8e40039`; Alembic head verified as `b2c3d4e5f6a7` and
extended linearly to `c5d6e7f8a9b0` → `d6e7f8a9b0c1`, both round-tripped. Phase 6
(responsive sweep, state audit, the two required E2E journeys, full regression) in
progress.

---

## 14. Production Readiness Defect Gate

The product owner paused this sprint's production path on discovering seven
real, user-facing defects independent of this sprint's own scope (Communications
Centre, notification preferences, AI drafting, trade-neutral pipeline). This
sprint's own CI has also never been green (every one of its 4 pushes — Phases
1 through 4+5 — failed on a frontend `check-types` error, unrelated to the
gate below), so it was not eligible for production regardless.

Reproduction against `origin/main` @ `8e40039`, this sprint's own branch, and (as
reference only, never merged) the abandoned `sprint-037-commercial-security-ai`
worktree confirmed all seven as real and pre-existing (not caused by this
sprint), each closed on its own branch off `origin/main` per the product
owner's explicit phased-sequencing decision (mirroring Sprint 037's own
phase-per-PR precedent):

| # | Blocker | Root cause | Branch |
|---|---|---|---|
| 1 | Email verification | Genuinely missing — signup never verified an email anywhere. | `sprint-039-gate-a-email-verification` — **done, see below.** |
| 2 | Forgot/reset password | Genuinely missing — no route, no token table, no UI link. | `sprint-039-gate-b-password-reset` — **done, see below.** |
| 3 | Stripe pricing/billing | Correct checkout/webhook/seat architecture on solid rails, but still the old 2-tier £79/£149 catalogue; no trial. | `sprint-039-gate-c-billing-pricing` — **done, see below.** |
| 4 | GeoCore AI | Combination: `OPENAI_API_KEY` genuinely unset (owner gate) + tool-calling genuinely never built (v1 scope limit); frontend copy is accurate, not stale. | `sprint-039-gate-d-geocore-ai` — **done, see below.** |
| 5 | Quote editing | Stone quotes have no edit endpoint at all; general quotes have a tested backend `PATCH` that the frontend never calls (dead code) and no edit UI. No revision concept exists. | `sprint-039-gate-e-quote-editing` — **done, see below.** |
| 6 | Blurry logo | Real, but not the initial sizing hypothesis: display sizing is ample (~4x downscale from source). The actual cause is pixel-level — every brand asset is a raster crop from one flattened AI-generated board, no vector master exists anywhere in the repo. | `sprint-039-gate-f-logo-mitigation` — **partially mitigated, see below.** |
| 7 | Stale stone positioning | Real: marketing homepage hero/copy/OG/JSON-LD still lead with "stone and construction"; `apps/web/app/signup/page.tsx` was already fixed to trade-neutral copy in Sprint 036 — only the marketing site regressed/was left behind. | `sprint-039-gate-g-trade-neutral-positioning` — **done, see below.** |

None of these seven overlap this sprint's own diff (verified via `git diff`/`git log`
against every relevant file, not assumed), so each is being closed independently and
merged to `origin/main` directly, ahead of and regardless of this sprint's own Phase 6
closeout — full combined staging acceptance across all seven happens before any
production go-ahead, per the product owner's explicit instruction.

### 14.1 Blocker 1 — Email verification: evidence

**Branch:** `sprint-039-gate-a-email-verification` (off `origin/main` @ `8e40039`).
**Alembic:** extends the verified head `b2c3d4e5f6a7` → `e1f2a3b4c5d6` (`add email
verification foundation`), linear, round-tripped (`alembic upgrade head` /
`downgrade -1` both verified locally against a real Postgres instance).

**What shipped:**
- `users.email_verified_at` (nullable, no backfill — every existing and every *new*
  user is unverified until they actually click a link) + `email_verification_tokens`
  (opaque `secrets.token_urlsafe(32)`, sha256-hashed at rest, 24h expiry, single-use
  `used_at` marker — same shape as `Invitation`/`PortalLink`).
- `EmailVerificationService` (`app/auth/verification_service.py`) sends through the
  **existing Sprint 038 `DeliveryService`/Resend infrastructure** (`app/communications/`)
  via a new `CommunicationType.EMAIL_VERIFICATION` — no parallel email pathway. The
  abandoned Sprint 037 worktree's `app/email/sender.py` (a standalone SMTP-based
  adapter) was read only as reference for its token-hashing pattern; it was not
  merged, and this implementation deliberately does not reuse it.
- `POST /auth/email/verify/resend` (authenticated, rate-limited via a new
  `CooldownLimiter`, no-ops honestly if already verified) and
  `POST /auth/email/verify/confirm` (public, single-use, expiring, generic 400 on any
  invalid/used/expired token — same error for all three so a confirm attempt reveals
  nothing).
- `require_verified_email` dependency (`app/auth/dependencies.py`) with a legacy grace
  period keyed off a fixed `identity_security_cutover_at` setting (never "now" at
  request time) — wired to the one concrete sensitive boundary that exists today,
  `POST /invitations` (inviting a second user). Further boundaries (billing, security
  settings) gain the same guard as their own gate phases land, per that dependency's
  own docstring.
- Frontend: `/verify-email` page (verifying/success/invalid/no-token states, works
  unauthenticated since a link can be opened on a different device); Settings →
  Security shows a Verified/Unverified badge with a working "Resend verification
  email" button; `TeamCard`'s invite form now surfaces the real 403 reason instead of
  a generic failure.
- `AuthService.create_user()` gained an `email_verified: bool = True` parameter —
  every existing caller (test fixtures, `app/auth/seed.py`, and
  `InvitationService.accept_invitation`, since clicking a real emailed invitation link
  is itself a form of email-ownership proof) keeps its prior, unaffected behavior;
  only the public `signup()` explicitly opts out (`email_verified=False`), since that
  is the one path where nothing has yet confirmed the caller controls the address.

**Regressions found and fixed as a direct, verified consequence of this change**
(not assumed safe — each one reproduced, then fixed):
- Multiple test files' manual tenant teardown (`tests/conftest.py`,
  `tests/test_auth.py`, `tests/test_follow_up_automation.py`,
  `tests/test_command_centre.py`, `tests/test_cleanup_launch_qa.py`) didn't delete the
  new `EmailVerificationToken` row before deleting the `User` row it FKs to —
  real `IntegrityError`s, not hypothetical, reproduced and fixed one at a time.
- **`scripts/production/cleanup_launch_qa.py`** — the real Sprint 031 production
  cleanup script — would have hit the identical `IntegrityError` deleting a real QA
  tenant's users in production. Fixed (added `EmailVerificationToken` to its deletion
  order via a `user_id` subquery, same treatment as `QuoteItem`). While there, also
  fixed a **pre-existing, unrelated Sprint 038 gap** the same test exposed:
  `Communication`/`EmailSuppression` were never added to this script's tenant-scoped
  delete list when Sprint 038 shipped them — now added.
- `tests/test_communications.py::TestRetryPending`'s exact `retried == 1` assertion
  was too strict against `retry_pending()`'s own documented cross-tenant sweep
  behavior — any other unretried "unavailable" Communication row anywhere in the dev
  database (now a common, expected byproduct of every signup's verification-email
  attempt when Resend is unconfigured) legitimately gets swept too. Loosened to
  `>= 1`; the test's real assertions (the two specific rows' final status) are
  unaffected and still exact.
- Four E2E specs (`full-system-journey`, `project-operations`,
  `role-boundary-owner-vs-staff`, plus this blocker's own two new specs) sign up a
  fresh Owner and immediately invite a Staff member as pure setup for what they
  actually test — now genuinely blocked by `require_verified_email`, correctly. Each
  gained a real verify-then-confirm step (mints a token the same way
  `EmailVerificationService` does, via a real Python subprocess against the same
  database the E2E run's own FastAPI server uses — not a mock, not a bypass) before
  inviting.

**Verification run (this branch, local — not yet staging):**
- Backend: `python -m pytest tests/` — **974 passed, 1 skipped**, 0 failed (baseline
  before this branch: 959 passed, 1 skipped — the +15 are this blocker's own new
  `tests/test_email_verification.py`, and zero pre-existing tests regressed).
- Frontend: `pnpm run check-types` — clean. `pnpm run lint` — clean. `pnpm run build`
  — succeeds, `/verify-email` correctly statically generated.
- Frontend unit (`pnpm run test`, vitest): 147 passed, 2 failed on first run
  (`GeneralQuoteBuilder.test.tsx`, `app/projects/[id]/page.test.tsx` — both 5s
  timeouts under full-suite parallel load); both confirmed to pass in isolation and
  are unrelated to this change (neither file touches auth/invitations).
- E2E (`npx playwright test`, full suite, real Chromium + real FastAPI + real
  Postgres): **28 passed, 0 failed.** First pass showed 3 failures
  (`automations.spec.ts`'s dashboard-visibility assertion, two
  `geocore-ai-and-settings.spec.ts` responsive/theme-toggle timeouts) that were
  *not* dismissed as pre-existing/unrelated flakiness without checking — the
  browser console showed a real `RecentActivityPanel` crash ("Element type is
  invalid... got undefined") on every one of them. Root cause: this blocker's new
  backend `ActivityType.EMAIL_VERIFICATION_REQUESTED`/`EMAIL_VERIFIED` values (now
  emitted on every real signup) had no matching entries in the frontend's separately
  -maintained `apps/web/types/activity.ts` union or `apps/web/lib/activity.ts`'s
  icon/tone lookup maps — the exact same class of bug Sprint 025 already fixed once
  for a different set of missing values (see that file's own docstring), now
  reintroduced by this blocker. Fixed by adding both new values to all three; full
  E2E suite reran clean immediately after (also confirmed via the real GitHub
  Actions CI run on this PR, not only locally).
- New E2E coverage added: `e2e/email-verification.spec.ts` — signup → real unverified
  state visible in Settings → resend → confirm via a minted token → real verified
  state visible; and a second spec proving `POST /invitations` is genuinely blocked
  for an unverified Owner and genuinely unblocked once verified (server-side, not
  merely UI copy).

**Known limitations, honestly stated:**
- This branch is pushed and open as PR #28 (`sprint-039-gate-a-email-verification`),
  with a real green GitHub Actions CI run (backend/frontend/e2e all passing) — but
  not yet merged, and not yet deployed to staging.
- `require_verified_email` is deliberately scoped to `POST /invitations` only in this
  phase — it is not yet applied to any billing or security-settings route, since
  those don't exist as gated concepts until their own blocker phases land.

### 14.2 Blocker 2 — Forgot / reset password: evidence

**Branch:** `sprint-039-gate-b-password-reset` (off `origin/main` @ `8e40039`).
**Alembic:** extends the verified head `b2c3d4e5f6a7` → `f2a3b4c5d6e7` (`add password
reset foundation`), linear, round-tripped. NOTE: the sibling Blocker 1 branch also
extends `b2c3d4e5f6a7` in parallel (migration `e1f2a3b4c5d6`) — whichever of the two
merges second must rebase its `down_revision` onto the other's new head before it can
merge cleanly; documented in both migration files' own docstrings, not a mistake.

**What shipped:**
- `users.token_version` (integer, default 0, no backfill needed) + `password_reset_tokens`
  (opaque `secrets.token_urlsafe(32)`, sha256-hashed at rest, 1h expiry — deliberately
  shorter than Blocker 1's 24h verification token, since a reset token grants immediate
  account takeover if leaked — single-use `used_at` marker, same shape as
  `email_verification_tokens`/`Invitation`/`PortalLink`).
- `create_access_token` now embeds a `token_version` claim; `get_current_user`
  (`app/auth/dependencies.py`) rejects a token whose claim doesn't exactly match the
  user's current value, even if the token hasn't otherwise expired. A token missing the
  claim entirely (issued before this feature existed) is treated as claiming version 0,
  matching every existing user's starting value — so no existing production session is
  force-logged-out by this migration deploying; only a user's own future reset ever
  changes what their tokens must claim. **This was not the first design — see §14.2.1
  below for a real bug a GitHub Actions CI run caught and how it changed the approach.**
- `PasswordResetService` (`app/auth/password_reset_service.py`) sends through the
  **existing Sprint 038 `DeliveryService`/Resend infrastructure**
  (`app/communications/`) via a new `CommunicationType.PASSWORD_RESET` — no parallel
  email pathway.
- `POST /auth/password/forgot`: identical response whether or not the account exists,
  response-time padded to a constant floor (`password_reset_response_floor_seconds`) so
  a naturally-faster not-found path can't be distinguished by timing, rate-limited via a
  new `CooldownLimiter` (same class Blocker 1 also introduces independently — both
  branches will need a trivial merge-conflict resolution on `app/auth/rate_limit.py`,
  keeping one copy of the shared class, when both land).
- `POST /auth/password/reset`: single-use, expiring, generic 400 on any invalid/used
  /expired token, enforces an 8-character minimum password (Pydantic `Field(min_length=8)`
  on `ResetPasswordRequest`) — no invented character-class rules beyond what this
  product has ever asked of a password anywhere, including at signup.
- Frontend: `/forgot-password` (email form → generic confirmation, identical on success
  or failure — the page itself cannot know which, matching the backend's own
  no-enumeration contract) and `/reset-password` (token from the URL, new/confirm
  password fields, form/success/invalid/no-token states) pages; a "Forgot password?"
  link added to the login page.

**Same ActivityType-drift bug class as Blocker 1 — caught proactively this time.**
Blocker 1's own gate report (§14.1) documents a real regression where new backend
`ActivityType` values crashed `RecentActivityPanel` because the frontend's separately
-maintained `apps/web/types/activity.ts`/`lib/activity.ts` weren't updated in the same
change. This blocker's two new values (`PASSWORD_RESET_REQUESTED`, `PASSWORD_CHANGED`)
were added to both the backend enum and the frontend union/lookup maps in the same
commit, specifically because that lesson had already been learned once — not
reproduced here.

### 14.2.1 A real bug real CI caught: `iat`-based revocation was wrong

The first implementation of session revocation compared JWT's `iat` claim against a
`token_valid_after` timestamp column (`issued_at < token_valid_after` → reject). Backend
tests were green locally, the branch was pushed, and PR #29's `pull_request`-triggered
CI run passed. The separately-triggered `push` CI run on the *identical commit* then
failed: `test_reset_revokes_an_existing_session` — `assert 401 == 200`, a fresh
post-reset login wrongly rejected.

Root cause, confirmed by construction (not guessed): JWT's `iat` is second-precision by
spec — PyJWT truncates any sub-second component when encoding — while
`token_valid_after` was a microsecond-precision Postgres timestamp. A login issued a
genuine instant *after* a reset can still encode an `iat` that floors down to the second
*before* `token_valid_after`'s own sub-second remainder, whenever both fall inside the
same wall-clock second — exactly what a fast automated test (no human reaction time
between reset and re-login) reliably triggers, and what real CI's own timing happened to
hit on one run and not the other.

The first fix attempt (widen the comparison with a 1-second grace window) was tried,
proven wrong immediately by the *other* direction of the same test
(`assert post_reset_me.status_code == 401` → got `200`: the stale pre-reset session was
now wrongly still accepted), and reverted. Analysis showed the asymmetry is fundamental:
an old (pre-reset) token's `iat` is *always* provably less than `token_valid_after`
(floor of a strictly-earlier instant is still less than the reset instant), but a new
(post-reset) token's `iat` can be *ambiguously* equal-or-less within the same second —
no single timestamp threshold correctly resolves both directions when comparing a
second-precision claim against a microsecond-precision value.

**Fix:** replaced the timestamp comparison with an exact integer `token_version`
counter (migration `f2a3b4c5d6e7`, amended before merge — this branch was never
deployed, so amending in place rather than adding a second migration was safe). Integer
equality has no precision-loss failure mode. Added
`tests/test_password_reset.py::test_login_issued_in_the_same_second_as_a_reset_is_not_wrongly_rejected`,
`test_login_with_a_stale_token_version_is_rejected`, and
`test_a_token_with_no_token_version_claim_is_treated_as_version_zero` — all three
construct their JWTs and `token_version` values by hand to deterministically prove the
exact scenario a lucky/unlucky millisecond had previously made intermittent, rather than
relying on real timing to reproduce it. Full backend suite reran clean after (976
passed, 1 skipped, 0 failed) and a second real CI run confirmed it holds outside this
local machine too.

**Regressions found and fixed as a direct, verified consequence of this change:**
- `tests/test_communications.py::TestRetryPending`'s exact `retried == 1` assertion —
  the identical pre-existing fragility Blocker 1 already found and fixed independently
  on its own branch (a real password-reset request now also leaves a retryable
  "unavailable" Communication row behind when Resend is unconfigured, and
  `retry_pending()`'s cross-tenant sweep is not scoped to a single test's own rows).
  Loosened to `>=` here too; both branches carry the same fix, to be reconciled (kept
  once) at merge time.

**Verification run (this branch, local, plus two real GitHub Actions CI runs):**
- Backend: `python -m pytest tests/` — **976 passed, 1 skipped, 0 failed** after both
  fixes above (the `TestRetryPending` assertion, and the `token_version` redesign in
  §14.2.1). Along the way: one `TestRetryPending` failure (fixed, same pre-existing
  fragility Blocker 1 independently found), and one real GitHub-Actions-only failure
  (`test_reset_revokes_an_existing_session`, root-caused and fixed in §14.2.1 — this
  is the one that mattered). A separate, unrelated `test_runtime_config.py` failure was
  also seen once locally and is a **pre-existing, this-machine-specific flake, not
  caused by this branch**: its own subprocess (`python -m app.core.runtime_check`)
  exits with a raw Windows `STATUS_ACCESS_VIOLATION` (0xC0000005) when spawned from
  inside pytest specifically, never when run directly, and confirmed to reproduce
  identically against a completely unmodified `origin/main` checkout — not this
  branch's responsibility, and it has not recurred in real CI (Linux runners).
- Frontend: `pnpm run check-types`, `pnpm run lint`, `pnpm run build` all clean;
  `/forgot-password` and `/reset-password` correctly statically generated. Vitest
  scoped to the 3 new/changed test files: **9 passed.** A full-suite vitest run under
  concurrent load hit worker-pool timeouts (infrastructure, not test failures); the
  same 3 files re-run in isolation afterward were clean.
- E2E: `e2e/password-reset.spec.ts` (2 new specs) plus the full existing suite. Locally,
  the full-session "forgot → reset → old session revoked" scenario and a completely
  untouched, pre-existing spec (`e2e/logout.spec.ts`) both intermittently failed on this
  specific local machine, with two distinct, now-resolved causes: (1) a zombie Next.js
  dev-server process left squatting on port 3000 by an earlier warm-up attempt, serving
  stale code to the browser (confirmed via `netstat`/`taskkill`, not guessed); and (2)
  the real `token_version` bug in §14.2.1, which the local E2E run was, in fact,
  correctly catching — it was not pure environmental noise, and treating the first E2E
  failure as "just the environment" without also independently deriving and fixing the
  root cause (which real CI then confirmed) would have been the wrong call. Two real
  GitHub Actions CI runs on this PR (Ubuntu runners, not this local Windows machine):
  the first caught the `token_version` bug for real (`push`-triggered run,
  `test_reset_revokes_an_existing_session` failed with `assert 401 == 200`); the second,
  after the fix, passed cleanly across all three jobs (backend/frontend/e2e), including
  the exact E2E scenario that had been failing.

**Known limitations, honestly stated:**
- `app/auth/rate_limit.py`'s new `CooldownLimiter` class is defined independently on
  both this branch and the sibling Blocker 1 branch (identical implementation) — a
  trivial dedup at merge time, not a design conflict.
- This branch is pushed and open as PR #29 (`sprint-039-gate-b-password-reset`), with a
  real green GitHub Actions CI run (backend/frontend/e2e all passing, on the commit that
  includes the `token_version` fix) — not yet merged, not yet deployed to staging.

### 14.3 Blocker 3 — GeoCore pricing, Stripe subscriptions and billing: evidence

**Branch:** `sprint-039-gate-c-billing-pricing` (off `origin/main` @ `8e40039`).
**Alembic:** extends the verified head `b2c3d4e5f6a7` → `a3b4c5d6e7f8` (`add
subscription trial columns`), linear, round-tripped. NOTE: the sibling Blocker 1/2
branches also extend `b2c3d4e5f6a7` in parallel (migrations `e1f2a3b4c5d6`,
`f2a3b4c5d6e7`) — whichever of the three merges last must rebase its `down_revision`
onto the others' new head before it can merge cleanly; documented in all three
migration files' own docstrings, not a mistake.

**Reproduction, before any change:** production genuinely still served the old 2-tier
catalogue — `app/billing/plans.py`'s `PRICING_GBP` was `{pro: £79/£790, business:
£149/£1490}`, confirmed by reading the file directly (not assumed from a screenshot),
and the "Billing isn't fully configured yet" string traced to `app/billing/service.py`'s
`_get_stripe()` raising whenever `STRIPE_SECRET_KEY` is unset — a real, honest 503, not
a bug, but paired with genuinely stale pricing rather than the locked one. No trial
column, model, or code path existed anywhere (`Subscription` had no `trial_start`/
`trial_end`; confirmed by reading `app/database/models.py`).

**Existing architecture confirmed solid, not rebuilt from scratch** (matching the
earlier audit's assessment): checkout already looked up the Stripe Price ID
server-side from a plan+billing_period pair validated against a Pydantic enum-like
`field_validator` (`app/billing/models.py`'s `CheckoutSessionRequest`) — a client can
supply extra fields (a spoofed `price_id`/`amount`) and they are silently ignored,
never trusted (proven by `test_checkout_ignores_a_client_supplied_price_or_amount`,
not merely assumed from reading the code). Webhook signature verification
(`stripe.Webhook.construct_event`) and idempotency (`ProcessedStripeEvent`, PK on
Stripe's own event id) were already correctly implemented and tested.

**What shipped:**
- `app/billing/plans.py` rewritten to the locked 4-tier catalogue — Starter
  (£29/£290, 1 seat), Team (£59/£590, 3 seats), Pro (£99/£990, 10 seats), Business
  (£199/£1,990, 25 seats), annual = exactly 10× monthly on every tier — plus
  Enterprise (custom, contact-sales/demo, never self-service). This remains the single
  authoritative plan catalogue: `GET /billing/plans` is built entirely from this file,
  and the frontend pricing page and Settings → Billing card both render whatever it
  returns — neither hardcodes a price.
- `app/billing/trial.py` (new) — every signup now starts a real 14-day trial
  (`start_trial_if_eligible`, called from `AuthService.signup()`), deliberately
  creating the `Subscription` row with **no Stripe customer/subscription id at all**.
  Stripe is never contacted during the trial — a stronger guarantee than Stripe's own
  trial-on-Checkout mechanism, since it makes charging a card-less tenant structurally
  impossible rather than merely policy. A real checkout later (via
  `create_checkout_session`) creates a genuine Stripe subscription at that point,
  converting the same row in place (proven by
  `test_checkout_completed_converts_a_trial_to_paid_and_preserves_trial_history` —
  trial_start/trial_end survive the upgrade as historical record).
- `app/billing/entitlements.py` gained `is_trial_expired()` — an expired trial is
  deliberately **not** treated as "no subscription" (which would fail open to
  unmetered/unlimited, the opposite of "must not accidentally receive permanent paid
  access"): `require_seat_available` now blocks any *new* seat once a trial has
  expired without conversion, while never removing or disabling anyone already there
  (same "handle safely, never delete/disable" principle the brief applies to a tenant
  exceeding a newly-assigned tier). Full access-blocking beyond the seat dimension
  (e.g. read-only mode) was not built — see Known limitations.
- 8 Stripe Price settings (`app/core/config.py`) — Starter/Team are new;
  Pro/Business reuse Sprint 032's original setting names but must be repointed to NEW
  Stripe Price objects at the new amounts (see the owner-gate spec below) — the old
  £79/£149 Price objects stay live in Stripe untouched, still serving any
  already-existing subscriber bound to them directly (a Stripe subscription
  references its Price by id, independent of what this app's env vars point to).
- Frontend: pricing page rebuilt for 5 plans (was a 3-column, 2-self-service-plan
  grid), trial countdown banner, current-plan/trialing-plan state per card, "Book a
  demo" as Enterprise's primary CTA (`NEXT_PUBLIC_DEMO_BOOKING_URL`, same
  "never hardcode an unverified destination" pattern Sprint 034 already established
  for `NEXT_PUBLIC_SALES_EMAIL` — the existing `sales-cta.test.mjs` contract test
  still passes unmodified). Settings → Billing card gained the same trial banner and
  a 5-column change-plan grid.
- Seat enforcement numbers (1/3/10/25) now match the locked entitlements exactly —
  `require_seat_available` itself needed no logic change, only the new
  `ENTITLEMENTS` map it already reads generically.

**Regressions found and fixed as a direct, verified consequence of this change** (the
same "every real signup now creates a new row" lesson Blockers 1 and 2 each hit
independently, this time for `Subscription` instead of `EmailVerificationToken`/none):
- `tests/conftest.py`'s `_cleanup_other_tenant`, plus `test_auth.py`,
  `test_follow_up_automation.py`, `test_command_centre.py`, and
  `test_cleanup_launch_qa.py`'s own manual tenant-teardown helpers, all needed a
  `delete(Subscription)` added before their `Tenant`/`User` deletes — real
  `IntegrityError`s, reproduced then fixed one at a time.
- **`scripts/production/cleanup_launch_qa.py`** — the real Sprint 031 production
  cleanup script — would have hit the identical `IntegrityError` deleting a real QA
  tenant's users in production, since `Subscription` was never added to its
  `_TENANT_SCOPED_TABLES_IN_ORDER` list. Fixed (it has a plain `tenant_id` column, no
  join needed, unlike Blocker 1's `EmailVerificationToken` fix on this same script).

**Owner gate — Stripe Products/Prices to create (nothing fabricated, no live object
touched):** see the exact 8-row table, environment variable names, staging-vs-production
and test-vs-live-mode split, and what to leave untouched, already delivered in this
gate's conversation record and unchanged since — reproduced here for the permanent
record:

| Product | Price | Amount | Interval |
|---|---|---|---|
| GeoCore Starter | Starter Monthly | £29.00 | month |
| GeoCore Starter | Starter Annual | £290.00 | year |
| GeoCore Team | Team Monthly | £59.00 | month |
| GeoCore Team | Team Annual | £590.00 | year |
| GeoCore Pro | Pro Monthly | £99.00 | month |
| GeoCore Pro | Pro Annual | £990.00 | year |
| GeoCore Business | Business Monthly | £199.00 | month |
| GeoCore Business | Business Annual | £1,990.00 | year |

Env vars: `STRIPE_PRICE_STARTER_MONTHLY`, `STRIPE_PRICE_STARTER_ANNUAL`,
`STRIPE_PRICE_TEAM_MONTHLY`, `STRIPE_PRICE_TEAM_ANNUAL`, `STRIPE_PRICE_PRO_MONTHLY`
(repoint), `STRIPE_PRICE_PRO_ANNUAL` (repoint), `STRIPE_PRICE_BUSINESS_MONTHLY`
(repoint), `STRIPE_PRICE_BUSINESS_ANNUAL` (repoint). Create the full set twice — once
in Stripe Test mode (→ `simo-api-staging`) and once in Live mode (→
`simo-api-production`, only after staging's full test-mode lifecycle passes). Old
£79/£149 Price objects: leave untouched in Stripe, for rollback/history — no
existing subscriber is affected by an env var repoint. Enterprise: no Stripe object,
ever, for self-service.

**Verification run (this branch, local, plus real GitHub Actions CI):**
- Backend: `python -m pytest tests/` — **964 passed, 1 skipped, 0 failed** (+28 in
  `tests/test_billing.py`, up from the pre-existing 20). Two intermittent failures
  seen along the way (`test_runtime_config.py`, `test_runtime_http.py`) are the same
  pre-existing, this-machine-specific flake already documented and confirmed against
  unmodified `origin/main` in Blocker 2's own evidence (§14.2) — both pass cleanly in
  isolation and are unrelated to this branch's changes.
- Frontend: `pnpm run check-types`, `pnpm run lint`, `pnpm run build` all clean;
  `pnpm run test:sales-cta` (the Sprint 034 no-hardcoded-mailbox contract test) still
  passes unmodified. `apps/web/app/pricing/page.test.tsx`: 5 passed (widened from 4
  to 5 plans, trial-state assertions added).
- E2E: new `e2e/billing-pricing.spec.ts` (2 specs) written to prove the 4-tier
  catalogue renders with the exact locked prices in both monthly and annual view, a
  new Owner is shown as trialing Pro, and checkout's 503 "not configured yet"
  fallback is proven honest. Local Playwright runs on this specific machine hit the
  same demonstrated sandbox instability already documented in Blocker 2's evidence
  (§14.2) — a zombie dev-server process re-appeared on port 3000 from an earlier run
  (confirmed via `netstat`/`taskkill`, not guessed) and, after clearing it, even a
  bare `curl` to `localhost`/`127.0.0.1` timed out or was refused, which is an
  environment-level networking fault, not a Next.js/FastAPI problem (both servers
  logged themselves as ready). Full local E2E confirmation was not reached in that
  session, so this was deferred to real GitHub Actions CI (the same authoritative
  signal Blockers 1 and 2 both relied on) — which then caught two genuine bugs in the
  new spec itself: `getByText("GeoCore Starter")` and `getByText("Your trial")` each
  resolved to two elements in real Chromium (a plan's name also appears inside its
  own "Upgrade to"/"Choose" button, and the trial badge's text is a case-insensitive
  substring of the trial countdown banner's own copy), both fixed by scoping to
  `getByRole("heading", …)` and `{ exact: true }` respectively. A separate, genuine
  regression was also caught in the **pre-existing** `geocore-ai-and-settings.spec.ts`
  (Sprint 036): its billing journey asserted the old "No plan yet" state and a
  "Choose GeoCore Pro" button, both of which stopped existing once every signup
  started a real trial of Pro (Pro's card now shows "Current plan" instead) — fixed
  to assert the trial banner and exercise checkout on GeoCore Business instead. CI
  run [34655456149](https://github.com/SMC-OS/SMC-OS/actions/runs/34655456149) on
  commit `189ad06` is fully green: **backend ✓, frontend ✓, e2e ✓** (all 28 specs).

**Known limitations, honestly stated:**
- Trial-expiry enforcement is scoped to seats only (the existing enforcement lever in
  this codebase) — an expired, unconverted trial does not lose access to the product
  more broadly (e.g. read-only mode). Flagged as a deliberate scope decision, not an
  oversight; extending it is straightforward future work on the same
  `is_trial_expired()` helper.
- No real Stripe test-mode lifecycle (checkout → subscription created → webhook →
  GeoCore reflects it) has been exercised yet — that requires the owner-gate Price
  objects above to exist first, and is the next step before any staging sign-off.
- This branch is pushed and open as PR #30 (`sprint-039-gate-c-billing-pricing`), with
  a real green GitHub Actions CI run (backend/frontend/e2e all passing) — not yet
  merged, not yet deployed to staging.

### 14.4 Blocker 4 — GeoCore AI capability: evidence

**Branch:** `sprint-039-gate-d-geocore-ai` (off `origin/main` @ `8e40039`, same base as
the sibling gate branches). No migration — this blocker needed no schema change.

**Reproduction, read-only, before any change:**
- **origin/main / current Sprint 039 branch (`sprint-039-communications-ai-pipeline`,
  not yet merged):** `app/ai/service.py` on both is architecturally identical for the
  symptom in question — a real LLM is used only when `OPENAI_API_KEY` is configured;
  otherwise the service falls back to `app/brain/BrainManager`, a keyword router over
  the material catalogue, and labels every reply `engine: "builtin"`. The unmerged
  Sprint 039 branch does *not* fix Blocker 4's root cause — it only corrects a
  different, narrower wording bug (below) and adds a real message-drafting feature
  (Phase 4+5, human-review-gated) that does not exist on `main`. Deliberately **not**
  pulled into this branch: merging an entire 5-phase, not-yet-independently-verified
  feature branch into a narrow defect-gate fix would blow this blocker's scope and its
  isolation from PR #30-style review. Flagged here as a separate decision for whoever
  owns merging `sprint-039-communications-ai-pipeline` itself.
- **staging (`simo-api-staging`) and production (`simo-api-production`), Railway
  project `simo-os`:** `describe-service` was used for both — it lists variable
  *names* only, never values, so no secret was read, printed or logged at any point in
  this investigation. Neither service's variable list contains `OPENAI_API_KEY` or any
  other `OPENAI_*` name. Full staging variable list: `APP_ENV, CORS_ALLOWED_ORIGINS,
  DATABASE_URL, JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET_KEY, PORT,
  READINESS_TIMEOUT_SECONDS, RESEND_API_KEY, RESEND_WEBHOOK_SECRET, SEED_ADMIN_EMAIL,
  SEED_ADMIN_PASSWORD, SEED_DATA_ENABLED, UPLOAD_DIR`. Production's list is the same
  shape minus `READINESS_TIMEOUT_SECONDS`, plus `RAILWAY_RUN_UID`. This is the
  authoritative, direct confirmation the key is absent in both environments — not an
  inference from behaviour.
- **Live staging behaviour**, confirmed directly (one throwaway signup against
  `simo-api-staging-staging.up.railway.app`, cleaned up as ordinary test data — no
  production writes were made, since the Railway config check above already
  conclusively answers the same question for production without needing to create any
  data in the live commercial database): `GET /api/v1/ai/capabilities` →
  `llm_configured: false`, `workspace_context: false`, `quote_drafting: false`,
  `material_search: true`, with the honest note "No AI provider is connected to this
  workspace...". `POST /api/v1/ai/chat` → `engine: "builtin"`, reply is the plain,
  accurate "I'm GeoCore's built-in assistant..." fallback copy. This is the running
  process itself reporting its real state, not a guess.
- **Frontend (`apps/web/app/ai/page.tsx`):** entirely capability-driven — reads
  `capabilities.llm_configured` to choose between `SUGGESTIONS_WITH_LLM` and
  `SUGGESTIONS_BUILTIN`, to pick the header subtitle, and to show the "No AI provider
  is connected..." banner. No hardcoded or stale copy found. **Verdict: not a frontend
  bug** — the UI is accurately reflecting exactly what the backend reports.
- **Workspace context (`app/ai/context.py`):** already a genuine, tenant-scoped,
  bounded, PII-free summary of quotes/projects/tasks — a real "full business-context"
  payload, not just materials. Gated behind the same missing key, not separately
  broken.

**Genuine code defect found and fixed (independent of the owner gate):** the system
prompt (`app/ai/service.py`, `_SYSTEM_PROMPT`) told the model "GeoCore cannot send
email, SMS or messages to customers" — false since Sprint 038 shipped real quote
delivery and follow-up automation on `main` itself. The assistant was instructed to
tell users their own product couldn't do something it does every day, whenever an LLM
*is* configured. Corrected to state GeoCore itself can email a customer (e.g.
delivering a quote), always as a person's action in GeoCore, never the AI's own.
Deliberately worded without any reference to AI-driven "drafting", since that
capability does not exist on this branch's base (`main`) — only on the unmerged
communications-ai-pipeline branch. New regression test
`test_the_prompt_does_not_claim_geocore_cannot_email_customers` locks this down via
the existing stub-client pattern already used by this test file.

**Invariants preserved:** tenant isolation and bounded/PII-free context were already
enforced by `app/ai/context.py` and untouched; no invented figures (the system prompt
still explicitly forbids this); no silent sends and no destructive actions (the
service has no tools and still cannot write); the human-review gate for outbound
AI-assisted communication does not exist on this branch and was not added, so there is
nothing to bypass. This fix only removes a false claim from the model's own
instructions — it grants the model no new capability.

**A separate, unrelated pre-existing defect found incidentally, not fixed here (out of
this blocker's scope):** while running the full backend suite,
`tests/test_automations.py::test_project_starting_scan_notifies_once` and
`tests/test_dashboard.py::test_dashboard_reflects_real_data` both failed. Root-caused,
not dismissed: both rely on comparing a Python-local `date.today()` (used in
`app/database/crud.py`'s `count_quotes_today` and in the automation scanner's
"starting tomorrow" query) against a date derived from a `timestamptz` column inside
Postgres, whose session timezone need not match the application host's local
timezone — a real, latent day-boundary bug, not test flakiness. Confirmed
pre-existing and unrelated to this change by stashing this branch's entire diff and
re-running the same two tests against unmodified `origin/main`: identical failures.
Not fixed here because it is unrelated to GeoCore AI and is not one of the seven named
blockers — flagged for a separate, dedicated fix.

**Owner gate — the blocking item for this blocker's main symptom:**

| Field | Answer |
| --- | --- |
| Exact variable name(s) | `OPENAI_API_KEY` (required). `OPENAI_MODEL` (optional — defaults to `gpt-4o-mini` in code; only needed to use a different model). |
| Exact Railway service(s) | `simo-api-staging` (environment `staging`) and `simo-api-production` (environment `production`), project `simo-os`. |
| Separate keys for staging vs. production? | Recommended: yes, two separate OpenAI API keys, one per environment — mirrors the existing pattern for every other provider in this codebase (Resend, Stripe) and means a staging key can be rotated or rate-limited without touching production traffic. Not a hard requirement of the code (it reads one `OPENAI_API_KEY` value per environment either way). |
| Model/config variable also required? | No. `OPENAI_MODEL` has a working default (`gpt-4o-mini`) baked into `app/core/config.py`. Only set it if a different model is wanted. |
| Key alone sufficient, or is a redeploy/restart required? | Setting a Railway service variable triggers Railway's normal automatic redeploy of that service; no manual restart step beyond that. Because `AIService._get_client()` constructs the OpenAI client lazily on first real use (never at import or startup), the new key takes effect as soon as the new deployment is live — no additional app-level cache to bust. |
| Exact post-configuration verification steps | 1) `GET /api/v1/ai/capabilities` (authenticated) on the environment just configured — expect `llm_configured: true`, `workspace_context: true`, `quote_drafting: true`. 2) `POST /api/v1/ai/chat` with a business question (e.g. "What needs my attention today?") — expect `engine: "llm"` and a reply grounded in that tenant's real quotes/projects/tasks, not a material lookup. 3) Confirm the frontend `/ai` page shows the `SUGGESTIONS_WITH_LLM` prompts and no "No AI provider is connected" banner. 4) Ask a question with no real answer in the workspace summary and confirm the model says so rather than inventing a figure (per the system prompt's explicit instruction). Repeat all four for the other environment once its own key is set — the two are configured independently. |

**Verification run:**
- Backend: `python -m pytest tests/test_geocore_ai.py` — **12 passed** (11 pre-existing
  + 1 new regression test for the corrected prompt wording). Full suite:
  **957 passed, 1 skipped, 3 failed** — one failure is the same pre-existing,
  this-machine-specific `test_runtime_config.py` flake already documented in
  Blocker 2's evidence (§14.2); the other two
  (`test_automations.py::test_project_starting_scan_notifies_once`,
  `test_dashboard.py::test_dashboard_reflects_real_data`) are the pre-existing,
  unrelated day-boundary defect described above, confirmed present on unmodified
  `origin/main` with this branch's changes stashed out.
- Frontend: no frontend changes were needed — `apps/web/app/ai/page.tsx` was already
  fully capability-driven (confirmed by reading it directly, not assumed).
- E2E: no new E2E coverage was needed for this fix. The corrected system-prompt
  wording is only ever sent to a real LLM, which is not configured anywhere Playwright
  runs (locally or in CI) — the existing backend unit test with a stub client
  (`AIService(client=stub)`) is the correct and only way to verify prompt content
  without a real provider. The existing E2E spec
  (`geocore-ai-and-settings.spec.ts::geocore_ai_holds_a_conversation_and_never_shows_developer_internals`)
  continues to exercise the unaffected builtin path and is untouched.

**Known limitations, honestly stated:**
- The dominant symptom ("presents as a material lookup bot") is **not yet resolved in
  either staging or production** — it is owner-gated on `OPENAI_API_KEY`, per the table
  above. No code change can fix this; the implementation is already correct and
  waiting on the credential.
- The "AI drafting with a human review gate" feature (Phase 4+5 of
  `sprint-039-communications-ai-pipeline`) is real, already built, and not yet merged
  anywhere — a further, separate scope/merge decision, not part of this fix.
- The pre-existing day-boundary bug in `count_quotes_today`/the automation scanner
  (above) remains unfixed — out of scope for Blocker 4, flagged for separate work.
- This branch is pushed and open as PR #31 (`sprint-039-gate-d-geocore-ai`), with a
  real green GitHub Actions CI run (backend/frontend/e2e all passing) — not yet
  merged, not yet deployed to staging.

### 14.5 Blocker 5 — Quote editing: evidence

**Branch:** `sprint-039-gate-e-quote-editing` (off `origin/main` @ `8e40039`, same base
as the sibling gate branches). No migration — no schema change was needed.

**Reproduction, before any change:** the backend's `PATCH /api/v1/quotes/{id}`
(`app/quotes/router.py::update_general_quote` → `QuoteService.update_general`) was
already fully built, already correctly re-prices from either replaced lines or an
unchanged set, already refuses a stone-kind quote (409) and a non-draft quote (409),
and was already comprehensively tested (`tests/test_general_quotes.py`'s `# ---
Editing ---` section — reprice-with-new-lines, reprice-without-lines,
refuse-an-approved-quote, refuse-a-stone-quote, 404-cross-tenant — all present and all
passing before this branch touched anything). The frontend API client already wrapped
it (`apps/web/lib/api.ts`'s `updateGeneralQuote`). Confirmed by reading the code
directly, not assumed: **nothing in the frontend ever called it.**
`grep -rn "updateGeneralQuote" apps/web --include="*.tsx" --include="*.ts"` outside
`lib/api.ts` returned no matches. `apps/web/app/quotes/[id]/page.tsx` had no Edit
button, no edit route, and no edit form anywhere — a user could view a draft general
quote and mark it sent, approve it, or download its PDF, but never change it. This is
"incomplete", precisely as the blocker describes it, not "broken": the one piece that
was missing was the entry point, not the underlying logic.

**What shipped:**
- `apps/web/components/quotes/GeneralQuoteBuilder.tsx` gained an optional
  `existingQuote?: Quote` prop. When present, every field initialises from the quote
  (including its line items, mapped from `QuoteItem[]` back into the same `LineRow`
  shape the create flow already uses), the submit button reads "Save changes", submit
  calls `api.updateGeneralQuote(existingQuote.id, payload)` instead of
  `createGeneralQuote`, and the success card reads "Quote updated" / "Back to the
  quote" instead of "Quote created" / "Open the quote". The pricing arithmetic itself
  — the sprint's central claim for this component — is untouched; edit mode reuses it
  exactly.
- New page `apps/web/app/quotes/[id]/edit/page.tsx`: fetches the quote, then refuses
  plainly (no half-rendered form) for the same three reasons the backend already
  enforces — not found, a stone quote ("stone quotes use their own template"), or a
  quote that is not a draft ("already been sent or approved") — before rendering
  `GeneralQuoteBuilder` in edit mode.
- `apps/web/app/quotes/[id]/page.tsx` gained an "Edit" link, visible exactly when
  `quote.status === "draft" && quote.quote_kind === "general" && canAct` — mirroring
  the backend's own refusal conditions so the button never offers something the API
  would then reject.

**Invariants preserved:** tenant isolation and the draft/general-only edit rule are
enforced server-side exactly as before (untouched); no invented figures (the total
shown is always the server's re-priced answer, confirmed by the E2E assertion below);
no silent mutation of a document the customer already holds (a sent or approved quote
has no Edit entry point, and the backend still refuses it as a second, authoritative
line of defence even if a client bypassed the UI); nothing here adds a send/delivery
path, so no human-review-gate question arises.

**Verification run:**
- Backend: unaffected (no backend files changed). Re-ran
  `python -m pytest tests/test_general_quotes.py` to confirm the baseline this
  frontend feature depends on is still exactly as solid as it looked: **30 passed**.
- Frontend: `pnpm run check-types`, `pnpm run lint`, `pnpm run build` all clean (the
  build's route list shows the new `ƒ /quotes/[id]/edit` page). New/updated unit
  tests, run individually rather than via the full `vitest run` (the full run hit the
  same "Timeout terminating forks worker" cascade already documented as a
  this-machine-specific resource issue in earlier blockers' evidence — dozens of
  entirely unrelated test files, e.g. `MobileNav.test.tsx`, `AuthProvider.test.tsx`,
  `usePolling.test.ts`, failed to even start a worker, which is a process-pool
  exhaustion signature, not a test assertion failure): `GeneralQuoteBuilder.test.tsx`
  — **8 passed** (6 pre-existing + 2 new edit-mode tests);
  `app/quotes/[id]/page.test.tsx` + `app/quotes/[id]/edit/page.test.tsx` together —
  **10 passed** (7 pre-existing + 3 new edit-entry-point tests across both files).
- E2E: new test `a_draft_general_quote_can_be_edited_and_the_change_is_saved`
  (`e2e/general-quoting.spec.ts`) — creates a draft general quote via the API, opens
  it, clicks Edit, confirms the existing line is pre-filled (not a blank form),
  changes the quantity, saves, asserts the **server's** re-priced total (900 → 1080
  after 20% VAT, not a value computed by the test), confirms the detail page reflects
  it, then marks the quote sent and confirms the Edit link disappears. Local
  Playwright hit the same webServer startup timeout already documented repeatedly in
  this gate's evidence (backend started cleanly; the frontend dev server did not
  become reachable inside the harness's timeout on this specific machine) — deferred
  to real GitHub Actions CI, the same authoritative signal every prior blocker in this
  gate has relied on. CI then caught three genuine bugs in the new spec itself, all
  root-caused and fixed rather than dismissed: `toHaveValue(2)` doesn't type-check
  against Playwright's `string | RegExp` signature (unlike jest-dom's own
  `toHaveValue`, which does accept a number); `getByRole("link", { name: "Edit" })`
  was a strict-mode violation because this test's own unique run id
  (`edit-<timestamp>-<random>`) appears inside the seeded customer's own name, whose
  link on the same page substring-matches "Edit" too; and `£1,080.00` legitimately
  appears twice on the quote detail page (the header badge and the itemised total
  row), the same pattern the file's own pre-existing test already handles with
  `.first()`. CI run
  [34663587582](https://github.com/SMC-OS/SMC-OS/actions/runs/34663587582) on commit
  `23f4dc4` is fully green: **backend ✓, frontend ✓, e2e ✓** (all 27 specs).

**Known limitations, honestly stated:**
- Only general quotes can be edited through this new UI, matching the backend's own
  restriction exactly — a stone quote still has no edit path (it never did; it is
  priced by a completely different, slab-based code path, and building an edit flow
  for it is a separate, larger piece of work, not attempted here).
- Editing is whole-form: there is no per-field "quick edit" (e.g. changing just the
  valid-until date without opening the full builder). Consistent with how the create
  flow already works, and not something the blocker asked for.
- This branch is pushed and open as PR #32 (`sprint-039-gate-e-quote-editing`), with a
  real green GitHub Actions CI run (backend/frontend/e2e all passing) — not yet
  merged, not yet deployed to staging.

### 14.6 Blocker 6 — Blurry logo on the marketing site: evidence

**Branch:** `sprint-039-gate-f-logo-mitigation` (off `origin/main` @ `8e40039`, same
base as the sibling gate branches). No migration.

**Reproduction, before any change — the CSS/sizing hypothesis was tested and ruled
out first:** the marketing header renders `/brand/horizontal-logo.png` (590×143
source) via `next/image` at `width={200} height={49}`, and `.wordmark img { height:
2.25rem; width: auto; }` displays it at roughly 147×36 CSS pixels. That is a ~4x
downscale from the source — ample resolution even at 2–3x device pixel ratios.
Confirmed directly rather than assumed: sizing and CSS are **not** the cause.

**Actual root cause, confirmed at the pixel level:** the source PNG was cropped and
zoomed 3x with nearest-neighbour scaling (no interpolation added) to inspect the raw
source pixels directly. The letterforms show soft, feathered edges baked into the
file itself — not a display, scaling, or Next.js compression artefact. This traces to
the brand asset pack's own documentation
(`.brand-assets-extracted/GeoCore-Official-Brand-Asset-Pack/README.txt`, present in
the repo working tree but untracked):

> "The board is a single flattened raster image, so these files are exact region
> exports from that board... these are raster exports rather than original
> vector/SVG source artwork... Do not redesign or reinterpret the G geometry."

Every logo asset currently in use (`apps/marketing/public/brand/*.png`,
`apps/web/public/brand/*.png`) is a crop from one flattened, AI-generated raster
board (`00-geocore-official-brand-board.png`, 1536×1024 — a typical image-generation
canvas size, not a design-tool export). **There is no vector (SVG/AI/EPS) master
anywhere in the repository.** The softness is inherent to the source artwork, not
something any code, CSS, or Next.js Image configuration change can fix.

**What was deliberately NOT done:** no redrawing, sharpening, upscaling, AI
enhancement, re-cropping, or geometry reinterpretation of the logo. The brand pack
explicitly forbids reinterpreting the "G" geometry, and fabricating a "fixed" asset
without owner approval would ship an unapproved brand asset — the same discipline
applied to Blockers 3 and 4's owner-gated external dependencies.

**What shipped — a safe, source-preserving mitigation only:**
- `apps/marketing/app/page.tsx`: added `quality={100}` to the header logo's
  `next/image`. Next.js's optimizer re-encodes at quality 75 by default; on an
  already-soft source, that compounds the softness with avoidable extra lossy
  compression for no benefit. This stops making a soft source *worse* — it does not
  sharpen, upscale, or alter it in any way.
- New regression test `apps/marketing/logo-quality.test.mjs` (static source-text
  assertion, same pattern as the existing `indexability.test.mjs`): fails if
  `quality={100}` is ever silently dropped from the header logo. Wired into CI as a
  new step ("Test marketing logo quality mitigation") in the same required `frontend`
  job as the existing indexability and sales-CTA contract checks
  (`.github/workflows/ci.yml`), immediately after "Test marketing indexability
  contract".

**Verification run:**
- `pnpm run test:logo-quality` (marketing) — **1 passed**.
- `pnpm run test:indexability` (marketing) — **9 passed**, unaffected.
- `pnpm run check-types`, `pnpm run lint`, `pnpm run build` (marketing) — all clean.

**Status: PARTIALLY MITIGATED — owner vector/high-fidelity asset required.** The
mitigation is real and shipped, but it does not resolve the underlying complaint on
its own. Full resolution requires one of: (a) a genuine vector (SVG/AI/EPS) redraw of
the approved "G" geometry from whoever controls the brand source, or (b) a
higher-fidelity raster master supplied by the owner to re-export the crops from. This
blocker is **not** being marked closed.

This branch is pushed and open as PR #33 (`sprint-039-gate-f-logo-mitigation`), with a
real green GitHub Actions CI run (backend/frontend/e2e all passing) — not yet merged,
not yet deployed to staging.

### 14.7 Blocker 7 — Stale stone-specific positioning: evidence

**Branch:** `sprint-039-gate-g-trade-neutral-positioning` (off `origin/main` @
`8e40039`, same base as the sibling gate branches). No migration. Note: this branch
and Blocker 6's (`sprint-039-gate-f-logo-mitigation`) both touch
`apps/marketing/app/page.tsx` — Blocker 6 only the header `<Image>`'s `quality` prop,
this one only the hero/feature copy further down the same file. Different hunks, no
line-level overlap; whichever merges second should merge cleanly, same as the
Alembic `down_revision` friction already documented for the other sibling branches.

**Audit performed, read-only, before any change** — every surface named in the
blocker:
- Homepage hero, supporting sections, feature cards (`apps/marketing/app/page.tsx`)
- Marketing meta description / Open Graph / structured data (all three driven by one
  `SITE_DESCRIPTION` constant in `apps/marketing/lib/site.ts`)
- `apps/web`'s own app metadata (`apps/web/app/layout.tsx`) and PWA manifest
  (`apps/web/app/manifest.ts`)
- Pricing copy (`apps/web/app/pricing/page.tsx`) — clean, no stone-specific top-level
  language found
- Signup/onboarding copy (`apps/web/app/signup/page.tsx`, `apps/web/app/onboarding/`)
  — already trade-neutral, fixed in Sprint 036 per that file's own comment ("The
  previous placeholders... told every plumber, roofer and decorator signing up that
  this product was not for them") — confirmed current placeholders are
  "Hartley Building Ltd" / "Sam Hartley", not stone-specific
- AI-facing copy (`app/ai/service.py`'s `_SYSTEM_PROMPT`) — already trade-neutral
  ("Stone and worktops are one specialism among many, never the assumed default"),
  confirmed unchanged and correct
- Root `README.md`

**Found — four genuine top-level positioning defects, plus one drift bug:**
1. `apps/marketing/lib/site.ts`'s `SITE_DESCRIPTION` — "the AI operating system for
   **stone and construction** businesses". This single constant feeds the marketing
   meta description, Open Graph description, and all three `structuredData` entries
   (`Organization`, `WebSite`, `SoftwareApplication`) in `page.tsx` — one fix here
   corrects all of them at once.
2. `apps/marketing/app/page.tsx`'s hero `<h1>` — "The operating system for stone and
   construction businesses."
3. `apps/marketing/app/page.tsx`'s feature-section lead — "Built around the way a
   stone and construction business actually runs."
4. `apps/marketing/app/page.tsx`'s first capability card — "Multi-item quotes with
   real material **and slab calculations**, priced consistently every time" — the
   very first feature a visitor reads named slab calculations as the headline
   mechanism, for a product now positioned around construction and renovation in
   general.
5. **Drift, not a fresh defect:** `apps/web/app/layout.tsx`'s own metadata had
   *already* been corrected to "The AI operating system for construction and
   renovation businesses" (Sprint 034/036 work, confirmed by reading it directly) —
   but `apps/web/app/manifest.ts`'s PWA manifest description still read "AI operating
   system for stone and construction businesses", never updated to match. The two
   had silently diverged.

**What shipped:**
- `apps/marketing/lib/site.ts`: `SITE_DESCRIPTION` corrected to "construction and
  renovation businesses", fixing the meta description, Open Graph, and all
  structured-data entries in one place.
- `apps/marketing/app/page.tsx`: hero `<h1>` corrected to "The AI operating system
  for construction and renovation businesses."; feature-section lead corrected to
  "Built around the way a construction or renovation business actually runs"; first
  capability card reworded to "Multi-item quotes — labour, materials and specialist
  slab calculations — priced consistently every time" (labour and materials lead;
  slab calculations named as one input among several, not the headline).
- `apps/web/app/manifest.ts`: description corrected to match `layout.tsx` exactly
  ("The AI operating system for construction and renovation businesses").
- `README.md`: same correction to the one-line project description.
- Stone/worktops remain fully supported and unchanged as a specialist
  vertical/template throughout — `/quotes/new/stone`, the "Quoting stone or
  worktops?" callout on `/quotes/new`, the stone-kind quote badge, and every backend
  stone-pricing code path are untouched. This blocker corrects positioning claims
  about what GeoCore *is*, not the stone functionality itself.

**New regression tests (TDD: written to assert the corrected copy and confirmed
failing against the pre-fix source before landing the fix, then passing after):**
- `apps/marketing/positioning.test.mjs` (3 tests) — asserts `SITE_DESCRIPTION` and
  the homepage `<h1>` both say "construction and renovation businesses" and neither
  the site's `lib/site.ts` nor `page.tsx` contains "stone and construction" or
  "operating system for stone" anywhere.
- `apps/web/app/positioning.test.mjs` (2 tests) — asserts `layout.tsx` and
  `manifest.ts` both say "construction and renovation businesses" and neither
  contains "stone and construction", closing the drift gap between them for good.
- Both wired into `.github/workflows/ci.yml` as new required steps ("Test app
  trade-neutral positioning", "Test marketing trade-neutral positioning") in the same
  job as the existing indexability/sales-CTA/logo-quality contract checks.

**Verification run:**
- `pnpm --filter marketing test:positioning` — **3 passed**.
- `pnpm --filter marketing test:indexability` — **9 passed**, unaffected.
- `pnpm --filter web test:positioning` — **2 passed**.
- `git diff --check` — clean, no whitespace errors.
- `pnpm run check-types` (repo-wide, via turbo) — **3/3 packages successful**
  (`web`, `marketing`, `@repo/ui`).
- `pnpm run lint` (repo-wide) — clean.
- `pnpm run build` (repo-wide): the combined turbo run hit one transient failure —
  `next/font` could not reach `fonts.googleapis.com` during the marketing build, a
  network-connectivity fault in this sandbox, not a code defect. Confirmed by
  re-running each app's build standalone immediately after: `apps/marketing` —
  clean; `apps/web` — clean. Not treated as a real failure without this
  confirmation, per this gate's established discipline of never dismissing a
  failure without verifying its cause first.
- Final sweep for any remaining stale reference: `grep -ri "stone and construction"`
  across the entire repository returns matches only inside the two new test files'
  own negative assertions — zero remaining occurrences in source, copy, or docs.

**Known limitations, honestly stated:**
- E2E: no new E2E coverage was added. This blocker is a copy/metadata correction with
  no new interactive behaviour to exercise, and the existing E2E suite does not
  assert marketing homepage copy (the marketing app has no E2E specs of its own —
  its own indexability/positioning contracts are covered by the static
  `node --test` files instead, matching how `indexability.test.mjs` already covers
  that app without Playwright).
- This branch is pushed and open as PR #34 (`sprint-039-gate-g-trade-neutral-positioning`),
  with a real green GitHub Actions CI run (backend/frontend/e2e all passing) — not yet
  merged, not yet deployed to staging.
