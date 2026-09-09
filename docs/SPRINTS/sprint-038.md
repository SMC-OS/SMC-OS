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

### 4.3 Owner actions required, in order

1. Confirm the provider choice (Resend, or state a preference for Postmark or another).
2. Create the provider account (this session cannot and will not do this).
3. Add `send.geocore.one` as a verified sending domain in the provider's dashboard;
   copy the exact SPF/DKIM/DMARC record values it issues (they will differ slightly in
   selector names from the illustrative table above — provider-generated, not
   predictable in advance).
4. Apply those exact records in the GoDaddy DNS panel, additively — nothing existing is
   edited or removed.
5. Confirm domain verification succeeds in the provider dashboard (DNS propagation,
   typically minutes to a few hours).
6. Generate a production API key; provide it to be set as a Railway secret (never pasted
   into chat/committed — set directly in Railway, or handed over through whatever secure
   channel the owner prefers).
7. Confirm a safe test-recipient mailbox for staging/production live-send verification
   (never a real customer address).

**This session will not create the account, generate the DNS values, or touch DNS.**
Phase 1 (§7) proceeds in parallel and does not depend on this gate.

---

## 5. Communication data model (design, pending implementation)

A new `messages` table, tenant-scoped, following the `Notification`/`Invitation` token
and dedupe conventions already proven in this codebase:

- `id`, `tenant_id` (indexed, NOT NULL — every query filters by it, per contract §3.7)
- `customer_id`, `quote_id`, `project_id`, `automation_id`, `automation_run_id` — all
  nullable FKs, indexed where used for history lookups
- `channel` (`"email"` only initially — no SMS/WhatsApp toggle before those channels
  exist, per the brief's own §16 instruction)
- `direction` (`"outbound"` only initially; modeled as an enum for future inbound
  parity with the portal's existing two-way messaging)
- `message_type` (`invitation`, `quote_sent`, `quote_follow_up`, `project_confirmation`,
  `project_update`, `project_completion`, `review_request`)
- `recipient`, `sender_identity` (rendered tenant display name/reply-to, never a raw
  credential)
- `subject`, `body_snapshot` (the rendered content actually sent — a safe, immutable
  record; never re-rendered from live data later, so history stays accurate even if a
  template changes)
- `provider`, `provider_message_id` (nullable until accepted), `status` (`draft`,
  `queued`, `sending`, `sent`, `delivered`, `failed`, `bounced`, `suppressed` — only
  states Resend's API/webhooks can actually establish; **`delivered` is only ever set
  from a verified webhook event, never assumed from the send-API's 200 response**)
- `attempt_count`, `last_attempted_at`, `failure_category` (`transient`/`permanent`/
  `suppressed`), `failure_detail` (safe, user-facing text only — no raw provider
  stack traces)
- `dedupe_key` (unique index, tenant-scoped) — the idempotency primitive for both
  duplicate-click and duplicate-worker-retry prevention
- `created_at`, `updated_at`

No API keys, tokens, or credentials are ever stored on a message row (contract §3).

---

## 6. Delivery abstraction (design, pending implementation)

```
DeliveryService (domain layer)
  → EmailProvider (protocol/ABC: send(), classify_failure(), verify_webhook())
    → ResendEmailProvider (concrete, lazily constructed — same shape as
      AIDraftService/billing's Stripe client)
```

`DeliveryService` is the only thing `app/quotes`, `app/invitations`, and
`app/automations` ever call — none of them import a provider SDK directly. If
`resend_api_key` is unset, `DeliveryService` returns a typed "unavailable" result; no
caller ever fabricates a success state to work around it.

---

## 7. Phased delivery plan

Following this repo's own established pattern for security/data-sensitive multi-part
work (the sibling Sprint 037 branch's explicit phase table), Sprint 038 ships in
separate, independently-reviewable phases rather than one large PR:

| Phase | Scope | Depends on §4 owner gate? |
|---|---|---|
| **1** | `messages` table + migration, `DeliveryService`/`EmailProvider` abstraction (provider unset → honest unavailable state throughout), template system with escaping, invitation-flow rewrite (role becomes settable, truthful pending/sent/failed/accepted/expired/revoked states, manual-link fallback preserved), full test suite for all of the above against a mock provider | No |
| **2** | Provider wiring (`ResendEmailProvider`), webhook endpoint + signature verification + idempotent event handling, suppression list | **Yes — blocked until §4 is resolved** |
| **3** | Quote delivery ("Send quote" UI using the portal-link pattern, not a raw PDF attachment), quote-follow-up automation (delay + cancellation-on-approval + dedupe), new customer-facing automation actions (`send_email`, `send_quote`, `send_quote_follow_up`, `send_project_update`, `send_review_request`), delivery-retry worker as its own Railway service | Yes (needs Phase 2) |
| **4** | Communication history UI (customer/quote/project timelines), server-side notification-preference foundation (in-app/email only), GeoCore AI drafting integration (draft-only, never sends), full responsive sweep | Partially (history UI for real messages needs Phase 2/3 data) |
| **5** | Trade-neutral project pipeline — its own migration with a deterministic value mapping, `PipelineCounts`/dashboard contract update, upgrade/downgrade safety tests, stone-tenant behaviour preserved exactly. Deliberately last and separately reviewable: it is a schema-risk change to `projects` with no dependency on anything else in this sprint, exactly the kind of change Sprint 036 §10.2 already declined to bundle with a quote-model rewrite for the same reason. | No |

Password-recovery activation (brief §17): discovery did not find an existing,
blocked-only-on-delivery password-recovery flow in this codebase — that work belongs to
the sibling Sprint 037 (identity security), not here. Recorded and deferred explicitly,
not silently dropped.

---

## 8. Status

**Phase 0 (this document) complete.** Phase 1 (provider-independent groundwork) begins
next and does not wait on §4. Phases 2–3 are blocked on the owner resolving §4.
Overall sprint status while any phase is incomplete:

**SPRINT 038 IN PROGRESS — Phase 1 starting; Phases 2–3 BLOCKED on provider/DNS owner
action (§4).**
