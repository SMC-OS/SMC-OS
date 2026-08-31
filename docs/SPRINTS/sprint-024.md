# Sprint 024 — Notifications / Follow-up Automation

Status: **CONTRACT LOCKED — no production code, no migrations, no tests
written yet.** Locked per `docs/ROADMAP.md`'s reconciled v1.0 sequence.
See LOCKED CONTRACT at the end of this document.

Branch: `sprint-024-notifications-follow-up`
Baseline: `main` @ `36802bb` (Sprint 023 merge, confirmed via
`git rev-parse origin/main`)

## Objective

The system should automatically identify enquiries that have gone stale
with no progress, create exactly one actionable notification for the
right person, and let that person see it, navigate to the Project, and
mark it read — with zero duplicates no matter how many times the
automation runs.

## 1. Current-state findings (verified against `main` @ `36802bb`)

### A full notification stack already exists — but it is tenant-broadcast, not per-user

`NotificationRecord` (`app/database/models.py`): `id, tenant_id
(nullable), title, message, type (String, default "info"), read (bool),
timestamp`. **No recipient field, no source-entity link, no dedupe key.**
`NotificationService.list_all`/`unread_count` (`app/notifications/service.py`)
take only `tenant_id` — every user in a tenant sees and shares the read
state of every notification. The one existing automatic-notification
call site, `PortalService.handle_customer_message`
(`app/portal/service.py:216`), creates a tenant-wide broadcast on a new
portal message — there is no precedent anywhere for targeting one
specific user. This is the central gap Sprint 024 must close: a
follow-up naturally belongs to one person (the assignee or the Owner),
not the whole tenant.

### `NotificationType` is a UI severity, not a domain category

`app/notifications/models.py::NotificationType` = `success | warning |
info | error` — purely cosmetic icon/color selection
(`apps/web/components/shell/NotificationsPanel.tsx`'s `TYPE_ICON`/
`TYPE_TONE` maps). It is not a semantic event category like
`ActivityType`, and reusing it for that would conflict with its existing
meaning. A separate field is needed for "what kind of automated event
this is" / "what it links to."

### Frontend notification UI exists and is solid, but has no navigation

`NotificationsPanel.tsx` + `useNotifications.ts` (`apps/web/hooks/`):
real 5-second polling, unread badge, mark-read-on-click, pending-state
handling during the mark-read request. **Clicking a notification does
nothing but mark it read — there is no link to any entity.** This is the
other central gap: §14/§24's "clicking it navigates to correct entity"
requires adding safe, server-computed navigation, not a client-supplied
URL.

### Zero scheduler/cron/background-job infrastructure exists anywhere

Searched `app/`, `scripts/`, `requirements.txt`, `deploy/railway/*.toml`:
no Celery, no APScheduler, no RQ, no Redis, no Railway cron/scheduled-job
config. `deploy/railway/api.railway.toml`'s only automation-adjacent
entry is `preDeployCommand` (migrations, not periodic work). Sprint 024
is the first sprint to need any periodic-execution mechanism at all —
confirms the brief's own steer toward the smallest option: a pure domain
function wrapped by a CLI entrypoint, not a new heavyweight stack.

### `Project` (Sprint 006/023) is the only entity with both a lifecycle state and an assignee

`app/database/models.py::Project`: `status` (7-value pipeline, Sprint
006/023), `assigned_user_id` (nullable FK → `users.id`, Sprint 023),
`created_at`. No separate "last touched"/"last activity" timestamp
exists anywhere on `Project` (or anywhere in this schema — the
established convention, reconfirmed by every prior sprint's own
docstrings, is `created_at` only, with `ActivityLog` as the mutation
trail, never a duplicate mutation-timestamp column).

### `Quote` has no `Project`/assignee relationship

`app/database/models.py::Quote`: links only to `customer_id`. The `Project
→ Quote` link (`Project.quote_id`, Sprint 020) is one-directional and
only populated *after* handoff (i.e., after a quote is *approved* — an
unapproved quote almost never has a linked Project yet). A
"quote follow-up" rule would therefore almost always fall back to
"notify the Owner" with no way to exercise the assigned-Staff path —
a materially weaker vertical than one built on `Project`.

### `Appointment` (Sprint 022) also links to `Project`

`app/database/models.py::Appointment`: `project_id`, `scheduled_at`,
`status`. A "site visit reminder" rule is structurally viable (via
`Appointment.project_id → Project.assigned_user_id`) but is a
future-facing time window ("before it happens"), which is harder to
make deterministic and easy to test than a past-facing age check, and
duplicates none of the setup already needed for the enquiry rule.

### RBAC / auth

`app/notifications/router.py` already requires `get_current_user` on
every route (Sprint 012, ADR-029) — no route is currently
`require_role`-gated (any authenticated tenant member, Owner or Staff,
can read/write their tenant's notifications; `role=None` still passes
today since only authentication, not role, is checked). The automation
job itself will run outside any HTTP request — no router, no
`get_current_user`, no role check needed or wanted (§9's "should not
depend on an HTTP user role" — confirmed correct by the fact no such
dependency exists to reuse even if desired).

### Existing service/atomicity precedent

Sprints 021–023 established the caller-owned-transaction pattern
(`commit=False` → dependent write → one `commit()`) for *multi-write*
operations. `PostgresNotificationRepository.add()` currently does a
single `crud.create_notification()` call with its own immediate commit —
already atomic by virtue of being one write. This matters for §12/§22
below.

## 2. Candidate automation rules (evaluated per §4)

| Candidate | Recipient path exercises both branches? | Time direction | Deterministic testing | New schema needed |
|---|---|---|---|---|
| A. Stale enquiry follow-up | Yes — `Project.assigned_user_id` or Owner | Past-facing (age) | Easy — inject `now`, no row mutation needed | `Project` untouched; only `NotificationRecord` extended |
| B. Quote follow-up | No — `Quote` has no assignee path, almost always Owner-only | Past-facing (age) | Easy | Would need a new `Quote`↔recipient path |
| C. Upcoming site visit reminder | Yes — via `Appointment.project_id` | Future-facing (window before an event) | Harder — needs a due *window*, not just an age threshold | Reuses `Appointment`, but adds a second join hop |

**Selected: A — Stale Enquiry Follow-up**, alone. It is the smallest
vertical that genuinely exercises the full recipient-fallback contract
(§7) with no new joins beyond `Project` (already touched by Sprint 023),
needs zero changes to `Quote` or `Appointment`, and its past-facing
"has this sat untouched since X" check is trivially deterministic with
an injectable `now` — no synthetic future dates, no window-edge math.

B and C are **explicitly deferred**, not rejected — B's weak recipient
story and C's window-based complexity make either a worse *first*
automation rule than a *later addition once the machinery below proves
itself*. Both can reuse the exact same `NotificationRecord` extension,
dedupe strategy, and CLI-runner shape this sprint locks in.

## 3. Locked automation rule

**Stale Enquiry Follow-up.** A Project is eligible when:

- `Project.status == "enquiry"`, and
- `Project.created_at <= now - STALE_ENQUIRY_THRESHOLD` (locked at **7
  days** — a plain module-level constant, not configuration; the
  smallest coherent choice per §4, trivially adjustable later without a
  schema change since it's a plain Python `timedelta`).

`created_at` is used as the sole staleness signal because it is the
*only* per-Project timestamp this schema has ever had (§1) — inventing a
`last_touched_at` column would be the first mutation-timestamp column in
the entire schema, breaking an unbroken convention for a threshold this
sprint can satisfy without one. A Project that was enquiry-converted
(Sprint 021) but is still `status == "enquiry"` (that conversion never
changes `status`, by Sprint 021's own locked decision) is still correctly
eligible — "enquiry" is the actionable pipeline state regardless of
whether a Customer record exists yet.

## 4. Locked `NotificationRecord` schema extension

Four additive, nullable columns — existing rows (portal-message
broadcasts, anything seeded) remain valid with no backfill:

- `recipient_user_id: UUID | None` — FK → `users.id`, indexed. `NULL`
  means "tenant-wide broadcast" (today's only behavior, preserved
  exactly); set means "visible only to this user" (§7/§8/§9's isolation
  requirement).
- `source_type: str | None` — e.g. `"project"`. Named generically (not
  `project_id`) because this is the first "polymorphic" reference in
  this schema; a plain nullable `str`, not an enum, since only one value
  exists today and Decision-locking a full enum for a single member
  would be premature.
- `source_id: UUID | None` — **not** a foreign key (it can point to
  different tables depending on `source_type`, so a single FK constraint
  can't express it — same reasoning any polymorphic-association design
  requires). Tenant/existence validation happens at write time in the
  service, never assumed at the schema level.
- `dedupe_key: str | None` — **`UNIQUE`**. Postgres treats multiple
  `NULL`s in a unique column as distinct from each other, so existing
  and future non-automated notifications (which never set this) are
  unaffected. Automated notifications always set it; format locked below.

No change to `type` (stays the existing UI-severity enum; automated
follow-ups use `WARNING`, an existing member — "correct type" per §17's
acceptance criteria means exactly this).

### Dedupe key format

`f"stale_enquiry_follow_up:{project_id}"` — **no time-window component**.
Reasoning: `Project.status` only ever moves forward through the
Sprint 023-locked linear pipeline (enquiry → quoted → ... ), so a given
Project can become "newly stale while still in enquiry" **at most once
in its lifetime** — there is no way for it to leave `enquiry` and later
return to it. A per-project key is therefore already maximally precise;
adding a rolling window (e.g., `:2026-08-31`) would only let the *same*
still-stale enquiry generate a fresh notification every day the job
runs, which is explicitly not wanted (§6: "the same logical reminder
must not generate duplicate notifications"). This is a deliberate
simplification of the brief's example conceptual identity, justified by
this entity's specific (monotonic) lifecycle — B or C, if built later,
may need a real window component since their source data can recur.

## 5. Locked recipient contract

1. If `Project.assigned_user_id` is set → that user (Sprint 023 already
   guarantees they belong to the Project's own tenant — no re-check
   needed, but the service still re-validates as defence-in-depth, §8).
2. Else → the tenant's **Owner**, resolved as the earliest-created
   `role == "Owner"` user for that tenant (`crud.list_users_by_tenant`,
   already ordered by `created_at`, `UserRole.OWNER.value` filter, first
   match). Every tenant has exactly one Owner in current practice (the
   signup flow creates exactly one); this tie-break is documented for
   correctness, not because multiple Owners are expected.
3. If neither resolves (should be structurally impossible — every tenant
   has an Owner) → skip the Project entirely (`skipped_no_recipient`,
   not a crash) rather than create an unaddressed notification.

## 6. Locked tenant isolation

- The automation query is global (spans all tenants — it is an internal
  job, not a per-request HTTP handler), but every `NotificationRecord` it
  creates carries **that Project's own** `tenant_id` — never the
  runner's, never a default. `source_id`/`recipient_user_id` are both
  re-validated to belong to that same tenant before the insert (defence
  in depth beyond what Sprint 023 already guarantees for
  `assigned_user_id`).
- Read/write API isolation: `NotificationService.list_all`/
  `unread_count`/`mark_read` gain a `user_id` parameter. New filter:
  `tenant_id == caller.tenant_id AND (recipient_user_id IS NULL OR
  recipient_user_id == caller.id)`. A caller can never list, count, or
  mark-read another user's targeted notification, even within their own
  tenant — closes §7/§8/§9/§25's recipient-isolation requirement without
  touching the existing tenant-broadcast behavior at all (`NULL` rows
  keep matching for everyone, exactly as today).

## 7. Locked RBAC

- HTTP routes: unchanged — `get_current_user` only (existing behavior;
  no new `require_role` gate — reading/marking-read one's own
  notifications was never role-gated and Sprint 024 has no reason to
  start).
- Automation execution: no HTTP boundary at all. The CLI entrypoint
  calls the domain service directly against a plain DB session — no
  user, no token, no role, matching §9/§11's explicit instruction and
  the fact this codebase has never had a service-account/internal-role
  concept to reuse.

## 8. Locked transaction/atomicity contract

Per §1's finding: creating one `NotificationRecord` is already a single
atomic write (like the existing `PostgresNotificationRepository.add()`).
**No `ActivityLog` event is added** (§12's explicitly offered escape
hatch — "notification creation itself may already be sufficient
evidence"): the notification row already carries every fact an
`ActivityLog` row would (tenant, recipient, source, dedupe key,
timestamp), and a second audit trail duplicating a first with zero new
information is exactly the "noisy duplicated audit trail" §12 warns
against. Consequence: **no caller-owned multi-write transaction pattern
is needed this sprint** — each Project's notification insert
succeeds or fails independently within one automation run; a failure on
one Project must never block or half-write another Project's
notification (proven by a failure-injection test that a DB-level error
on one insert doesn't corrupt the run's aggregate counts or leave a
partial row).

## 9. Locked execution mechanism

- Domain service: `app/notifications/follow_up_service.py` —
  `FollowUpService.run(db: Session, now: datetime) -> FollowUpRunResult`
  (a small dataclass: `examined, created, skipped_existing,
  skipped_not_due, skipped_no_recipient`). Pure, fully unit-testable
  against any `db`/`now`, no I/O beyond the DB, no printing.
- CLI entrypoint: `app/jobs/follow_up.py` (first module in a new
  `app/jobs/` package — the brief's own suggested shape). `python -m
  app.jobs.follow_up`: opens one `SessionLocal()`, calls
  `follow_up_service.run(db, now=datetime.now(timezone.utc))`, prints
  the result's counts as one line of structured (JSON) output, exits
  `0` on success and **`1`** on any unhandled exception (no secrets in
  output — only counts).
- No new Railway service, no cron config, no public trigger endpoint
  (§11) — staging verification invokes the same CLI via `railway ssh`
  against the real staging DB, exactly like `alembic` commands already
  are today. Adding a persistent Railway cron service is explicitly
  deferred (§13 out-of-scope) — nothing in the locked scope requires one
  yet, and the brief only permits adding one "if the locked architecture
  requires it," which it does not.

## 10. Locked frontend contract

Reuse `NotificationsPanel.tsx`/`useNotifications.ts` unchanged in
structure; extend, not replace:

- `AppNotification` (`apps/web/types/notification.ts`) gains
  `source_type: string | null` and `source_id: string | null`.
- Clicking a notification: marks read (existing behavior, unchanged)
  **and**, if `source_type === "project"`, navigates to
  `/projects/{source_id}` — a server-computed, closed mapping from a
  fixed enum of known `source_type` values to a fixed route template,
  never a client-supplied or stored URL (§14's explicit safety
  requirement). Any other/unknown `source_type` (or `null`, today's only
  case) does not navigate — existing behavior for existing notifications
  is unchanged.
- No new "notification preferences" surface, no redesign of the panel —
  matches §13/§25's "do not build a full communications centre."

## 11. True E2E contract

Real Chromium + real Next.js + real FastAPI + real Postgres, no mocks,
no wall-clock waiting:

1. Sign up a fresh synthetic tenant/Owner (real API).
2. Create a Project (real API) — it starts at `status == "enquiry"`
   with `created_at = now`, which is *not yet* stale.
3. Run the real automation entrypoint (`python -m app.jobs.follow_up`)
   invoked as a subprocess against the same database, passing an
   explicit override so the rule evaluates as due **without waiting 7
   real days** — the service's `now` parameter is exactly what makes
   this possible without any sleep or fabricated row mutation (decided
   at RED-writing time: either a small `--now` CLI override for exactly
   this test/ops purpose, or a documented direct-DB `created_at`
   backdate for the synthetic row — whichever keeps the spec honestly
   "real API/DB, no product-code special-casing for tests," chosen
   during implementation).
4. Log in through the real UI.
5. Open the notifications panel — see the follow-up, unread.
6. Click it — verify navigation to `/projects/{id}` and that it is now
   marked read (via the real API response, not client state).
7. Reload — verify the read state persisted.
8. Run the automation entrypoint again — verify via the live API that
   exactly one `stale_enquiry_follow_up` notification exists for this
   Project (no duplicate).

## 12. Staging contract

Identical discipline to Sprints 022/023 (`docs/STAGING_RUNBOOK.md`):
clean-commit `git archive` + `railway up`, `/health`/`/ready`,
**`alembic current` must equal `alembic heads` before any browser
verification** (Sprints 020, 022, and 023 all hit CLI migration drift —
treat a fourth recurrence as expected, not surprising, and remediate via
the documented `railway ssh` path before proceeding). Automation
verified by invoking the real CLI entrypoint via `railway ssh` against
synthetic staging-only data — run twice, confirm no duplicate. No new
Railway service, no production deployment, no production scheduling.

## 13. Migration plan

One migration, generated via `alembic revision --autogenerate` from the
actual current `main` head (verified: `081460e0e63a`, Sprint 023) —
four nullable columns on `notifications` (`recipient_user_id`,
`source_type`, `source_id`, `dedupe_key`), one explicitly named FK
(`fk_notifications_recipient_user_id_users`, never left
autogenerate-unnamed, per every prior new-column migration's established
fix in this repo), one regular index on `recipient_user_id`, one unique
index on `dedupe_key`. Verified with `alembic heads`/`alembic check` and
a full downgrade→upgrade round-trip before use.

## 14. Explicit out of scope

Quote follow-up (candidate B) and site-visit reminders (candidate C) —
deferred, not rejected (§2). Email/SMS delivery of any kind. A
persistent Railway cron/scheduled-job service (the CLI entrypoint is
sufficient for this sprint; a scheduler wrapping it is future
infrastructure). Notification preferences/settings UI. Multiple
recipients per notification. Per-notification-type read-state tables
(the existing single `read` boolean is sufficient since every automated
notification targets exactly one user). Retrying/backoff logic for the
CLI job. Any change to `Quote` or `Appointment` schemas. Any Sprint
025-030 work.

## 15. Locked TDD sequence

1. First RED: eligible stale enquiry with an assigned Staff member →
   `FollowUpService.run` creates exactly one `NotificationRecord`,
   correct tenant/recipient/source/type/dedupe key, unread.
2. GREEN: migration + model extension + minimal `FollowUpService`/CLI.
3. RED/GREEN: run twice → second run creates zero additional
   notifications (`skipped_existing` increments).
4. RED/GREEN: DB-level uniqueness — a direct duplicate-`dedupe_key`
   insert attempt raises/is rejected at the DB layer, not just the
   service layer.
5. RED/GREEN: Project younger than the threshold → not eligible,
   `skipped_not_due`.
6. RED/GREEN: Project status != `enquiry` → not eligible at all
   (never counted as examined-and-skipped for the wrong reason).
7. RED/GREEN: cross-tenant — two tenants' stale enquiries each produce
   their own correctly-tenant-scoped notification, zero cross-talk.
8. RED/GREEN: recipient fallback — unassigned Project → tenant Owner
   receives it.
9. RED/GREEN: recipient — assigned Project → the assigned Staff member
   receives it, not the Owner.
10. RED/GREEN: failure safety — one Project's insert failing (injected)
    never corrupts another Project's already-committed notification in
    the same run.
11. Backend regression (full suite).
12. Frontend RED/GREEN: notification navigation (source-aware click),
    recipient-scoped list/unread-count/mark-read.
13. Frontend hardening: cross-user/tenant visibility, mark-read failure
    safety (existing pattern, extended).
14. True Playwright E2E.
15. Full local regression (backend, frontend, e2e, typecheck, lint,
    runtime-config, docker-contract, build, alembic heads/check).
16. Exact-head CI.
17. Staging deploy + migration verification + automation run (twice,
    no duplicate) + browser/security verification + smoke.
18. Docs closeout.
19. Final feature CI.
20. PR, explicit merge commit, origin/main verification, post-merge CI.

## LOCKED CONTRACT

- **Rule**: Stale Enquiry Follow-up only (candidates B/C deferred).
  Eligibility: `status == "enquiry"` AND `created_at <= now - 7 days`.
- **Schema**: `NotificationRecord` gains `recipient_user_id` (nullable
  FK → `users.id`), `source_type` (nullable `str`), `source_id`
  (nullable `UUID`, no FK), `dedupe_key` (nullable, `UNIQUE`). Migration
  from current main head `081460e0e63a`.
- **Dedupe key**: `f"stale_enquiry_follow_up:{project_id}"` — no window
  component, justified by the source entity's monotonic lifecycle.
- **Recipient**: `Project.assigned_user_id` if set, else the tenant's
  earliest-created Owner, else skip (never crash).
- **Isolation**: notification API filters `tenant_id == caller AND
  (recipient_user_id IS NULL OR recipient_user_id == caller.id)`;
  automation re-validates every entity's tenant before writing.
- **RBAC**: HTTP routes unchanged (`get_current_user` only); automation
  has no HTTP boundary and no role dependency.
- **Atomicity**: single-write-per-notification; no `ActivityLog` event;
  no multi-write transaction needed; one Project's failure never affects
  another's already-committed result within the same run.
- **Execution**: `app/notifications/follow_up_service.py` (pure,
  testable) + `app/jobs/follow_up.py` (thin CLI, `python -m
  app.jobs.follow_up`, exits `1` on unrecoverable failure). No new
  Railway service, no public trigger endpoint.
- **Frontend**: existing panel/hook extended with `source_type`/
  `source_id` and closed-mapping navigation-on-click; no redesign.
- **E2E**: real browser/API/DB, CLI automation invoked against real
  data, run twice to prove no duplicate, navigation and read-persistence
  verified live.
- **Out of scope**: everything in §14, unconditionally.

### Verdict

- **Automation rule selected: YES** — Stale Enquiry Follow-up.
- **Sprint 024 contract locked: YES.**
- **Ready for the first backend RED: YES.**
