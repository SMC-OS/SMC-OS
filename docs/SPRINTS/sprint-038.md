# Sprint 038 — GeoCore Communications, Outbound Delivery & Automation Execution

**Status:** Phase 0 (discovery + locked contract) complete. Implementation not started —
blocked at the provider/DNS decision gate below (§4).
**Branch:** `sprint-038-geocore-communications`
**Baseline:** `8d0efd2` (Sprint 036 closeout, merge of `#23`, `origin/main`)
**Worktree:** isolated at `SMC-OS-sprint-038` (sibling of the main checkout), created via
`git worktree add -b sprint-038-geocore-communications <path> origin/main`

**Naming note.** A different, pre-existing "Sprint 037" (`sprint-037-commercial-security-ai`
— commercial launch, identity security, billing trial) is already in progress in a separate
worktree (`SMC-OS-sprint-037`, last commit `dd07d3e`, Phase A in progress with real
uncommitted changes). This sprint is deliberately numbered **038**, confirmed with the
product owner, to avoid colliding with that work. Nothing in that worktree was read for
implementation details, modified, or touched.

---

## 1. Mission

Turn Sprint 036's automation *detection* foundation into a real communication and
*execution* system:

> "GeoCore detects that work needs doing" → "GeoCore can safely execute approved
> business communication, record what happened, recover from failures, and continue the
> workflow."

Primary commercial journey this sprint targets:

```
Customer/Lead → Quote created → Quote sent → Delivery recorded → No response →
Follow-up due → GeoCore executes the follow-up → Delivery recorded → Quote approved →
Project created → Team/customer communication continues → Project completed →
Review request becomes available
```

GeoCore remains "the AI operating system for construction & renovation businesses."
Stone & Worktops remains a specialist trade workflow — untouched by this sprint's core
communications work (§15's trade-neutral pipeline is deliberately scoped separately,
see §7).

---

## 2. Discovery — what actually exists today

Discovery was performed by three parallel read-only audits against the real repository
at `8d0efd2`, each citing exact files/lines, plus a direct read of
`docs/DNS_GEOCORE_ONE.md` in full. Synthesized findings below; every claim traces to a
specific file.

### 2.1 Outbound communication — genuinely does not exist

Confirmed by grep across `app/` for `smtp|sendgrid|resend|postmark|mailgun|ses|twilio`
and by the codebase's own documentation:

- `docs/DNS_GEOCORE_ONE.md:118-121`: "If GeoCore ever sends transactional email itself
  (it does not today — no SMTP client, no email-provider integration anywhere in
  `app/`)..."
- `docs/SPRINTS/sprint-036.md` §10.1 (its own forward-looking note for this sprint):
  "no provider dependency, no configuration, no code path anywhere in the repository.
  Invitations, quote sending and review requests are all manual link-sharing today."
- `requirements.txt`: zero email/messaging packages. Nothing installed-but-unused.
- `.env.example`, `deploy/railway/staging.env.example`, all three `deploy/railway/*.toml`:
  zero email/SMTP/provider variables. The only "email"-named var anywhere is
  `SEED_ADMIN_EMAIL`, unrelated to sending.

There is nothing to wire up — this sprint builds the provider integration from scratch.

### 2.2 The "ships dark until configured" convention (must be followed exactly)

`app/core/config.py:91-111` — the established pattern for every optional third-party
integration:

- `openai_api_key: str | None = None` — `app/quotes/ai_draft.py`'s `AIDraftService`
  constructs its client lazily, only on first real use, only if the key is set. Never a
  startup dependency.
- `stripe_secret_key` / `stripe_webhook_secret` / price IDs — same shape; unset means
  `app/billing/router.py` returns 503 for anything Stripe-dependent, not a boot error.

Settings-field naming convention (`app/core/config.py:49-111`, full current list):
`app_env, seed_data_enabled, cors_allowed_origins, readiness_timeout_seconds,
database_url, jwt_secret_key, jwt_algorithm, jwt_expire_minutes,
login_rate_limit_max_attempts, login_rate_limit_window_seconds, seed_admin_email,
seed_admin_password, invitation_expire_days, portal_link_expire_days, upload_dir,
openai_api_key, openai_model, stripe_secret_key, stripe_webhook_secret,
stripe_price_pro_monthly, stripe_price_pro_annual, stripe_price_business_monthly,
stripe_price_business_annual, frontend_base_url`. New provider config follows the same
`snake_case`, `<provider>_api_key` / `<provider>_webhook_secret`, all-optional shape.

**A missing email provider key must degrade the same way**: `draft_message` and any
"Send quote" UI must stay fully functional in preview/draft form; only the actual
transmission step is gated, and it fails honestly (visible "delivery unavailable" state)
rather than silently or falsely.

### 2.3 DNS and Microsoft 365 mail — read in full, nothing touched

Full text of `docs/DNS_GEOCORE_ONE.md` read directly (not summarized by an agent, given
the stakes). Registrar: GoDaddy. Mail: Microsoft 365, GoDaddy-brokered. Live records that
**must never be modified or removed** by this sprint:

| Type | Host | Live value |
|---|---|---|
| MX | `@` | `0 geocore-one.mail.protection.outlook.com.` |
| TXT (SPF) | `@` | `v=spf1 include:secureserver.net -all` |
| TXT (verification) | `@` | `NETORGFT21096048.onmicrosoft.com` |
| TXT (DMARC) | `_dmarc` | `v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;` |
| CNAME | `selector1._domainkey` | `selector1-geocore-one._domainkey.netorgft21096048.w-v1.dkim.mail.microsoft.` |
| CNAME | `selector2._domainkey` | `selector2-geocore-one._domainkey.netorgft21096048.w-v1.dkim.mail.microsoft.` |
| CNAME | `autodiscover` | `autodiscover.outlook.com.` |

**The SPF trap, stated explicitly in that doc** (§3, lines 117-121): a DNS zone holds
exactly one SPF TXT record. If a new provider's SPF requirement were added at the apex
(`@`), it would have to be *merged into* the existing record
(`v=spf1 include:secureserver.net include:<provider> -all`) — a second `@` TXT record
named "SPF" breaks Microsoft 365 mail outright. This sprint avoids that risk entirely by
sending from a **dedicated subdomain** instead of the apex — see §4.2. Zero apex records
are touched by this sprint's design.

### 2.4 In-app notifications — real, but email-blind

`app/notifications/` (`models.py`, `service.py`, `repository.py`, `router.py`). Backed by
Postgres since Sprint 002 (ADR-001). `NotificationCreate` has `title`, `message`, `type`,
`recipient_user_id` (nullable = tenant-wide), `source_type`/`source_id`, and a
`dedupe_key` — the exact idempotency primitive this sprint's message ledger should mirror.
**No channel field exists** (no in-app vs. email distinction today).

### 2.5 Automations — internal-only by design, with an honest forward-declared toggle

`app/automations/actions.py:1-25` docstring: "None of them transmits anything to a
customer... GeoCore has no outbound email, SMS or messaging infrastructure." Four action
types today, all internal:

- `create_notification` — in-app notification row.
- `create_task` — internal follow-up task row.
- `draft_message` — writes a *task* containing drafted text for a human to manually
  send; explicitly not a transmission (docstring: "it does not quietly start
  transmitting").
- `create_project_from_quote` — delegates to `quote_service.handoff`.

There is no `AutomationMeta` Python class, but there is a real, already-shipped
structured API field: `GET /automations/meta` returns
(`app/automations/router.py:62-69`):

```json
"delivery": {
  "external_delivery_available": false,
  "note": "Automations act inside your workspace only. GeoCore does not send email, SMS or messages to customers; a drafted message is prepared for a person to review and send."
}
```

This is the exact, already-built toggle point: flipping `external_delivery_available`
to `true` (once a real provider is configured) is what lets the frontend change its own
copy and expose customer-facing send actions, per Sprint 036's own design intent.

### 2.6 Delayed "wait N days, check a condition" mechanism already exists

`app/automations/scan.py` — for quotes (lines 80-129): pulls all `sent` quotes,
computes a lookahead window relative to `quote.valid_until`, fires only while the quote
is still in a chaseable status (`{"sent"}`), and is idempotent per time-window via a
`discriminator` string fed into `automation_engine.run_for_subject`. **This is precisely
the mechanism** a "3 days after `quote.sent`, if still unanswered, send follow-up"
trigger extends — a new `SCAN`-kind trigger plus a `_scan_*` method keyed off
`quote.sent_at` rather than `valid_until`.

`app/automations/engine.py:22-24,132-136`: every dispatched action gets its own
`dedupe_key=f"{key}#{index}"`, so a partially-failed run can be safely re-run without
double-creating side effects. No automatic scheduled retry/backoff exists yet — only
idempotent re-run safety. A real delivery worker needs to add the former on top.

### 2.7 Webhook precedent — Stripe, directly reusable pattern

`app/billing/router.py:148-162`: `POST /webhook`, public, unauthenticated
(`include_in_schema=False`), reads raw payload + `stripe-signature` header.
`app/billing/service.py:147-161`: verifies via `stripe.Webhook.construct_event(...)`
inside try/except → 400 on bad signature, 503 if `stripe_webhook_secret` unset.
Idempotency: `crud.mark_stripe_event_processed(db, event["id"], event["type"])` is a
no-op on replay. **This exact shape — verify signature first, then idempotency-key
check — is the template for the email provider's delivery/bounce webhook.**

### 2.8 Jobs / scheduled execution — an established, provider-agnostic pattern

`app/jobs/follow_up.py` — CLI entrypoint (`python -m app.jobs.follow_up`), deployed per
`docs/SPRINTS/sprint-031.md` as its own dedicated Railway cron service
(`simo-follow-up-production`, `cronSchedule: "0 3 * * *"`, no public domain, non-root,
`DATABASE_URL` via `RAILWAY_PRIVATE_DOMAIN` reference — configured directly on the
Railway service, not in a checked-in `.toml`). Idempotent via a `dedupe_key`
unique-constraint check in `app/notifications/follow_up_service.py`, with the comment
that a concurrent-run race is caught by the DB constraint itself, not app-level locking.

`app/jobs/automations.py` — same CLI shape, drives `app/automations/scan.py`; not
confirmed wired to its own Railway cron service in-repo (only `follow_up`'s cron is
documented). **This sprint's delivery-retry worker should follow the same
one-dedicated-service pattern** — a new Railway service, same app image via
`git archive` + `railway up` (per the established clean-commit deploy procedure), narrow
`startCommand`. New billed Railway resources are an owner-approval-gated action per
Sprint 031 precedent — flagged in §4, not created without confirmation.

### 2.9 Invitations — copy-paste link only, single-use, role hardcoded

`app/database/models.py:626-653` `Invitation`: `token_hash` (sha256 of an opaque
`secrets.token_urlsafe(32)`), `status` ∈ `{"pending","accepted","revoked"}` ("expired" is
derived from `expires_at`, never stored), single-use via a status-check-then-flip on
accept (`app/invitations/service.py:111-134`). The raw token is returned exactly once,
in the create-invitation HTTP response — no delivery mechanism exists; staff copy the
link themselves. **Role is hardcoded to `STAFF` always**
(`app/invitations/service.py:78`) — the "role" column exists but isn't settable yet,
confirmed by the router's own docstring. Frontend consumer route already exists:
`apps/web/app/invite/[token]/page.tsx`.

### 2.10 Quotes and the portal — more groundwork already exists than expected

`app/database/models.py:261-266`: `Quote.status` is a plain string, default `"draft"`,
**with `sent_at`, `approved_at`, `approved_by_user_id` columns already present** —
`"sent"` is a real, already-modeled status (added for Sprint 036's `quote.sent`
automation trigger and its "follow up unanswered quotes" template,
`app/automations/templates.py:33-56`). **No code path currently sets `sent_at` via an
actual send** — it appears to be flippable today only through a manual
status-update path, not a delivery event. This sprint must find and lock down that exact
call site so a failed delivery can never leave a quote silently marked `"sent"`.

Quotes reach customers via `PortalLink` (`app/database/models.py:656-686`) — reusable
(not single-use, unlike `Invitation`), `status` ∈ `{"active","revoked"}`, same
opaque-token-hash convention. `POST /portal-links` is available to any authenticated
user (not Owner-gated). The public token routes return the customer's
projects/quotes and stream the invoice PDF
(`app/portal/router.py:93-150`). **This is the existing safer architecture the sprint
brief itself points at** ("use the existing secure customer portal... rather than
emailing sensitive quote data unnecessarily") — the quote-send email should link to a
portal link, not attach the full PDF by default.

`app/quotes/pdf.py`'s `PDFGenerator.create()` is download-only today (reportlab,
in-memory `bytes`, streamed as an attachment response) — no send path exists yet, which
is expected.

### 2.11 Project pipeline — confirmed stone-shaped, and confirmed why it's risky to rename in place

`app/projects/models.py:10-21`: `ProjectStatus(str, Enum)` =
`ENQUIRY, QUOTED, BOOKED, TEMPLATED, FABRICATED, INSTALLED, COMPLETE`. `ProjectService
.update_status` (`app/projects/service.py:129-182`) enforces a **strict linear
sequence** — only the exact next value is accepted; any skip/repeat/backward move raises
`InvalidProjectTransitionError`; the status write and its `PROJECT_STATUS_CHANGED`
activity-log row happen in one transaction, with automation dispatch firing
*after* commit. `PipelineCounts` (`app/dashboard/service.py:29-30`) iterates
`for status in ProjectStatus`, directly coupled to the enum's member set.

`ActivityLog` rows (`app/activity/repository.py:97-126`) store the status-change
`description` as a **plain-text f-string interpolated at write time**
(`f"Project {project_id} moved from {previous_status} to {status.value}"`) — the literal
English words are baked into old rows forever, not re-derived from the enum at read
time. **This is good news for a rename**: existing historical rows keep reading
correctly regardless of what the enum's members become, because they never re-resolve
against it. What *is* genuinely risky is the linear-sequence engine and the
`PipelineCounts` dashboard contract, which are both tightly coupled to the exact member
set — changing either requires a deliberate, tested migration with a value mapping, not
a find-and-replace. See §7 for why this sprint treats it as a separately-paced
sub-effort rather than folding it into the same PR as email infrastructure.

### 2.12 Test conventions

`tests/conftest.py`: `client` (TestClient wrapper), `db` (raw session), `auth_headers`
(seeded admin login), `other_tenant_auth_headers` (isolated second tenant, explicit
FK-safe cleanup). External API mocking: the service module's private client attribute is
replaced directly with `unittest.mock.MagicMock` (`billing_service._stripe = MagicMock()`,
`ai_draft_service._client = mock_client`); config values are set via
`monkeypatch.setattr(settings, ...)`. No `responses`/`respx`, no real network calls in
tests, ever. The email provider client must follow the identical shape: a
module-level lazily-constructed `_client`, swapped for a mock in tests.

---

## 3. Locked contract

Binding for this sprint, derived directly from discovery:

1. **No provider account or DNS record is created without owner confirmation** (§4).
   Everything provider-independent proceeds now; everything provider-dependent stops at
   that gate.
2. **Sending subdomain, not apex.** All new mail infrastructure lives under a dedicated
   subdomain (proposed: `send.geocore.one`, confirmed in §4). Zero existing Microsoft
   365 records (`@` MX/SPF/verification, `_dmarc`, `selector1/2._domainkey`,
   `autodiscover`) are read, modified, or removed by this sprint.
3. **"Ships dark until configured"**, exactly matching `openai_api_key`/
   `stripe_secret_key`: every new setting is `str | None = None`; the app boots and
   runs fully normally with none set; delivery-dependent endpoints return a truthful
   503/unavailable state, never a fake success.
4. **A quote/invitation is never marked "sent" on anything less than a confirmed
   provider-accepted send.** A failed transmission leaves status exactly where it was
   before the attempt, with a visible failure record.
5. **Every outbound message is auditable** — no communication leaves the system without
   a `Message` row recording who/what/when/status.
6. **Idempotency everywhere a retry can happen** — worker re-runs, webhook redelivery,
   and duplicate user clicks must not produce duplicate sends, mirroring the
   `dedupe_key`/`discriminator` patterns already proven in `app/notifications` and
   `app/automations`.
7. **Tenant isolation and RBAC are extended, never weakened** — every new table carries
   `tenant_id`; every new route is added to `tests/test_rbac_matrix.py`.
8. **The trade-neutral project pipeline (§15 of the brief) is treated as its own
   carefully-paced sub-effort**, not bundled into the same PR as email infrastructure —
   see §7 for the reasoning, which follows the same risk-separation logic Sprint 036 §10.2
   already used to defer it once, and that the sibling Sprint 037 branch's own phased
   structure (Phase A–E, separate PRs) independently confirms is this repo's preferred
   pattern for security/data-sensitive work.
9. **GeoCore AI drafts; it never sends.** Automation delivery actions execute
   independently of the AI, per an explicit human trigger or a configured automation
   only.
10. **No production email testing against real customers.** All provider integration
    tests use mocks; any live-send smoke test during staging/production verification
    uses an explicitly owner-designated test mailbox, never a real tenant's customer.

---

## 4. Provider and DNS decision — OWNER GATE

Per the brief's own instruction ("If a provider is not already selected/configured,
stop before requiring a paid external account or DNS mutation and report"), this is the
smallest point requiring owner action. Everything provider-independent (§7 Phase 1)
proceeds without waiting on this.

### 4.1 Recommended provider: **Resend**

| | |
|---|---|
| Why | Domain verification is subdomain-first by design (exactly matches §4.2's isolation strategy), a real free tier (3,000 emails/month, 100/day) sufficient for this stage, first-class webhook support for `delivered`/`bounced`/`complained`/`failed` events with HMAC-signed payloads (directly reusable against the Stripe webhook pattern in §2.7), a plain HTTP API with no heavyweight SDK dependency, and an approval process that doesn't gate transactional use the way some competitors do for a new account. |
| Alternative | **Postmark** — excellent transactional deliverability reputation specifically, but stricter new-account approval and no meaningful free tier; a reasonable fallback if Resend's account approval or deliverability doesn't work out in practice. |
| Required account | A Resend account tied to an email the owner controls (not this session — no account is created without the owner doing so, since it becomes the durable owner of a production sending identity). |
| Required API key | One `RESEND_API_KEY`, generated after domain verification, stored only as a Railway secret on `simo-api-staging`/`simo-api-production` — never committed, never logged. |

### 4.2 Required DNS — all under a new subdomain, zero existing records touched

Proposed sending subdomain: **`send.geocore.one`**. Resend (like every reputable
transactional provider) issues exact record values only after the domain is added in
their dashboard — the table below is the standard shape; exact values are generated at
setup time and will be confirmed before being handed to the owner as a final checklist:

| Type | Host | Value | TTL | Purpose | Action |
|---|---|---|---|---|---|
| TXT | `send.geocore.one` | `v=spf1 include:amazonses.com -all` (Resend's actual SPF include, confirmed at setup) | 600 | SPF for the sending subdomain only | **ADD** |
| CNAME ×3 (typical) | `resend._domainkey.send.geocore.one` (exact selector name confirmed at setup) | provider-issued | 600 | DKIM for the sending subdomain | **ADD** |
| TXT | `_dmarc.send.geocore.one` | `v=DMARC1; p=none; rua=mailto:<owner-chosen address>` (start at `p=none` — monitor before enforcing) | 600 | DMARC scoped to the subdomain only | **ADD** |

**Every existing record in §2.3 — `@` MX/SPF/verification, `_dmarc` (the apex one),
`selector1._domainkey`, `selector2._domainkey`, `autodiscover` — is KEEP, unmodified,
untouched.** None of the new records share a name with any existing one (`send.
geocore.one` and `_dmarc.send.geocore.one` are disjoint from `@` and the bare
`_dmarc`), so there is no collision to get wrong, and the "SPF trap" in §2.3 never
applies — this sending subdomain gets its own single SPF record, entirely separate from
the apex's existing one.

### 4.3 Owner actions required, in order — CLEARED

1. ~~Confirm the provider choice~~ — Resend, confirmed.
2. ~~Create the provider account~~ — done by the owner.
3. ~~Add `send.geocore.one` as a verified sending domain~~ — **verified in Resend**,
   confirmed by the owner.
4. ~~Apply those exact records in the GoDaddy DNS panel~~ — done; per the owner, no
   existing Microsoft 365 record was touched.
5. ~~Confirm domain verification succeeds~~ — confirmed.
6. ~~Generate a production API key; provide it to be set as a Railway secret~~ —
   `RESEND_API_KEY` is set on both `simo-api-staging` and `simo-api-production`,
   confirmed by variable name only via `mcp__railway__get-service-config` (never a
   value — the tool doesn't return one). This session has not requested, seen, printed,
   logged, or committed either key.
7. A safe test-recipient mailbox for the live-send verification in §11.7/§12 is still
   needed before that step — not yet confirmed.

**Still outstanding, and expected to become its own checkpoint once staging is
verified**: creating/configuring the actual webhook endpoint in the Resend
dashboard (exact URL + events + resulting `RESEND_WEBHOOK_SECRET`) — §11.1 built the
receiving endpoint, but only the owner can create the sender-side webhook
registration. This will be presented as an explicit stop, not guessed.

---

## 5. Communication data model (built, Phase 1)

**Naming correction from this document's own first draft**: §2.9 originally called this
"the messages table". It isn't — `messages`/`Message` already exist
(`app/database/models.py`, Sprint 017/ADR-033: portal customer↔staff chat). Building a
second, unrelated thing under the same name would have been a real collision (same table
name, same Python class name, genuinely different concept). The implemented table is
**`communications`** / `app.database.models.Communication`, migration
`a1b2c3d4e5f6_add_communications_and_email_suppressions` (down-revision
`d5e6f7a8b9c0`, the sole existing head — no branch created). Verified via offline
`alembic upgrade/downgrade --sql` (no live DB available in this environment; see §8) —
both directions generate clean, additive-only SQL with no changes to any existing table.

Built exactly as designed, tenant-scoped, following the `Notification`/`Invitation` token
and dedupe conventions already proven in this codebase:

- `id`, `tenant_id` (indexed, NOT NULL — every query filters by it, per contract §3.7)
- `customer_id`, `quote_id`, `project_id`, `invitation_id`, `automation_id`,
  `automation_run_id` — all nullable FKs, indexed, and all `ondelete="SET NULL"` (an
  audit ledger must not block or cascade-delete when its subject is hard-deleted — see
  the model's own docstring; `tenant_id` deliberately has no such override)
- `channel` (`"email"` only initially — no SMS/WhatsApp toggle before those channels
  exist, per the brief's own §16 instruction)
- `direction` (`"outbound"` only initially)
- `message_type` (`invitation`, `quote_sent`, `quote_follow_up`, `project_confirmation`,
  `project_update`, `project_completion`, `review_request` — `app.communications.models
  .CommunicationType`)
- `recipient`, `sender_identity` (rendered tenant display name/reply-to, never a raw
  credential)
- `subject`, `body_html`, `body_text` (the content actually sent, snapshotted at send
  time — never re-rendered from live data later, so history stays accurate even after a
  template or the underlying quote/project changes)
- `provider`, `provider_message_id` (nullable until accepted), `status` (`draft`,
  `queued`, `sending`, `sent`, `delivered`, `failed`, `bounced`, `suppressed` —
  `app.communications.models.CommunicationStatus`; **`delivered` is reserved for a
  verified provider webhook event — nothing in Phase 1 ever sets it, since no webhook
  endpoint exists yet (Phase 2)**)
- `attempt_count`, `last_attempted_at`, `failure_category` (`transient`/`permanent`/
  `suppressed`/`unavailable` — the last one distinct on purpose: a worker must never
  busy-retry a send that was never actually attempted against a provider because none was
  configured), `failure_detail` (short, safe, user-facing text — never a raw provider
  response body or stack trace)
- `dedupe_key`, enforced by a `UNIQUE(tenant_id, dedupe_key)` **database constraint**,
  not merely a pre-check in code — same defence-in-depth pattern Sprint 036 already
  established for `tasks.dedupe_key`/`automation_runs.dedupe_key`
- `created_at`, `updated_at`

A second table, `email_suppressions` (tenant-scoped, `UNIQUE(tenant_id, email)`), was
added in the same migration — see §7.

No API key, token, or credential is ever stored on either table (contract §3; confirmed
by reading every column definition — none exists).

---

## 6. Delivery abstraction (built, Phase 1)

```
DeliveryService (app/communications/service.py)
  → EmailProvider (app/communications/provider.py — ABC: send())
    → ResendEmailProvider (concrete, lazily constructed over plain httpx —
      already a dependency, no new SDK — same shape as
      AIDraftService/BillingService's vendor clients)
```

`DeliveryService.send()` is the only thing `app/invitations` calls this phase (Phase 3
adds `app/quotes` and `app/automations` callers). No caller anywhere imports a provider
SDK directly. Ordering inside `send()` is deliberate and tested (`tests/test_communications
.py`): dedupe check first (a retry returns the existing row, provider never called
again) → suppression check next (a suppressed recipient is recorded as `suppressed`
without ever reaching the provider) → the `communications` row is written with status
`queued` and committed *before* the provider is called, so a crash mid-send still leaves
an inspectable row → only then is the provider invoked, and the row updated in place
with the real outcome. If `resend_api_key` is unset, `ResendEmailProvider` raises
`EmailProviderUnavailable`, which `DeliveryService` turns into a truthful
`failed`/`unavailable` row — never a fake success, and never raised back out to the
caller (an invitation is created successfully either way; see §7).

`ResendEmailProvider.send()` classifies a provider response into `ACCEPTED` (2xx),
`TRANSIENT_FAILURE` (429, 5xx, or a network/timeout error — retry may help), or
`PERMANENT_FAILURE` (any other 4xx — a bad request/key/unverified sender that a retry
cannot fix). Covered by `tests/test_communications.py::TestResendEmailProvider` against
a fake HTTP client (no real network call anywhere in the test suite).

`resolve_sender_identity()` reuses `app.tenants.identity.resolve()`'s exact display-name
fallback chain (trading name → legal name → workspace name) so the name a customer sees
in their inbox matches the name on their PDF letterhead, and never sends "From" a
tenant's own address (no way to verify a tenant controls it) — always
`"{Tenant} via GeoCore" <noreply@send.geocore.one>`, Reply-To the tenant's own
`contact_email` when set.

---

## 7. What Phase 1 actually built

Everything below is implemented, tested (against mocks — no real provider account
exists yet), and merged to this branch. Nothing here required the §4 owner gate.

- **`app/communications/`** — the full module: `models.py` (Pydantic:
  `CommunicationStatus`, `CommunicationType`, `FailureCategory`, `CommunicationOut`,
  `EmailSuppressionOut`), `provider.py` (`EmailProvider`, `ResendEmailProvider`,
  `resolve_sender_identity`), `templates.py` (all seven system templates — invitation,
  quote sent, quote follow-up, project confirmation, project update, project completion,
  review request — each escaping every piece of tenant/customer/quote content through
  `html.escape()` before it reaches markup; only `render_invitation` is called from
  anywhere yet), `service.py` (`DeliveryService`), `router.py` (read-only
  `GET /api/v1/communications` history endpoint, filterable by customer/quote/project/
  invitation — `AUTHENTICATED`, same posture as `app/tasks`).
- **Migration** `a1b2c3d4e5f6` — `communications` + `email_suppressions` (§5).
- **`app/core/config.py`** — `resend_api_key`, `resend_webhook_secret`,
  `email_sending_domain` (default `send.geocore.one`), all optional, "ships dark"
  exactly like `openai_api_key`/`stripe_secret_key`.
- **`app/database/crud.py`** — `create_communication`, `get_communication_by_dedupe_key`,
  `update_communication_result`, `list_communications`,
  `get_latest_communication_for_invitation`, `get_email_suppression`,
  `create_email_suppression`, `list_email_suppressions`.
- **Invitation flow rewrite** (`app/invitations/service.py`,
  `app/invitations/router.py`, `app/invitations/models.py`) — `create_invitation()` now
  renders and attempts to send a real invitation email via `DeliveryService`, using the
  raw (never the row id) token in the accept link. This is strictly additive: the
  manual-link fallback (`token` in the create response) is unchanged, and a delivery
  failure — including "no provider configured at all", which is every environment's
  reality until §4 is resolved — is caught and never prevents invitation creation from
  succeeding (`InvitationService._send_invitation_email`'s own docstring states this
  contract). `InvitationOut` gains `delivery_status`/`delivery_failure_detail`, populated
  by the router from the invitation's latest `Communication` row; `Invitation.status`
  itself (the pending/accepted/revoked membership lifecycle) is unchanged. **Role is
  deliberately still Staff-only** — the invitations router's own existing docstring
  already framed widening it as a materially bigger RBAC decision left to a future
  sprint, and that decision now specifically belongs to the sibling
  `sprint-037-commercial-security-ai` branch's "3-tier RBAC model" phase, not here;
  building a second, competing RBAC change in this sprint would risk directly
  conflicting with that in-progress work.
- **Tests** — `tests/test_communications.py` (new: `DeliveryService` send/dedupe/
  suppression/tenant-isolation, `ResendEmailProvider` response classification, sender
  identity resolution, template escaping) plus additions to `tests/test_invitations.py`
  (the email attempt happens, survives an unexpected `DeliveryService` exception, uses
  the raw token not the row id, and the honest `delivery_status` reaches the API
  response). `tests/test_rbac_matrix.py` gains the new route row (`GET
  /api/v1/communications`, `AUTHENTICATED`), per this repo's own contract that every new
  route is registered there.
- **Cross-cutting fix, found during implementation**: three existing test files
  (`tests/test_invitations.py`, `tests/test_billing.py`, `tests/conftest.py`'s
  `other_tenant_auth_headers`) create real invitations and hard-delete their tenant in
  cleanup. Once invitation creation started writing a `Communication` row, that would
  have failed those cleanups on the tenant-delete step (an FK referencing a still-NOT
  -NULL `tenant_id`). Fixed by (a) making every *subject* FK on `communications`
  `ondelete="SET NULL"` (§5) so a hard-deleted quote/invitation/etc. never blocks or
  silently destroys audit history, and (b) explicitly deleting `communications` rows
  before the tenant-delete step in all three affected cleanup functions, matching the
  established `ActivityLog`-before-`Tenant` pattern already in this codebase.

Deliberately not touched this phase (Phase 3, needs a live provider — §4, §9 below):
`app/quotes` (the existing manual `POST /quotes/{id}/send` "mark sent" endpoint is
untouched), `app/automations` (no new action types registered), any webhook endpoint,
any delivery-retry worker.

---

## 8. Local verification performed, and its limit

This environment has no Docker daemon and no local PostgreSQL, and no interactive shell
to install one via WSL (`sudo` requires a password this session doesn't have). What was
verified without a live database:

- `python -m py_compile` on every new/changed file — clean.
- `python -c "import app.main"` — the full app, including the new router registration,
  imports with no errors.
- `alembic heads` — `a1b2c3d4e5f6` is the sole head, chained cleanly after
  `d5e6f7a8b9c0`, no branch.
- `alembic upgrade/downgrade --sql` (offline mode, no DB connection) for the new
  migration in both directions — clean, additive-only SQL, correct `ON DELETE SET NULL`
  clauses present on every subject FK, no statement touches an existing table.
- `pytest --collect-only` — all 923 tests (892 existing + this phase's additions)
  collect with zero errors, confirming every new/changed test file imports and
  parametrizes correctly.

**Not yet verified locally**: actually running the test suite against a real Postgres
(dedupe/suppression/idempotency behaviour, the FK `ondelete` clauses firing correctly,
RBAC gate assertions). This repo's CI (`.github/workflows/ci.yml`) runs `alembic upgrade
head` then `pytest` against a real `postgres:16-alpine` service container — that is
where this phase gets its first real-database run, watched and iterated on before
merge, exactly as Sprint 036's own deployment work did for its own local-environment
gaps.

---

## 9. Phased delivery plan

Following this repo's own established pattern for security/data-sensitive multi-part
work (the sibling Sprint 037 branch's explicit phase table), Sprint 038 ships in
separate, independently-reviewable phases rather than one large PR:

| Phase | Scope | Depends on §4 owner gate? |
|---|---|---|
| **1** | Communications data model + migration, `DeliveryService`/`EmailProvider` abstraction (provider unset → honest unavailable state throughout), template system with escaping, invitation-flow rewrite (truthful pending/sent/failed/accepted/expired/revoked states, manual-link fallback preserved), full test suite for all of the above against mocks — **complete, §7** | No |
| **2** | Provider activation, webhook endpoint + signature verification + idempotent event handling wired to the suppression list — **complete, §11** | Was blocked on §4; **§4 resolved by the owner** (Resend account created, `send.geocore.one` verified, `RESEND_API_KEY` set on both Railway environments) |
| **3** | Quote delivery (real send via the portal-link pattern, retry-not-resend on repeat clicks), quote-follow-up automation (customer-facing action + template, reusing the existing `quote.expiring` scan trigger and its per-window dedupe), a delivery-retry sweep — **complete, §11** | No longer — folded into the existing `app/jobs/automations.py` cron entrypoint rather than a new Railway service (§11) |
| **4** | Communication history UI (customer/quote/project timelines), server-side notification-preference foundation (in-app/email only), GeoCore AI drafting integration (draft-only, never sends), full responsive sweep | Partially (history UI needs frontend work not started this pass; the read API itself has existed since Phase 1, §7) |
| **5** | Trade-neutral project pipeline — its own migration with a deterministic value mapping, `PipelineCounts`/dashboard contract update, upgrade/downgrade safety tests, stone-tenant behaviour preserved exactly. Deliberately last and separately reviewable: it is a schema-risk change to `projects` with no dependency on anything else in this sprint, exactly the kind of change Sprint 036 §10.2 already declined to bundle with a quote-model rewrite for the same reason. | No |

Password-recovery activation (brief §17): discovery did not find an existing,
blocked-only-on-delivery password-recovery flow in this codebase — that work belongs to
the sibling Sprint 037 (identity security), not here. Recorded and deferred explicitly,
not silently dropped.

---

## 11. What Phase 2 and Phase 3 actually built

The owner gate (§4) cleared: a Resend account exists, `send.geocore.one` is verified,
and `RESEND_API_KEY` is set as a Railway variable on both `simo-api-staging` and
`simo-api-production` (confirmed by variable **name** only —
`mcp__railway__get-service-config`, which never returns values — per the explicit
instruction not to request, print, log, expose or commit either secret). Everything
below was built and tested against mocks/fakes before touching either environment.

### 11.1 Webhook handling (`app/communications/webhooks.py`, `POST /api/v1/communications/webhook`)

Resend delivers webhooks via Svix; verification implements Svix's own publicly
documented HMAC-SHA256 scheme directly (no extra SDK, same "stdlib over a vendor
library where stdlib suffices" choice `provider.py` made for sending) — see that
module's docstring for the exact algorithm. A request with a bad signature, missing
headers, or a timestamp more than 5 minutes from now is rejected (400) before any
payload parsing happens. The route itself returns 503 if `resend_webhook_secret` isn't
set — "ships dark" applies here too.

Idempotency: `processed_email_events` (migration `b2c3d4e5f6a7`), the same
first-INSERT-wins shape as `processed_stripe_events`, keyed on the delivery's own
`svix-id` — a replayed delivery is acknowledged (200) without re-applying side effects.

### 11.2 Delivery/bounce/complaint tracking

`DeliveryService.record_webhook_event()` resolves the event to a `communications` row
by `provider_message_id` (globally unique, generated once by Resend — safe to look up
without a tenant, per that method's own docstring) and:

- `email.delivered` → `status = "delivered"`.
- `email.bounced` → `status = "bounced"`, **and** a suppression is created
  (`reason="hard_bounce"`) so this tenant never sends to that address again.
- `email.complained` → the communication's own status is left alone (it *was*
  delivered — that's what a complaint means) but a suppression is created
  (`reason="complaint"`).
- Anything else (`email.sent`, `email.opened`, `email.clicked`, or an event type this
  sprint doesn't recognise) is acknowledged and ignored — Resend must never see a
  different response for an event this service can't or doesn't need to act on, or it
  will keep retrying it.

### 11.3 Retry behaviour

`DeliveryService.retry()` re-attempts a `failed` row **in place** (same row, same
`dedupe_key` — never a second send) when its `failure_category` is `transient` or
`unavailable`; `permanent` and `suppressed` are deliberately never retried. Bounded at
`MAX_ATTEMPTS = 5` (brief §11's "no endless retries"). `retry_pending()` sweeps every
tenant's retryable failures and is called from the **existing**
`app/jobs/automations.py` cron entrypoint, right after its scan — no new Railway
service, per the brief's own "do not introduce unnecessary infrastructure" and this
job already running on a schedule against every tenant.

### 11.4 Quote delivery (`POST /quotes/{id}/send-email`)

Additive alongside the untouched Sprint 007 `POST /quotes/{id}/send` (still transmits
nothing — the deliberate manual fallback, unaffected either way). The new endpoint
creates a fresh portal link (a link's raw token is only ever returned once, so an
existing link's token can't be reused), emails it via `DeliveryService`, and marks the
quote `sent` **only** when the communication's own status is `sent` — a failed or
suppressed attempt leaves the quote exactly where it was and reports the real reason in
the response body's `communication` field. Clicking again after a transient failure
retries the same row (`DeliveryService.retry()`) rather than sending a second time;
clicking again after success is a true no-op (no new provider call).

### 11.5 Quote follow-up automation

A new customer-facing action, `send_quote_follow_up`
(`app/automations/actions.py`), and a new template, "Automatically email unanswered
quotes" (`quote_follow_up_email`), reusing the *existing* `quote.expiring` scan trigger
— no new trigger type needed. Added **alongside** the original "Follow up unanswered
quotes" internal-task template rather than replacing it: a tenant who already activated
that one keeps getting exactly an internal task, unchanged; automatic customer email is
an explicit second choice they turn on separately. The engine's own per-action
`dedupe_key` (derived from the run's discriminator — the expiry window) is reused
directly as `DeliveryService`'s dedupe_key, so a single quote can never receive two
automated follow-up emails for the same expiry window, even under a retried/concurrent
worker. `GET /automations/meta` now reports `customer_facing_actions` and an honest
`delivery.external_delivery_available` that reflects whether `resend_api_key` is
*actually* set, not a hardcoded value — verified by a monkeypatch-driven test in both
directions.

### 11.6 Scope note: invitation role widening still deliberately out of scope

`send_quote_follow_up` is the only new customer-facing action this phase. §9 of the
original Sprint 038 brief lists `send_email`/`send_quote`/`send_project_update`/
`send_review_request` as candidates too — those, and the frontend UI for any of this
(communication history timelines, a "review before sending" screen, notification
preferences), are Phase 4 and not started this pass. Invitation role widening remains
the sibling Sprint 037 branch's territory, unchanged from §7's original reasoning.

### 11.7 Local verification performed, and its limit (same constraint as §8)

`py_compile` clean on every new/changed file; `python -c "import app.main"` clean
(including the router split now needed for a mixed public/authenticated
`communications` router — the webhook cannot sit behind `Depends(get_current_user)` at
the router level, and the fix mirrors the shape `app/invitations/router.py` and
`app/billing/router.py` already document); `alembic heads` — `b2c3d4e5f6a7` is the sole
head; `alembic upgrade/downgrade --sql` clean and additive for the new migration;
`pytest --collect-only` — 960 tests (923 after Phase 1 + this phase's additions)
collect with zero errors. One real bug was caught only by re-running the import check
after an edit: a stray `__table_args__` had been left detached from its owning class by
an earlier edit's match boundary — fixed before it ever reached a commit. Real-database
verification (dedupe/retry/webhook-idempotency behaviour actually firing, the new
migration applying) happens in CI, then for real on staging with the now-configured
`RESEND_API_KEY` — see this doc's closeout section once that run completes.

---

## 12. Staging deployment and verification

Both PRs (#24 Phase 1, #25 Phase 2+3) merged to `main` with CI green (backend/frontend/
e2e, real Postgres) on every push and post-merge. Deployed the exact merge SHA
(`6b351f9`) to staging from a clean `git archive` export (Sprint 021's clean-commit
procedure), one service at a time:

| Service | Result |
|---|---|
| `simo-api-staging` | ✅ SUCCESS |
| `simo-web-staging` | ✅ SUCCESS |

- `alembic current` = `alembic heads` = `b2c3d4e5f6a7` (the sole head, chained cleanly
  through every prior migration). No drift.
- `/health` → `{"status":"healthy"}` (200); `/ready` → `{"status":"ready","database":"reachable"}` (200).
- `GET /automations/meta` on the live staging API: `delivery.external_delivery_available`
  is genuinely `true` (proves `RESEND_API_KEY` is read from the real Railway variable by
  the running process, not just present in config), `customer_facing_actions` =
  `["send_quote_follow_up"]`.
- `GET /api/v1/communications` reachable (200, authenticated).
- `POST /api/v1/communications/webhook` (no signature) → 503, honestly reporting
  `RESEND_WEBHOOK_SECRET` is not yet set — expected; see §13.

### Real controlled transactional-email test

Per explicit owner instruction, sent to the owner's own mailbox
(`alkawaritm@gmail.com`) — never a real customer address. Triggered via a fresh
synthetic tenant's real team invitation (`POST /invitations`), through the exact same
`DeliveryService` → `ResendEmailProvider` path every other send in this sprint uses:

- API response: `"delivery_status": "sent"`, `"delivery_failure_detail": null`.
- The underlying `communications` row: `status: "sent"`, `attempt_count: 1`,
  `provider: "resend"`, `provider_message_id: "8bb23d59-8cbb-43eb-bb54-69149c5b4041"` —
  Resend's own id for the message, confirmed by a direct read via `railway ssh`, proving
  a genuine external API acceptance rather than an internal state change.

**Staging verification: PASS.** No regressions found in this sprint's own new surfaces
or the existing suite (CI). Synthetic tenants/invitations created during this
verification are left in staging's database, consistent with how every prior sprint's
own staging verification has operated (staging is designed to hold synthetic data; no
delete endpoints exist for most of these rows).

---

## 13. Webhook registration — OWNER CHECKPOINT

The receiving endpoint (§11.1) is deployed and live on both environments, and correctly
refuses to process anything (503) until it has a signing secret. Only the owner can
create the sender-side registration in the Resend dashboard — this session will not
guess at it.

**For each environment, in Resend's dashboard → Webhooks → Add Endpoint:**

| | Staging | Production |
|---|---|---|
| **URL** | `https://simo-api-staging-staging.up.railway.app/api/v1/communications/webhook` | `https://api.geocore.one/api/v1/communications/webhook` |
| **Events to select** | `email.sent`, `email.delivered`, `email.bounced`, `email.complained` | same |

Do **not** select `email.opened` or `email.clicked` — nothing in this sprint processes
them (§11.2's own scope note); selecting them only adds webhook volume this service
will acknowledge and discard. `email.delivery_delayed` is optional — harmless to
include, currently a no-op here.

Each registration is a **separate endpoint with its own signing secret** (`whsec_...`)
— staging and production are two different URLs, so Resend issues two different
secrets. After creating each:

1. Copy that endpoint's signing secret.
2. Set it as `RESEND_WEBHOOK_SECRET` on the matching Railway service
   (`simo-api-staging` for the staging secret, `simo-api-production` for the production
   one) — never pasted into chat, never committed; set directly in Railway or handed
   over through whatever secure channel is preferred.

Once staging's secret is set, this session can verify the full loop for real (send →
webhook fires → `communications` row reaches `delivered`, or a deliberately-bounced test
address reaches `bounced` + a suppression row) before recommending production
promotion for the webhook path specifically. Production deployment of everything
*else* in this sprint is not blocked on this — see §14.

---

## 14. Status

**Phases 1–3 merged, deployed to staging, and verified for real** — migration applied
cleanly, health/readiness green, honest capability flags confirmed live, and a genuine
transactional email sent and accepted by Resend (§12). Not yet done: webhook secret
configuration (§13, owner checkpoint) and production deployment (gated on the owner's
own "successful staging verification" instruction, now satisfied for the send path;
production promotion is a decision being handed back rather than taken unilaterally).
Phase 4 (history UI, notification preferences, AI drafting) and Phase 5 (trade-neutral
pipeline) are not started.

**SPRINT 038 IN PROGRESS — Phases 1–3 merged and verified on staging with a real
transactional send. BLOCKED on the owner registering the Resend webhook (§13) for
delivery/bounce/complaint tracking specifically. Production deployment of the rest is
ready pending the owner's go-ahead.**
