# Sprint 028 — UAT + Bug-Fix Cycle

## Objective

Sprint 027 built the connected full-system E2E journey and closed the
verification/tooling gap across Sprints 020–026. Sprint 028 is the first
sprint whose sole purpose is **acceptance**, not construction: exercise every
shipped user journey as a real user would (real FastAPI, real Next.js, real
PostgreSQL, real Chromium — no mocks), record PASS/FAIL/BLOCKED against a
locked acceptance matrix, and fix only genuine product defects the matrix
surfaces. Sprint 028 does not add features. It proves the product that
Sprints 008–027 shipped actually works end to end, for both personas, across
tenant boundaries, locally and on staging.

## UAT philosophy

- **Evidence over assumption.** A row is PASS only when it was actually run
  against real infrastructure and its evidence is recorded, not because the
  underlying code "looks correct."
- **A failing test is a lead, not a verdict.** Every FAIL is triaged (Phase 8
  categories A–F) before any code changes. Test-authoring bugs, environment
  noise, and intended behavior are not product defects.
- **No silent omissions.** Every matrix row gets a disposition. A row that
  cannot be run is BLOCKED with a stated reason, never dropped.
- **Fix the defect, not the symptom.** Every genuine defect gets a UAT-XXX ID,
  a RED test proving it, a minimal GREEN fix, and a retest — mirroring the
  TDD discipline Sprints 020–027 already established.
- **Passing is a valid, sufficient outcome.** If the matrix comes back clean,
  Sprint 028 is not a failure for lacking code churn — acceptance evidence is
  the deliverable, not a fixed quota of bugs.

## Severity definitions (Phase 4 — LOCKED)

| Severity | Definition |
|---|---|
| **BLOCKER** | Cannot complete a core business journey; tenant/security breach; data corruption or data loss; production-launch blocker; authentication bypass; cross-tenant exposure; critical persistence failure. |
| **HIGH** | Important workflow completes incorrectly; persisted state is wrong; permission incorrectly granted or denied; significant user dead end; major idempotency/atomicity regression; a core user journey cannot be reliably completed. |
| **MEDIUM** | Workflow works, but usability/state/error handling is materially confusing; incorrect non-critical UI state; poor retry/failure handling that does not corrupt data; misleading operational feedback; important but non-blocking acceptance issue. |
| **LOW** | Cosmetic issue; wording/layout inconsistency; minor non-blocking usability issue; polish issue with no data/security/workflow impact. |

**Close condition:** Sprint 028 may close only when BLOCKER-open = 0 and
HIGH-open = 0. Any MEDIUM or LOW left unfixed must be explicitly recorded as
**accepted** or **deferred with rationale** in the closeout (§ below). Severity
is never downgraded to make the sprint easier to close — a real
security/data-integrity defect keeps its true severity regardless of exit
pressure.

## Defect handling rules

1. A FAIL is first classified as: (A) genuine product defect, (B) test/fixture
   issue, (C) environment issue, (D) operator mistake, (E) intended behavior,
   or (F) enhancement request. Only (A) becomes a UAT-XXX defect.
2. Each genuine defect gets the next sequential `UAT-XXX` ID with: severity,
   matrix scenario, reproduction, expected, actual, layer, user impact.
3. Smallest durable automated RED first, committed alone
   (`test: reproduce UAT-XXX <short defect>`), then minimum GREEN
   (`fix: resolve UAT-XXX <short defect>`), each pushed separately. Unrelated
   UAT bugs are never combined into one fix commit.
4. A cross-tenant leak, unauthorized mutation, auth bypass, IDOR, portal-token
   boundary failure, secret exposure, data corruption, or privilege escalation
   is an automatic BLOCKER: pause the rest of the matrix, reproduce, RED, fix,
   run related security regressions, then resume.
5. A matrix scenario revealing a capability that was never part of a shipped
   contract is recorded as **PRODUCT ENHANCEMENT — DEFERRED**, never
   implemented in this sprint (see "No feature creep" below).

## Local acceptance approach

Run the full existing regression baseline first (Phase 7) — pytest, the
frontend suite (vitest, `tsc --noEmit`, lint, runtime-config test,
Docker-contract test, build), the full Playwright suite, and
`alembic heads` / `alembic check` / `git diff --check` — before any product
code changes, to separate pre-existing state from Sprint 028 findings. Then
run every acceptance-matrix row locally (Phase 8) against real FastAPI, real
Next.js, real PostgreSQL, and real Chromium, using fresh synthetic
tenants/data and isolated browser contexts. No real customer PII, ever.

## Staging acceptance approach

After all BLOCKER/HIGH defects are fixed, full regression is green, and the
exact reviewed feature HEAD is GREEN on CI (Phase 21–22), deploy that exact
commit to Railway project `simo-os`, services `simo-api-staging` /
`simo-web-staging`, using the clean-commit-export procedure in
`docs/STAGING_RUNBOOK.md` (never `railway up` from a dirty working directory).
Verify `/health` and `/ready` return 200, then separately verify
`alembic current` == `alembic heads` via the approved Railway SSH path —
health/ready never substitute for a schema check. Re-run the core acceptance
matrix against live staging with fresh synthetic tenants and isolated browser
contexts; a local PASS is not a substitute for a required staging PASS. Any
staging-only defect gets a new `UAT-XXX` ID, is reproduced locally where
possible, goes through the same RED/GREEN cycle, and staging is redeployed
with the new feature HEAD before retest.

## Personas

**OWNER** — workspace/admin: invites Staff, assigns Projects, performs
quote/project operations, views the Business Command Centre, receives
notifications, and has every Staff capability plus admin-only actions.

**STAFF** — operational: logs in, performs allowed Project/quote operations,
is blocked from Owner-only actions (both in the UI, via hidden controls, and
at the API layer — RBAC is never inferred from a hidden button alone), and
receives notification-recipient behavior appropriate to their role.

Both personas are verified at **both** layers: frontend visibility and
backend enforcement independently confirmed for every gated action.

## Tenant-isolation coverage

Using two isolated synthetic tenants, verify representative boundary checks
across every tenant-scoped resource: Customer, Project, Appointment, Quote,
Notification, Portal, Command Centre. Expected behavior follows the locked
resource convention: 404 for another tenant's object, and no cross-tenant
aggregates. No data may leak via object IDs, relationships, notification
sources, portal links, or dashboard totals. If a `role=None` fixture cannot be
constructed safely for the automated layer, it is recorded as
**BLOCKED BY STAGING FIXTURE SAFETY** rather than fabricated against a live
database.

## Connected journey coverage

Sprint 028 reuses the Sprint 027 connected journey
(`apps/web/e2e/full-system-journey.spec.ts`, 13 steps: workspace signup →
Customer/enquiry Project → Site Visit schedule/complete → Quote create/approve
→ handoff to Project → Staff assignment → forward status progression with an
invalid-transition check → document upload → portal link → cross-context
portal verification (project/quote/document + messaging + notification) →
stale-enquiry follow-up job run → Command Centre exact-value assertion →
portal-link revocation) rather than replacing it with a new, disconnected
suite. It is extended only where this sprint's UAT execution surfaces a real
acceptance gap not already covered by that journey — no duplicate journey
tests.

## No feature creep

Any capability UAT reveals as desirable but was never part of a shipped
contract is recorded as **PRODUCT ENHANCEMENT — DEFERRED** and not built in
this sprint. Examples: nicer dashboard charts, a new workflow state, an extra
calendar feature, a new notification type, a new portal function, AI
capability, payment functionality. Sprint 028 fixes defects in existing
intended behavior only. Per the Sprint 016/017 discovery, messaging/documents
have **no attachments, no read-state, no edit/delete, no rate limiting, no
WebSockets/SSE** — the UAT matrix exercises only what was actually shipped,
never invents coverage for unbuilt behavior.

## Exit criteria

- BLOCKER open = 0; HIGH open = 0.
- MEDIUM open = 0, or explicitly accepted/deferred with rationale.
- LOW open documented (fixed or deferred).
- Every core acceptance-matrix row is PASS, or explicitly justified BLOCKED.
- Connected journey: PASS. Owner: PASS. Staff: PASS. Tenant isolation: PASS.
  Portal token matrix: PASS. Follow-up automation: PASS. Command Centre: PASS.
- Staging UAT: PASS. Staging smoke: acceptable (no unexplained new failures
  against the Sprint 027 baseline of 20 passed / 0 failed / 7 blocked-by-design
  out of 27 total gates).
- If any of the above is not met, Sprint 028 remains OPEN.

---

## Acceptance matrix (Phase 6)

Status legend: `PENDING` = not yet executed (filled in during Phase 8 local
run and Phase 25 staging run). Persona `SYS` = system/automation (no logged-in
user). Persona `ANON` = unauthenticated portal-token holder.

### A. Auth / Tenant

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| AT-01 | ANON | Signup creates a new tenant + Owner user | Tenant and Owner persisted, session established | | PENDING | | |
| AT-02 | Owner/Staff | Login with valid credentials | Session established, redirected to app | | PENDING | | |
| AT-03 | Owner/Staff | Session persists across reload | User remains authenticated after page reload | | PENDING | | |
| AT-04 | Owner/Staff | Logout | Session terminated, protected routes redirect to login | | PENDING | | |
| AT-05 | ANON | Request a protected route while unauthenticated | Redirected to login, no data leak | | PENDING | | |
| AT-06 | Owner (Tenant A) | Attempt to access a Tenant B resource by ID | 404, no cross-tenant data returned | | PENDING | | |

### B. Users / Staff / RBAC

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| RB-01 | Owner | Invite a Staff member | Invitation created and deliverable (token/link) | | PENDING | | |
| RB-02 | ANON→Staff | Accept a Staff invitation | Staff account created, tenant-scoped, session established | | PENDING | | |
| RB-03 | Owner | Perform an Owner-only action | Succeeds, persisted | | PENDING | | |
| RB-04 | Owner & Staff | Perform an action allowed to both roles | Succeeds for both | | PENDING | | |
| RB-05 | Staff | Attempt an Owner-only action (UI + API) | Blocked in UI and rejected (403) at API | | PENDING | | |
| RB-06 | SYS | `role=None` behavior at automated-test layer (if a safe fixture exists) | Access denied consistently; BLOCKED-with-reason if no safe fixture | | PENDING | | |

### C. Customers / Enquiries

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| CE-01 | Owner/Staff | Create a Customer | Persisted, tenant-scoped | | PENDING | | |
| CE-02 | Owner/Staff | Create an unlinked enquiry Project | Persisted with no Customer relationship | | PENDING | | |
| CE-03 | Owner/Staff | Convert enquiry → Customer | Customer + `Project.customer_id` + Activity created atomically | | PENDING | | |
| CE-04 | Owner/Staff | Reload after conversion | Converted state persists across reload | | PENDING | | |
| CE-05 | Owner/Staff | Retry the same conversion | Idempotent — no duplicate Customer/Activity | | PENDING | | |
| CE-06 | Owner/Staff | Attempt to convert a non-enquiry Project | Rejected | | PENDING | | |

### D. Appointment / Site Visit

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| AV-01 | Owner/Staff | Schedule a Site Visit | Appointment persisted, linked to Project | | PENDING | | |
| AV-02 | Owner/Staff | Reload after scheduling | State persists | | PENDING | | |
| AV-03 | Owner/Staff | Complete a Site Visit | Status transitions, Activity recorded atomically | | PENDING | | |
| AV-04 | Owner/Staff | Cancel a Site Visit | Cancel path completes correctly | | PENDING | | |
| AV-05 | Owner/Staff | Attempt an invalid terminal transition | Rejected | | PENDING | | |
| AV-06 | Owner (Tenant A) | Attempt cross-tenant Appointment access | 404 | | PENDING | | |

### E. Quote

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| QT-01 | Owner/Staff | Create a Quote | Persisted, draft status | | PENDING | | |
| QT-02 | Owner/Staff | Load an existing Quote | Correct data returned | | PENDING | | |
| QT-03 | Owner/Staff | Approve a Quote | Status transitions to approved | | PENDING | | |
| QT-04 | Owner/Staff | Reload after approval | Approved state persists | | PENDING | | |
| QT-05 | Owner/Staff | Repeat approval / act on invalid state | Rejected or safely idempotent per contract | | PENDING | | |

### F. Quote → Project handoff

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| HO-01 | Owner/Staff | Hand off an approved Quote | New Project created | | PENDING | | |
| HO-02 | Owner/Staff | Inspect resulting Project | Correct initial status/fields | | PENDING | | |
| HO-03 | Owner/Staff | Verify Customer relationship | Correct Customer linked | | PENDING | | |
| HO-04 | Owner/Staff | Verify Quote relationship | Project references originating Quote | | PENDING | | |
| HO-05 | Owner/Staff | Retry handoff on the same Quote | Idempotent — returns the same Project | | PENDING | | |
| HO-06 | Owner/Staff | Attempt handoff on a draft Quote | Rejected | | PENDING | | |

### G. Project operations

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| PO-01 | Owner | Assign Staff to a Project | Assignment persisted | | PENDING | | |
| PO-02 | Owner | Reload after assignment | Assignment persists | | PENDING | | |
| PO-03 | Staff | Perform an allowed operation on an assigned Project | Succeeds, Activity recorded | | PENDING | | |
| PO-04 | Owner/Staff | Advance status strictly forward one step | Succeeds, Activity recorded atomically | | PENDING | | |
| PO-05 | Owner/Staff | Attempt to skip or move status backward | Rejected | | PENDING | | |
| PO-06 | Owner/Staff | Act on a terminal-status Project | Terminal behavior enforced | | PENDING | | |

### H. Follow-up automation

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| FU-01 | SYS | Seed a legitimately stale enquiry fixture | Fixture created, meets staleness criteria | | PENDING | | |
| FU-02 | SYS | Run the real follow-up CLI/job (first run) | Expected notification(s) created | | PENDING | | |
| FU-03 | SYS | Verify intended recipient | Correct tenant user(s) notified | | PENDING | | |
| FU-04 | SYS | Verify notification creation details | Correct source/type, unread initially | | PENDING | | |
| FU-05 | SYS | Run the job a second time | Zero duplicates created | | PENDING | | |
| FU-06 | Owner/Staff | Click through from notification | Correct navigation to the source Project | | PENDING | | |
| FU-07 | Owner/Staff | Mark notification read | Read state persists across reload | | PENDING | | |

### I. Client portal

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| PT-01 | ANON | Access with a valid portal token | Scoped data loads correctly | | PENDING | | |
| PT-02 | ANON | Access with a revoked token | Rejected, no data exposed | | PENDING | | |
| PT-03 | ANON | Access with an expired token | Rejected, no data exposed | | PENDING | | |
| PT-04 | ANON | Verify scoped data matches only the linked Customer/Project | Correctly scoped, nothing extra | | PENDING | | |
| PT-05 | ANON (Tenant A token) | Attempt to reach Tenant B data via the portal | No leakage | | PENDING | | |

### J. Messaging / Documents

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| MD-01 | ANON | Access documents via the portal | Only the linked Customer's documents visible, download works | | PENDING | | |
| MD-02 | ANON & Staff | Customer posts a portal message; Staff views it | Message persisted, staff-visible, triggers Activity + notification | | PENDING | | |
| MD-03 | ANON | Attempt document/message access with an invalid/revoked/expired token | Rejected, no data exposed | | PENDING | | |
| MD-04 | Staff | Post a staff message; reload | Persists in thread order, no unintended side effects (no activity/notification per shipped contract) | | PENDING | | |

### K. Business Command Centre

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| CC-01 | Owner | Project pipeline counts vs. controlled fixture | Exact match to independently-calculated fixture truth | | PENDING | | |
| CC-02 | Owner | Quote metrics (draft/approved/handed_off/quoted_value/approved_quoted_value) | Exact match; `handed_off` independently queried, not derived | | PENDING | | |
| CC-03 | Owner | Site-visit (Appointment status) metrics | Exact match | | PENDING | | |
| CC-04 | Owner | Follow-up metric (tenant-wide unread notifications) | Exact match | | PENDING | | |
| CC-05 | Owner | Supported monetary totals are correctly labeled | `quoted_value`/`approved_quoted_value` never mislabeled as "revenue" | | PENDING | | |
| CC-06 | Owner | Empty-state (zero data) tenant | Correct empty-state rendering, no errors | | PENDING | | |
| CC-07 | Owner (Tenant A) | Command Centre values with a populated Tenant B | No Tenant B values appear in Tenant A's dashboard | | PENDING | | |

### L. Security / Hardening

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| SH-01 | SYS | Inspect security headers on API responses | Sprint 026/027 header contract intact | | PENDING | | |
| SH-02 | SYS | CORS from an allowed origin | Allowed | | PENDING | | |
| SH-03 | SYS | CORS from a disallowed origin | Denied | | PENDING | | |
| SH-04 | ANON | Call a protected endpoint without auth | Enforced (401/403), no data leak | | PENDING | | |
| SH-05 | Owner (Tenant A) | Cross-tenant boundary spot-check on a protected endpoint | Enforced (404), no leak | | PENDING | | |
| SH-06 | SYS | Trigger a server error | Sanitized error, no stack trace/internal detail exposed | | PENDING | | |
| SH-07 | SYS | Inspect runtime config / repository for exposed secrets | None found | | PENDING | | |
| SH-08 | SYS | Staging `/health` and `/ready` | Both 200 | | PENDING | | |

---

## Data-integrity invariants to revalidate (Phase 13)

These invariants were established in earlier sprints and must be explicitly
re-confirmed, not assumed, during Phase 8/25 execution:

- **Enquiry conversion:** Customer + `Project.customer_id` + Activity persist
  atomically (CE-03).
- **Appointment:** creation/status transition + Activity persist atomically
  (AV-03).
- **Project operations:** assignment/status transition + Activity persist
  atomically (PO-04).
- **Quote handoff:** a repeat handoff on the same Quote returns the same
  Project, never a duplicate (HO-05).
- **Follow-up:** DB-level uniqueness prevents duplicate notifications across
  repeated job runs (FU-05).
- **Portal:** token state (valid/revoked/expired) never exposes invalid data;
  no partial persistence survives an injected failure path.

## UX acceptance (Phase 14)

For every major journey inspected above, additionally check: discoverability,
label clarity, loading state, pending state, success state, error state,
retryability, disabled-state behavior, reload persistence, terminal-action
visibility, navigation correctness. Fix only objectively broken/confusing
behavior on existing workflows — this sprint does not redesign pages for
subjective preference.
