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

## Acceptance matrix (Phase 6) — Phase 8 local execution results

Status legend: `PASS` = executed against real FastAPI/Next.js/PostgreSQL
(and real Chromium where noted) this sprint, evidence cited. `PENDING (staging)`
= locally PASS, re-verified against Railway staging in Phase 25. Persona
`SYS` = system/automation (no logged-in user). Persona `ANON` = unauthenticated
portal-token holder. Evidence file paths are repo-relative; `pytest` and
`vitest` evidence was captured from real runs against the local
Postgres-backed stack (docker-compose `simo-os-postgres`), and `e2e` evidence
from the real Chromium/Next.js-dev/FastAPI-dev stack
(`apps/web/playwright.config.ts`) — no mocks in either case.

### A. Auth / Tenant

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| AT-01 | ANON | Signup creates a new tenant + Owner user | Tenant and Owner persisted, session established | Matches | PASS | pytest `test_auth.py::test_signup_creates_tenant_and_user`; e2e `full-system-journey.spec.ts` step 1 | |
| AT-02 | Owner/Staff | Login with valid credentials | Session established, redirected to app | Matches | PASS | pytest `test_auth.py::test_login_success`; vitest `app/login/page.test.tsx::submits_credentials_and_redirects_to_customers_on_success`; every e2e spec's own login step | |
| AT-03 | Owner/Staff | Session persists across reload | User remains authenticated after page reload | Matches | PASS | e2e `full-system-journey.spec.ts` step 2 ("Session persists across a reload") | |
| AT-04 | Owner/Staff | Logout | Session terminated, protected routes redirect to login | Matches (previously untested — see below) | PASS | e2e `logout.spec.ts` (added this sprint, PASS, no defect) | |
| AT-05 | ANON | Request a protected route while unauthenticated | Redirected to login, no data leak | Matches | PASS | e2e `unauthenticated-redirect.spec.ts` (4 protected routes) | |
| AT-06 | Owner (Tenant A) | Attempt to access a Tenant B resource by ID | 404, no cross-tenant data returned | Matches | PASS | pytest `test_tenants.py::test_tenant_detail_cross_tenant_returns_404`; e2e `cross-tenant-boundary.spec.ts` | |

### B. Users / Staff / RBAC

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| RB-01 | Owner | Invite a Staff member | Invitation created and deliverable (token/link) | Matches | PASS | pytest `test_invitations.py::test_create_invitation_success`; vitest `app/settings/page.test.tsx::owner_can_create_an_invitation_and_sees_the_generated_link` | |
| RB-02 | ANON→Staff | Accept a Staff invitation | Staff account created, tenant-scoped, session established | Matches | PASS | pytest `test_invitations.py::test_accept_invitation_creates_staff_user_and_logs_in`; vitest `app/invite/[token]/page.test.tsx::renders_the_accept_form_for_a_pending_invitation_and_submits`; e2e `role-boundary-owner-vs-staff.spec.ts` (real accept via API, real browser session) | |
| RB-03 | Owner | Perform an Owner-only action | Succeeds, persisted | Matches | PASS | pytest `test_invitations.py::test_create_invitation_success`; `test_users.py::test_deactivate_user_flips_is_active_and_logs_activity`; `test_project_operations.py::test_owner_can_assign_a_same_tenant_staff_member_to_a_booked_project` | |
| RB-04 | Owner & Staff | Perform an action allowed to both roles | Succeeds for both | Matches | PASS | pytest `test_project_operations.py::test_staff_can_advance_status` + `test_valid_forward_status_transition_still_succeeds_for_owner` | |
| RB-05 | Staff | Attempt an Owner-only action (UI + API) | Blocked in UI and rejected (403) at API | Matches | PASS | pytest `test_rbac_matrix.py` (119 parametrized route/role checks) + `test_project_operations.py::test_same_tenant_staff_cannot_assign`; vitest `app/settings/page.test.tsx::staff_session_sees_no_invite_or_team_management_controls`; e2e `role-boundary-owner-vs-staff.spec.ts` (UI absence, not just 403) | |
| RB-06 | SYS | `role=None` behavior at automated-test layer (if a safe fixture exists) | Access denied consistently; BLOCKED-with-reason if no safe fixture | A safe service-layer `role=None` fixture exists and is exercised — not blocked | PASS | pytest `test_rbac_matrix.py::test_no_role_caller_is_forbidden[...]` (14 parametrized routes) + `test_command_centre.py::test_role_none_is_forbidden` + `test_dashboard.py::test_dashboard_role_none_is_forbidden` | |

### C. Customers / Enquiries

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| CE-01 | Owner/Staff | Create a Customer | Persisted, tenant-scoped | Matches | PASS | pytest `test_customers.py::test_create_customer`; e2e `full-system-journey.spec.ts` | |
| CE-02 | Owner/Staff | Create an unlinked enquiry Project | Persisted with no Customer relationship | Matches | PASS | pytest `test_projects.py::test_create_project_defaults_to_enquiry` | |
| CE-03 | Owner/Staff | Convert enquiry → Customer | Customer + `Project.customer_id` + Activity created atomically | Matches | PASS | pytest `test_enquiry_conversion.py::test_staff_can_convert_an_unlinked_enquiry_project_into_a_customer` + `test_successful_enquiry_conversion_creates_exactly_one_tenant_scoped_activity`; e2e `enquiry-conversion.spec.ts` | |
| CE-04 | Owner/Staff | Reload after conversion | Converted state persists across reload | Matches | PASS | e2e `enquiry-conversion.spec.ts` (explicit `page.reload()` persistence check) | |
| CE-05 | Owner/Staff | Retry the same conversion | Idempotent — no duplicate Customer/Activity | Matches | PASS | pytest `test_enquiry_conversion.py::test_repeat_conversion_returns_the_same_customer_without_creating_another` | |
| CE-06 | Owner/Staff | Attempt to convert a non-enquiry Project | Rejected | Matches | PASS | pytest `test_enquiry_conversion.py::test_conversion_rejects_a_non_enquiry_project` | |

### D. Appointment / Site Visit

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| AV-01 | Owner/Staff | Schedule a Site Visit | Appointment persisted, linked to Project | Matches | PASS | pytest `test_appointments.py::test_staff_can_create_a_scheduled_appointment_against_a_same_tenant_project`; e2e `site-visit-scheduling.spec.ts` | |
| AV-02 | Owner/Staff | Reload after scheduling | State persists | Matches | PASS | e2e `site-visit-scheduling.spec.ts` (explicit `page.reload()` persistence check) | |
| AV-03 | Owner/Staff | Complete a Site Visit | Status transitions, Activity recorded atomically | Matches | PASS | pytest `test_appointments.py::test_appointment_can_transition_to_completed_and_then_repeat_call_is_idempotent` + `test_completing_an_appointment_logs_exactly_one_site_visit_completed_activity`; e2e `site-visit-scheduling.spec.ts` | |
| AV-04 | Owner/Staff | Cancel a Site Visit | Cancel path completes correctly | Matches (previously untested — see below) | PASS | pytest `test_appointments.py::test_a_scheduled_appointment_can_be_cancelled` (added this sprint, PASS, no defect) | |
| AV-05 | Owner/Staff | Attempt an invalid terminal transition | Rejected | Matches | PASS | pytest `test_appointments.py::test_completed_appointment_cannot_transition_to_cancelled` | |
| AV-06 | Owner (Tenant A) | Attempt cross-tenant Appointment access | 404 | Matches | PASS | pytest `test_appointments.py::test_create_appointment_against_another_tenants_project_returns_404` + `test_status_update_for_another_tenants_appointment_returns_404` | |

### E. Quote

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| QT-01 | Owner/Staff | Create a Quote | Persisted, draft status | Matches | PASS | pytest `test_quotes_api.py::test_create_quote_persists_and_is_listed`; e2e `quote-handoff.spec.ts` | |
| QT-02 | Owner/Staff | Load an existing Quote | Correct data returned | Matches | PASS | pytest `test_quotes_api.py::test_get_quote_by_id` | |
| QT-03 | Owner/Staff | Approve a Quote | Status transitions to approved | Matches | PASS | pytest `test_quote_handoff.py::test_staff_can_approve_a_draft_quote`; e2e `quote-handoff.spec.ts` | |
| QT-04 | Owner/Staff | Reload after approval | Approved state persists | Matches | PASS | e2e `quote-handoff.spec.ts` (explicit `page.reload()` persistence check) | |
| QT-05 | Owner/Staff | Repeat approval / act on invalid state | Rejected or safely idempotent per contract | Rejected (409), no mutation — matches contract | PASS | pytest `test_quote_handoff.py::test_repeat_approval_of_an_already_approved_quote_is_rejected` (added this sprint, PASS, no defect) | |

### F. Quote → Project handoff

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| HO-01 | Owner/Staff | Hand off an approved Quote | New Project created | Matches | PASS | pytest `test_quote_handoff.py::test_staff_can_hand_off_an_approved_quote_into_a_project`; e2e `quote-handoff.spec.ts` | |
| HO-02 | Owner/Staff | Inspect resulting Project | Correct initial status/fields | Matches | PASS | pytest `test_quote_handoff.py::test_staff_can_hand_off_an_approved_quote_into_a_project` | |
| HO-03 | Owner/Staff | Verify Customer relationship | Correct Customer linked | Matches | PASS | e2e `quote-handoff.spec.ts` (asserts Project's Customer) | |
| HO-04 | Owner/Staff | Verify Quote relationship | Project references originating Quote | Matches | PASS | pytest `test_quote_handoff.py::test_staff_can_hand_off_an_approved_quote_into_a_project` | |
| HO-05 | Owner/Staff | Retry handoff on the same Quote | Idempotent — returns the same Project | Matches | PASS | pytest `test_quote_handoff.py::test_repeat_handoff_of_the_same_quote_is_idempotent` | |
| HO-06 | Owner/Staff | Attempt handoff on a draft Quote | Rejected | Matches | PASS | pytest `test_quote_handoff.py::test_handoff_rejects_a_draft_quote` | |

### G. Project operations

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| PO-01 | Owner | Assign Staff to a Project | Assignment persisted | Matches | PASS | pytest `test_project_operations.py::test_owner_can_assign_a_same_tenant_staff_member_to_a_booked_project`; e2e `project-operations.spec.ts` | |
| PO-02 | Owner | Reload after assignment | Assignment persists | Matches | PASS | e2e `project-operations.spec.ts` (explicit `page.reload()` persistence check) | |
| PO-03 | Staff | Perform an allowed operation on an assigned Project | Succeeds, Activity recorded | Matches | PASS | pytest `test_project_operations.py::test_staff_can_advance_status` | |
| PO-04 | Owner/Staff | Advance status strictly forward one step | Succeeds, Activity recorded atomically | Matches | PASS | pytest `test_project_operations.py::test_valid_forward_status_transition_still_succeeds_for_owner` + `test_successful_status_transition_logs_exactly_one_project_status_changed_activity`; e2e `project-operations.spec.ts` | |
| PO-05 | Owner/Staff | Attempt to skip or move status backward | Rejected | Matches | PASS | pytest `test_project_operations.py::test_skipping_a_status_stage_returns_409` + `test_reverting_a_status_backward_returns_409`; e2e `project-operations.spec.ts` (invalid-transition check) | |
| PO-06 | Owner/Staff | Act on a terminal-status Project | Terminal behavior enforced | Matches | PASS | pytest `test_project_operations.py::test_transition_from_complete_is_rejected` | |

### H. Follow-up automation

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| FU-01 | SYS | Seed a legitimately stale enquiry fixture | Fixture created, meets staleness criteria | Matches | PASS | pytest `test_follow_up_automation.py::test_project_younger_than_threshold_is_not_due`; e2e `follow-up-automation.spec.ts` | |
| FU-02 | SYS | Run the real follow-up CLI/job (first run) | Expected notification(s) created | Matches | PASS | pytest `test_follow_up_automation.py::test_run_creates_exactly_one_notification_for_a_stale_enquiry_with_assigned_staff`; e2e `follow-up-automation.spec.ts` runs the real `python -m app.jobs.follow_up` subprocess | |
| FU-03 | SYS | Verify intended recipient | Correct tenant user(s) notified | Matches | PASS | pytest `test_follow_up_automation.py::test_unassigned_project_falls_back_to_tenant_owner` + `test_two_tenants_each_get_their_own_correctly_scoped_notification` | |
| FU-04 | SYS | Verify notification creation details | Correct source/type, unread initially | Matches | PASS | e2e `follow-up-automation.spec.ts` (asserts `source_type`, `recipient_user_id`, initial unread state) | |
| FU-05 | SYS | Run the job a second time | Zero duplicates created | Matches | PASS | pytest `test_follow_up_automation.py::test_running_twice_creates_no_duplicate_notification` + `test_duplicate_dedupe_key_is_rejected_at_the_database_level`; e2e `follow-up-automation.spec.ts` (second real subprocess run) | |
| FU-06 | Owner/Staff | Click through from notification | Correct navigation to the source Project | Matches | PASS | e2e `follow-up-automation.spec.ts` (click → URL assertion) | |
| FU-07 | Owner/Staff | Mark notification read | Read state persists across reload | Matches | PASS | e2e `follow-up-automation.spec.ts` (reload + live API re-check) | |

### I. Client portal

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| PT-01 | ANON | Access with a valid portal token | Scoped data loads correctly | Matches | PASS | pytest `test_portal.py::test_get_portal_by_token_public`; e2e `full-system-journey.spec.ts` | |
| PT-02 | ANON | Access with a revoked token | Rejected, no data exposed | Matches | PASS | pytest `test_portal.py::test_revoked_portal_link_reads_as_revoked_and_returns_no_data`; e2e `portal-token-lifecycle.spec.ts` | |
| PT-03 | ANON | Access with an expired token | Rejected, no data exposed | Matches | PASS | pytest `test_portal.py::test_expired_portal_link_reads_as_expired_and_returns_no_data`; e2e `portal-token-lifecycle.spec.ts` | |
| PT-04 | ANON | Verify scoped data matches only the linked Customer/Project | Correctly scoped, nothing extra | Matches | PASS | pytest `test_portal.py::test_portal_returns_only_that_customers_projects_and_quotes` | |
| PT-05 | ANON (Tenant A token) | Attempt to reach Tenant B data via the portal | No leakage | Matches | PASS | pytest `test_portal.py::test_portal_cross_tenant_isolation` | |

### J. Messaging / Documents

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| MD-01 | ANON | Access documents via the portal | Only the linked Customer's documents visible, download works | Matches | PASS | pytest `test_documents.py::test_portal_lists_only_that_customers_documents` + `test_portal_downloads_document_successfully` | |
| MD-02 | ANON & Staff | Customer posts a portal message; Staff views it | Message persisted, staff-visible, triggers Activity + notification | Matches | PASS | pytest `test_messages.py::test_portal_message_has_null_sender_user_id_and_exact_side_effects` (asserts exactly 1 new Activity + 1 new Notification) | |
| MD-03 | ANON | Attempt document/message access with an invalid/revoked/expired token | Rejected, no data exposed | Matches | PASS | pytest `test_documents.py::test_portal_revoked_link_cannot_access_documents`; `test_messages.py::test_revoked_portal_token_cannot_list_or_post` + `test_expired_portal_token_cannot_list_or_post` | |
| MD-04 | Staff | Post a staff message; reload | Persists in thread order, no unintended side effects (no activity/notification per shipped contract) | Matches | PASS | pytest `test_messages.py::test_staff_message_creates_no_activity_or_notification` + `test_messages_are_listed_oldest_to_newest` | |

### K. Business Command Centre

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| CC-01 | Owner | Project pipeline counts vs. controlled fixture | Exact match to independently-calculated fixture truth | Matches | PASS | pytest `test_command_centre.py::test_pipeline_counts_are_exact_and_tenant_scoped`; e2e `business-command-centre.spec.ts` | |
| CC-02 | Owner | Quote metrics (draft/approved/handed_off/quoted_value/approved_quoted_value) | Exact match; `handed_off` independently queried, not derived | Matches | PASS | pytest `test_command_centre.py::test_quote_funnel_and_value_are_exact`; e2e `business-command-centre.spec.ts` | |
| CC-03 | Owner | Site-visit (Appointment status) metrics | Exact match | Matches | PASS | pytest `test_command_centre.py::test_site_visit_counts_are_exact` | |
| CC-04 | Owner | Follow-up metric (tenant-wide unread notifications) | Exact match | Matches | PASS | pytest `test_command_centre.py::test_follow_up_attention_counts_unread_project_sourced_notifications_tenant_wide` | |
| CC-05 | Owner | Supported monetary totals are correctly labeled | `quoted_value`/`approved_quoted_value` never mislabeled as "revenue" | The Sprint 025 Command Centre itself never mislabeled this — but the older, still-live home-page dashboard (`GET /api/v1/dashboard` + `StatGrid`) did, under the key/label "revenue" | **UAT-002 found and fixed** | pytest `test_dashboard.py::test_dashboard_never_labels_a_quote_total_as_revenue` (added this sprint); `test_command_centre.py` (Command Centre itself was already correct, per `app/dashboard/models.py`'s `QuotedValue` docstring) | UAT-002 |
| CC-06 | Owner | Empty-state (zero data) tenant | Correct empty-state rendering, no errors | Matches | PASS | pytest `test_command_centre.py::test_empty_tenant_gets_all_zeros_not_nulls_or_500` | |
| CC-07 | Owner (Tenant A) | Command Centre values with a populated Tenant B | No Tenant B values appear in Tenant A's dashboard | Matches | PASS | pytest `test_command_centre.py::test_pipeline_counts_are_exact_and_tenant_scoped` (tenant-scoping assertions); e2e `business-command-centre.spec.ts` (excludes other tenants) | |

### L. Security / Hardening

| ID | Persona | Scenario | Expected | Actual | Status | Evidence | Defect |
|---|---|---|---|---|---|---|---|
| SH-01 | SYS | Inspect security headers on API responses | Sprint 026/027 header contract intact | Matches | PASS | pytest `test_security_headers.py::test_security_headers_present_on_a_normal_response` + `test_security_headers_present_on_an_error_response` | |
| SH-02 | SYS | CORS from an allowed origin | Allowed | Matches | PASS | pytest `test_runtime_http.py::test_cors_preflight_allows_configured_origin` | |
| SH-03 | SYS | CORS from a disallowed origin | Denied | Matches | PASS | pytest `test_runtime_http.py::test_cors_preflight_rejects_origin_outside_configuration` | |
| SH-04 | ANON | Call a protected endpoint without auth | Enforced (401/403), no data leak | Matches | PASS | pytest `test_rbac_matrix.py::test_no_token_matches_expected_category[...]` (every protected route) | |
| SH-05 | Owner (Tenant A) | Cross-tenant boundary spot-check on a protected endpoint | Enforced (404), no leak | Matches | PASS | pytest `test_projects.py::test_get_project_cross_tenant_returns_404`; `test_customers.py::test_get_customer_cross_tenant_returns_404`; e2e `cross-tenant-boundary.spec.ts` | |
| SH-06 | SYS | Trigger a server error | Sanitized error, no stack trace/internal detail exposed | Matches | PASS | pytest `test_runtime_http.py::test_unhandled_exception_is_structured_redacted_and_keeps_safe_response` + `test_ready_redacts_database_errors_and_logs_only_the_exception_type` | |
| SH-07 | SYS | Inspect runtime config / repository for exposed secrets | None found | Matches — `.env` gitignored and untracked; repo-wide scan for common key/token patterns (`sk-`, `AKIA`, private-key headers, Slack tokens) found none | PASS | pytest `test_railway_contract.py::test_staging_environment_inventory_is_complete_and_secret_free`; manual repo-wide secret-pattern scan (this sprint) | |
| SH-08 | SYS | Staging `/health` and `/ready` | Both 200 | Both 200, with hardening headers and a request ID present | PASS | `curl` against `https://simo-api-staging-staging.up.railway.app/health` and `/ready` (this sprint, commit `d356dc0`); smoke `liveness`/`readiness` gates | |

**Matrix totals (final, local + staging):** 72 rows. **72 PASS.** 0 FAIL. 0
BLOCKED. 3 rows (AT-04, AV-04, QT-05) had no prior automated coverage and were
verified live this sprint, adding durable regression tests with no defect
found. 1 row (CC-05) surfaced a genuine defect (UAT-002) on a sibling legacy
endpoint, fixed this sprint.

## Phase 7 — local regression baseline (before any Sprint 028 code changes)

Run against the discovery-locked contract commit (`e4a0463`), before any
product code changes, per the locked contract's Phase 7 rule:

- Backend: `pytest` — **547 passed, 1 skipped, 0 failed** (identical to the
  Sprint 027 closeout baseline — no pre-existing regression).
- Frontend type-check (`pnpm --filter web exec tsc --noEmit`): clean.
- Frontend lint (`pnpm --filter web lint`): clean.
- Frontend component tests (`pnpm --filter web test`): **66/66 passed**
  (10 files).
- `pnpm --filter web test:runtime-config`: **7/7 passed**.
- `pnpm --filter web test:docker-contract`: **5/5 passed**.
- `pnpm build`: clean, all 14 routes generated.
- Playwright (`pnpm --filter web exec playwright test`, full suite):
  **12/12 passed** across all 11 spec files.
- `alembic heads` / `alembic current`: single head `2243d66f83da`, local DB at
  head. `alembic check`: no new upgrade operations detected.
- `git diff --check` (`7f24ac6..HEAD`): clean.

Baseline confirmed identical to Sprint 027's closeout state — any FAIL found
from here on is Sprint 028's own finding, not inherited noise.

## UAT defects found and fixed

### UAT-001 — profile menu shows hardcoded identity

- **Severity:** MEDIUM (misleading operational state — no access-control
  impact; RBAC is separately enforced server-side and by other, correct,
  `useAuth()`-driven UI gates elsewhere).
- **Matrix scenario:** Category B frontend-visibility check (RB-05/B general).
- **Reproduction:** Sign in as any user (Staff, or an Owner at a tenant other
  than the original seed tenant) and open the header profile menu
  (`components/shell/UserProfileMenu.tsx`). It always rendered a fixed
  `{ name: "Simo", role: "Owner", tenant: "Simo Marble & Construction Ltd" }`
  regardless of who was actually signed in — `AuthProvider` already exposed
  the real `role`/`tenantName` (and the backend already returns the real
  `name` on every auth response, `app/auth/models.py`), but the component
  never consumed any of them.
- **Expected:** The header shows the real signed-in user's name, role, and
  tenant.
- **Actual (before fix):** Always "Simo" / "Owner" / "Simo Marble &
  Construction Ltd", for every user in every tenant.
- **Layer:** Frontend only (display) — backend RBAC/tenant data were never
  wrong.
- **User impact:** A Staff user sees themselves labeled "Owner" (and every
  user sees someone else's name/company) in their own account menu —
  confusing, but does not grant or deny any actual capability.
- **RED commit:** `cc00dfa` — `test: reproduce UAT-001 profile menu shows hardcoded identity`.
- **GREEN commit:** `d6e7c09` — `fix: resolve UAT-001 profile menu shows hardcoded identity`.
- **Test-correctness follow-up:** `0d776f7` (RED test needed to open the
  dropdown before asserting dropdown-only content — test infra fix, not a
  behavior change).
- **Retest:** `vitest run components/shell/UserProfileMenu.test.tsx` — 2/2
  passed. Full `pnpm --filter web test` re-run: 68/68 passed. `tsc --noEmit`,
  lint, build: all clean.

### UAT-002 — legacy dashboard mislabels quote totals as "revenue"

- **Severity:** MEDIUM (misleading financial/operational state — the system
  has no payment/invoicing recognition anywhere; `docs/ROADMAP.md` still
  lists payment tracking as unbuilt/deferred, so no total in the product can
  legitimately be called revenue).
- **Matrix scenario:** CC-05 (supported monetary totals correctly labeled).
- **Reproduction:** As any Owner/Staff, load the home dashboard (`/`, not the
  Sprint 025 Command Centre). `GET /api/v1/dashboard` sums every quote's
  `total` regardless of status — draft included — via
  `crud.sum_quotes_revenue`, and returns it under the key `"revenue"`; the
  frontend `StatGrid` then displays it under the label "Revenue".
- **Expected:** Per the exact principle Sprint 025 already established for
  its own replacement metric (`app/dashboard/models.py`'s `QuotedValue`
  docstring: "a quote total is a price offered or committed to, not
  recognized income"), no quote-total figure may be labeled revenue.
- **Actual (before fix):** Labeled "revenue" in both the API response and the
  UI.
- **Layer:** Backend (response field name) + frontend (display label).
- **User impact:** Overstates the business's actual financial position by
  presenting unapproved draft-quote value as if it were earned income.
- **RED commit:** `57b6d86` — `test: reproduce UAT-002 legacy dashboard mislabels quote totals as revenue`.
- **GREEN commit:** `28e1c15` — `fix: resolve UAT-002 legacy dashboard mislabels quote totals as revenue`.
- **Retest:** `pytest tests/test_dashboard.py` — 6/6 passed. Full `pytest` —
  550 passed, 1 skipped, 0 failed. `tsc --noEmit`, lint, `vitest`, `build`:
  all clean.

### UAT-003 — dashboard greeting shows hardcoded identity

- **Severity:** LOW (cosmetic wording only — no access-control or financial
  impact; same underlying root cause as UAT-001, different location).
- **Matrix scenario:** UX acceptance (Phase 14) general check, surfaced while
  investigating UAT-001.
- **Reproduction:** Load the home dashboard (`/`) as any user. The greeting
  always read "Welcome back, Simo" regardless of who was signed in.
- **Expected:** Greets the actual signed-in user by their real name.
- **Actual (before fix):** Always "Welcome back, Simo".
- **Layer:** Frontend only.
- **User impact:** Cosmetic confusion only ("why does it call me Simo?");
  never affects data, permissions, or workflow correctness.
- **RED commit:** `a63dab0` — `test: reproduce UAT-003 dashboard greeting shows hardcoded identity`.
- **GREEN commit:** `66a19d5` — `fix: resolve UAT-003 dashboard greeting shows hardcoded identity`.
- **Retest:** `vitest run app/page.test.tsx` — 1/1 passed. Full
  `pnpm --filter web test`: 69/69 passed. `tsc --noEmit`, lint, `build`: all
  clean.

### Coverage additions with no defect found

Three matrix rows had no prior automated coverage. Each was verified live
against the real stack this sprint; all three PASS — no product defect,
durable regression test added so the gap doesn't reopen silently:

- **AT-04 (logout):** `9e29728` — `test: cover AT-04 logout via Sprint 028 UAT execution` (`apps/web/e2e/logout.spec.ts`).
- **QT-05 (repeat quote approval):** `a4ce752` — `test: cover QT-05 repeat quote approval via Sprint 028 UAT execution` (`tests/test_quote_handoff.py`).
- **AV-04 (site visit cancellation):** `b78f8a9` — `test: cover AV-04 site visit cancellation via Sprint 028 UAT execution` (`tests/test_appointments.py`).

### Deferred / accepted findings

None. No MEDIUM or LOW finding was left unaddressed — both UAT-002 (MEDIUM)
and UAT-003 (LOW) were fixed rather than deferred, since both fixes were
small, low-risk, and directly informed by an existing, already-correct
pattern elsewhere in the codebase (Sprint 025's `QuotedValue` convention for
UAT-002; `AuthProvider`'s already-exposed `name` field, added for UAT-001,
for UAT-003).

No PRODUCT ENHANCEMENT — DEFERRED items were logged: every UAT execution path
this sprint traced back to either already-shipped, correctly-working behavior,
or a genuine labeling/coverage defect in already-shipped behavior — nothing
UAT surfaced asked for new capability.

## Staging deployment and staging UAT (Phase 21-27)

**Feature CI (exact-head, pre-staging):** commit `d356dc0` — backend GREEN,
frontend GREEN, e2e GREEN (all 3 GitHub Actions check runs `completed`/
`success`).

**Deployment:** clean `git archive d356dc06b359a9976a5aa782ab2ffe080490258a`
export deployed via `railway up -c` per `docs/STAGING_RUNBOOK.md`'s
clean-commit procedure, to Railway project `simo-os`, environment `staging`,
services `simo-api-staging` and `simo-web-staging`. Both deployments
`SUCCESS`.

**Staging schema gate:**
- `GET /health` → 200. `GET /ready` → 200 (both with hardening headers and a
  request ID present).
- `railway ssh --service simo-api-staging --environment staging -- alembic current`
  → `2243d66f83da (head)` — matches local `alembic heads` exactly (no
  migration shipped this sprint, so this confirms no drift, per the
  runbook's Sprint 021 addendum).

**Real staging UAT** (synthetic data, real frontend/API/database, no
production access):
- Signup/login/session: PASS — real synthetic tenant/Owner created via
  `POST /api/v1/auth/signup` against the live staging API, session token
  issued.
- Owner/Staff + RBAC: PASS — Owner invited a synthetic Staff user, Staff
  accepted (`role: "Staff"` confirmed), Staff's attempt at an Owner-only
  action (`POST /api/v1/invitations`) correctly returned 403.
- Tenant boundaries: PASS — smoke `tenant_isolation` gate.
- Enquiry → Customer conversion: PASS — converted a real staging enquiry
  Project, Customer created with a real id, `Project.customer_id` set;
  repeat conversion returned the identical Customer id (idempotent, no
  duplicate).
- Site Visit: PASS — smoke `appointment` gate.
- Quote approval + handoff: PASS — smoke `quote_approve_handoff` gate.
- Project Operations: PASS — smoke `project_assignment_status` gate.
- Follow-up CLI + notification: PASS — independently verified via
  `railway ssh ... python -m app.jobs.follow_up --now <stale-iso>` against
  the real staging job entrypoint (not the smoke harness, which documents
  this as by-design BLOCKED since the job has no HTTP trigger): first run
  created a notification for a real synthetic stale enquiry
  (`source_type: "project"`, correct recipient, unread), confirmed via
  `GET /api/v1/notifications`; second run with the same `--now` created
  zero duplicates (`"created": 0, "skipped_existing": 24`).
- Portal valid/revoked: PASS — smoke `portal_token`, `portal_documents`,
  `portal_messaging`, and `token_enforcement` gates (the latter revokes a
  real staging portal link and confirms 404 on subsequent document/message
  access). Portal *expired*-token behavior was not independently
  re-exercised against staging (no supported way to fabricate token expiry
  via the API alone without direct DB manipulation, which this sprint does
  not authorize) — relying on the identical, already-deployed code path
  verified locally (PT-03, `test_portal.py::test_expired_portal_link_reads_as_expired_and_returns_no_data`
  and `portal-token-lifecycle.spec.ts`).
- Messaging/documents: PASS — smoke `staff_document`, `portal_documents`,
  `portal_messaging` gates.
- Command Centre: PASS — smoke `command_centre` gate.
- Security headers/runtime behavior: PASS — smoke `liveness`/`readiness`/
  `postgresql`/`cors_allowed`/`cors_denied` gates, plus a direct header
  check on `/health` confirming HSTS, `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, and a request ID all present.

**No new staging-only defect was found.** No UAT-004 was opened.

## Staging smoke (`scripts/staging/smoke.py`, 27 gates)

**20 passed / 0 failed / 7 blocked** — exactly matches the Sprint 027
baseline (20/0/7 of 27), no unexplained new failure.

Blocked (by design, each with a documented separate-verification path, all
independently satisfied above or in Phase 8):
- `migration` — verified separately via `railway ssh ... alembic current` above.
- `no_seeding` — `SEED_DATA_ENABLED=false` confirmed in `simo-api-staging`'s config.
- `follow_up_notification` — the job has no HTTP trigger by design; verified separately via `railway ssh` above.
- `restart_persistence` — requires `--allow-restart`, out of this sprint's scope (no restart-persistence regression suspected).
- `logs_request_ids` — requires an approved safe test-only failure trigger, not exercised.
- `repository_secret_scan` — must run locally, not via HTTP; satisfied by this sprint's own SH-07 local scan.
- `backup_restore` — requires a separately approved destructive-risk drill (Sprint 029/030 territory, not this sprint's).

**Production was not touched at any point during staging verification** — every
command above targeted `simo-api-staging`/`simo-web-staging` in the `staging`
environment only.

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

**All six invariants reconfirmed this sprint** — same evidence cited against
CE-03/AV-03/PO-04/HO-05/FU-05 above, plus `test_portal.py`'s revoked/expired
tests for the portal invariant. No regression found in any of them.

## UX acceptance (Phase 14)

For every major journey inspected above, additionally check: discoverability,
label clarity, loading state, pending state, success state, error state,
retryability, disabled-state behavior, reload persistence, terminal-action
visibility, navigation correctness. Fix only objectively broken/confusing
behavior on existing workflows — this sprint does not redesign pages for
subjective preference.

Checked across the connected journey and per-feature Playwright specs (all of
which assert loading/error/disabled states explicitly, e.g.
`DashboardStatusBar`'s error state, `StatCardSkeleton` loading state, and
every reload-persistence check already cited per matrix row above). Two
label-clarity defects were found and fixed this sprint: UAT-001 (identity
labels) and UAT-002 (financial-total label). No other objectively
broken/confusing UX found — no redesign performed.

---

## LOCKED ACCEPTANCE CONTRACT

This section is the sprint's frozen scope. It is committed separately from
the discovery draft above and, once committed, is not renegotiated mid-sprint
except by explicitly re-opening discovery in a follow-up commit.

1. **Scope is closed.** The acceptance matrix (§ "Acceptance matrix (Phase 6)",
   72 rows across categories A–L) is the complete set of scenarios Sprint 028
   evaluates. No row is silently dropped; a row that cannot run is recorded
   BLOCKED with a stated reason, never omitted.
2. **Severity is fixed.** The BLOCKER/HIGH/MEDIUM/LOW definitions in
   "Severity definitions (Phase 4 — LOCKED)" are final for this sprint. No
   defect is downgraded to ease closeout.
3. **No product code changes before this commit.** Everything before this
   point in the sprint is documentation only. Phase 7 (local regression
   baseline) is the first phase permitted to touch anything outside
   `docs/SPRINTS/sprint-028.md`, and only to run — not modify — existing
   suites. Product code changes begin only once a genuine `UAT-XXX` defect is
   identified per the Defect handling rules above.
4. **Journey reuse is mandatory.** The Sprint 027 connected E2E journey
   (`apps/web/e2e/full-system-journey.spec.ts`) and the 27-gate staging smoke
   suite (`scripts/staging/smoke.py`) are reused as-is and extended only for a
   proven acceptance gap — never duplicated or replaced.
5. **No feature creep.** Anything the matrix surfaces that was never part of
   a shipped contract (Sprints 008–027) is logged as
   **PRODUCT ENHANCEMENT — DEFERRED**, not built in this sprint.
6. **Exit criteria are fixed** as stated in "Exit criteria" above: this
   sprint closes only at BLOCKER = 0, HIGH = 0, and every core scenario,
   persona, tenant-isolation, portal-token, follow-up, connected-journey,
   Command Centre, and staging check at PASS (or explicitly justified
   BLOCKED), with all MEDIUM/LOW dispositioned.
7. **Both personas, both layers.** Every RBAC-gated scenario in categories B
   and G is verified at the frontend (visibility) and backend (enforcement)
   independently; a hidden button is never accepted as proof of enforcement.
8. **Production is out of reach.** Sprint 028 targets the `sprint-028-uat-bugfix-cycle`
   branch and, for staging verification, Railway's `simo-os` staging
   environment only (`simo-api-staging`, `simo-web-staging`). No production
   service is created, deployed to, or modified under this contract.

Locked by this commit. Execution (Phase 7 onward) begins next.

---

## Closeout

### Exit criteria — final check

- BLOCKER open: **0** (none found).
- HIGH open: **0** (none found).
- MEDIUM open: **0** — UAT-001 and UAT-002 both found MEDIUM, both fixed.
- LOW open: **0** — UAT-003 found LOW, fixed (not merely deferred).
- Every core acceptance-matrix row: **72/72 PASS** (§ "Matrix totals" above).
- Connected journey (`full-system-journey.spec.ts`): **PASS**.
- Owner: **PASS**. Staff: **PASS**. Tenant isolation: **PASS**.
- Portal token matrix (valid/revoked/expired): **PASS** (expired verified
  locally only — see staging-UAT note above; identical code path).
- Follow-up automation: **PASS** (local + independently on staging).
- Command Centre: **PASS** (local + staging).
- Staging UAT: **PASS**. Staging smoke: **acceptable** (20/0/7 of 27,
  identical to the Sprint 027 baseline).
- **All exit criteria satisfied — Sprint 028 may close.**

### Git / commits (this sprint, `e4a0463..HEAD` at closeout time)

- Baseline: `main` @ `7f24ac6` (Sprint 027 merge, PR #9).
- Branch: `sprint-028-uat-bugfix-cycle`.
- Discovery: `40cf252` — `docs: define Sprint 028 UAT matrix`.
- Contract lock: `e4a0463` — `docs: lock Sprint 028 acceptance contract`.
- UAT-001 RED: `cc00dfa`. UAT-001 GREEN: `d6e7c09`.
- Coverage (no defect) — AT-04: `9e29728`. QT-05: `a4ce752`. AV-04: `b78f8a9`.
- UAT-002 RED: `57b6d86`. UAT-002 GREEN: `28e1c15`.
- UAT-001 test-correctness follow-up: `0d776f7`.
- UAT-003 RED: `a63dab0`. UAT-003 GREEN: `66a19d5`.
- Phase 7/8 evidence: `d356dc0` — final reviewed feature HEAD, deployed to staging.
- This closeout commit (docs only).

### Test totals (final)

- Backend (`pytest`): **550 passed, 1 skipped, 0 failed**.
- Frontend component tests (`pnpm --filter web test`): **69/69 passed**
  (12 files).
- Playwright (full suite, 13 specs): **13/13 passed** (11 concurrently in
  one run + the remaining 2 individually, after isolating a confirmed
  local resource-contention flake — not a product defect, see Phase 7/8
  evidence commit for detail).
- Type-check (`tsc --noEmit`): clean.
- Lint (`pnpm --filter web lint`): clean.
- `pnpm --filter web test:runtime-config`: 7/7 passed.
- `pnpm --filter web test:docker-contract`: 5/5 passed.
- `pnpm build`: clean, 14 routes.
- Alembic: single head `2243d66f83da`, local and staging both at head; `alembic check` clean.
- `git diff --check`: clean.
- Feature CI (`d356dc0`): backend GREEN, frontend GREEN, e2e GREEN.

### Staging

- Deployed SHA: `d356dc06b359a9976a5aa782ab2ffe080490258a` (exact feature HEAD).
- `/health`: 200. `/ready`: 200.
- `alembic current` (staging): `2243d66f83da (head)` — matches `alembic heads`.
- Smoke: 20 passed / 0 failed / 7 blocked (of 27) — matches Sprint 027 baseline.
- Production: **untouched** (only `simo-api-staging`/`simo-web-staging` in the `staging` environment were targeted).

### Safety

- Production deployed: **NO**. Production DB touched: **NO**. Production
  config changed: **NO**. Production Railway services: **not targeted**.
- New product features added: **NO** — every code change this sprint fixed
  a labeling/coverage defect in already-shipped behavior; no new capability.
- Rebase used: **NO**. Force push used: **NO**.

### Ready for PR

All required evidence is in place: 72/72 matrix PASS, 0 open BLOCKER/HIGH/
MEDIUM/LOW, connected journey/Owner/Staff/tenant-isolation/portal/follow-up/
Command Centre all PASS, staging PASS, smoke acceptable, feature CI GREEN,
production untouched. Proceeding to PR against `main`.
