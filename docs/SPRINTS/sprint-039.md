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
| 3 | Stripe pricing/billing | Correct checkout/webhook/seat architecture on solid rails, but still the old 2-tier £79/£149 catalogue; no trial. | Not started. |
| 4 | GeoCore AI | Combination: `OPENAI_API_KEY` genuinely unset (owner gate) + tool-calling genuinely never built (v1 scope limit); frontend copy is accurate, not stale. | Not started. |
| 5 | Quote editing | Stone quotes have no edit endpoint at all; general quotes have a tested backend `PATCH` that the frontend never calls (dead code) and no edit UI. No revision concept exists. | Not started. |
| 6 | Blurry logo | Real: `next/image` requests the 590×143px source at a display size that exceeds it at 2×/3× DPR; separately, the correct 1200×630 OG image already exists on disk but was never copied into `apps/marketing/public/brand/`. | Not started. |
| 7 | Stale stone positioning | Real: marketing homepage hero/copy/OG/JSON-LD still lead with "stone and construction"; `apps/web/app/signup/page.tsx` was already fixed to trade-neutral copy in Sprint 036 — only the marketing site regressed/was left behind. | Not started. |

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
