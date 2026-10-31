# Launch acceptance record — 31 October 2026

## Decision

Launch acceptance remains OPEN. Production health and the tested live quote journey pass. Do not describe the service as fully audited, error-free, or capacity-certified, and do not advertise a supported concurrent-user limit yet.

This is an evidence record and execution plan, not legal approval or a completed recovery/load-test certificate.

## Verified production evidence

- Railway: six production services healthy, zero reported recent deployment failures in the 24-hour window, no pending production changes.
- API/web/marketing baseline: `d5f6012dc99f8e58c5c0f2df4ba6327dbe97201d`.
- Owner workspace: exact lowercase `support@geocore.one` owns SMC; complimentary Pro access was independently read back and live sign-in succeeded.
- Live quote: Review → Previous → Review left the list at three draft records. One Save increased it to four. The new synthetic QA Launch Quartz quote reopened with one line, £1,200 subtotal, £120 discount, £216 VAT, £1,296 total.
- Invoice PDF downloaded both from the wizard and after reopening. Text extraction confirmed the same figures and Invoice-000003. This is one live scenario, not a comprehensive PDF-layout audit.
- Live Stripe portal configurations: empty. A working paid customer portal is not established.
- Published Terms still explicitly leave refund terms undecided and several contractual sections subject to legal review. Company registration remains pending, confirmed by the owner during this review.
- Owner volunteered to monitor support/privacy mailboxes. Monitoring hours, response targets and a tested delivery/escalation path remain unconfirmed.
- Production API 24-hour memory range: approximately 0.100–0.152 GB; database disk approximately 0.922 GB. Idle/light-use resource metrics do not establish capacity.

## Fix candidate

The candidate carries forward PR #54's email-delivery outcome fix onto the deployed baseline. Failed, suppressed, pending and provider-accepted outcomes are distinguished. Provider acceptance never claims inbox delivery. Existing verification token, cooldown and access checks remain in force.

It also adds a server-derived complimentary-billing disclosure. A legacy access grant without a Stripe subscription is shown as complimentary, with no recurring charge or expiry; paid portal/cancel controls are omitted for that state. A grant that also has a Stripe subscription is not described as free. This is presentation of the existing entitlement, not a new privilege grant.

These changes need CI, review and deployment before they change the live application.

Local validation passed 101 focused backend checks and all 413 frontend tests, plus TypeScript, scoped ESLint and whitespace checks. Full PostgreSQL/E2E CI remains a release gate. The initial CI dependency audit found seven advisories in the existing pypdf 6.21.2 pin; the candidate updates that PDF inspection dependency to the maintainer's patched 6.21.4 release and requires a clean audit rerun.

## Gate 1 — onboarding

Status: PREPARED, not passed. The owner requested preparation before supplying a new test mailbox.

1. Use an owner-controlled unused mailbox and an isolated fresh browser session. Create a uniquely named QA Launch workspace through public signup; do not reuse the permanent owner account.
2. Record selected plan, trial start/end and workspace identity. Confirm no card or paid subscription is created at signup.
3. Verify protected business routes are denied before email verification. Observe actual delivery outcome and mailbox receipt; do not equate HTTP 200, DNS records or a provider acceptance event with inbox receipt.
4. Follow the actual email link. Confirm single-use and expiration behavior, log out, sign in again, and verify the new workspace identity and absence of the SMC workspace's customer data.
5. Test resend failure/suppression messaging after deploying the fix. Record redacted outcomes; never retain raw verification tokens or passwords in evidence.

## Gate 2 — billing

Status: OPEN. Signature/resource-dispatch regression tests are not payment lifecycle acceptance.

- Use the existing GeoCore sandbox and staging integration, not live cards or the complimentary SMC workspace.
- Confirm all eight configured recurring prices, test keys, signed webhook endpoint, API version and destination belong to the same sandbox.
- Configure and test a customer portal: invoices, payment-method updates, and cancellation at period end. No self-service plan changes are required for the initial cancellation test. Do not enable tax collection or publish refund terms without a confirmed business/VAT position.
- Expire one synthetic no-card trial, complete hosted Checkout with a Stripe test payment method, and verify the signed subscription/invoice events activate the matching workspace. Confirm one subscription, server-side prices and amounts, and no activation solely from a success redirect.
- Test immediate payment failure and a renewal failure with a test clock. Verify the expected past-due/unpaid state, access policy, recovery, and duplicate/out-of-order event handling.
- Cancel through the portal, verify paid-through access and final expiry, then test resumption before expiry. Record webhook deliveries and application state, not only Stripe state.
- Portal configuration writes were previously blocked by connector permissions/approval. Do not retry through a different identity or browser to bypass that restriction.
- Any real-money payment requires a separately agreed amount and owner-controlled payment step. No live charge was made in this review.

## Gate 3 — legal and privacy

Status: OPEN; do not invent missing business facts.

| Record | Confirmed | Needed before publication/sign-off |
| --- | --- | --- |
| Contracting entity | Intended company registration pending | Actual current contracting person/business, service address, registration when available, VAT status |
| Hosting | Railway services/volumes in `ams` | Account-specific DPA applicability, access/support processing, onward providers and transfer assessment |
| Stripe | Live GeoCore account and sandbox exist | Correct contracting entity; applicable controller/processor roles; accepted DPA/transfer terms evidence |
| Email | Resend implemented/configured by variable name | Account DPA record, actual processing/retention settings, delivery and mailbox proof |
| AI/marketing | OpenAI/Gemini/Meta are conditional in code | Which are enabled, exact account settings, data flows, retention, regions and transfer arrangements |
| Retention | 30-day workspace deletion recovery window | Adopted periods/criteria for accounting, security, suppression and backups; automated enforcement and holds |
| ICO | No confirmed assessment/registration evidence | Complete ICO fee self-assessment for the actual operator; retain outcome and pay/register if required |
| Subscription terms | Price/interval and recurring wording exist | Approved VAT treatment, renewal, cancellation and refund position |

Railway's Amsterdam resource location is not proof that every provider or support subprocess occurs only there. A provider's public DPA does not prove GeoCore's account configuration, contractual party or completed transfer assessment.

Review sources checked on 31 October 2026:

- ICO fee assessment: https://ico.org.uk/for-organisations/data-protection-fee/data-protection-fee-self-assessment/
- ICO processor contract requirements: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/contracts-and-liabilities-between-controllers-and-processors-multi/what-needs-to-be-included-in-the-contract/
- Railway DPA: https://railway.com/legal/dpa
- Resend DPA and subprocessors: https://resend.com/legal/dpa and https://resend.com/legal/subprocessors
- Stripe UK DPA: https://stripe.com/gb/legal/dpa

## Gate 4 — recovery and support

Status: OPEN. Offline upload-recovery tool tests passed; this does not demonstrate a matched hosted database/upload restore.

Use `docs/STAGING_RUNBOOK.md`'s existing approval gates. Before the backup phase, present the exact maintenance window, writer freeze, chosen synthetic document IDs and common database recovery timestamp. Read back source volume mounts and backup ownership/schedules; do not restore onto an active mount.

Proposed scratch names, if paid resources are necessary:

- `simo-postgres-recovery-launch-20261031`
- `simo-api-recovery-launch-20261031`
- `simo-uploads-recovery-launch-20261031`

No scratch resources or backups were created in this review. Cost/size/duration must be approved before provisioning. Independently hash the database dump, upload archive, manifest and correlation record; then present exact targets and hashes for the restore approval. Restore only into isolated scratch targets, never active staging or production. Test staff and customer-portal download hashes, tenant isolation, metadata relationships, Alembic revision and common recovery point; record measured RPO/RTO. Obtain separate cleanup approval where the runbook requires it.

Owner-operated support still needs documented hours, target acknowledgement/resolution times, an incident escalation contact and a tested mailbox/alert route. Prepare a timed incident exercise and retain a redacted incident log. Do not promise 24/7 monitoring or guaranteed response times without coverage.

## Gate 5 — capacity

Status: NOT RUN for representative concurrent writes/PDFs/uploads. Supported simultaneous-use limit remains unverified.

Staging currently runs an older release. A staging-only source update was prepared for all three application services to pin the deployed production baseline. Review the patch before applying; it contains source changes only and no production or volume changes. Subsequent fix-candidate testing must identify its exact SHA separately from the production baseline.

Execution specification after staging is current and ready:

1. Record deployed SHA, migrations, service limits/replicas, database connection settings and starting disk/memory. Use synthetic test workspaces and at least two tenants; fixture verification is explicitly not evidence of mailbox onboarding.
2. Ramp 1, 5, 10, 25, 50 and 100 active users, with independent sessions and realistic think time. Registered businesses and active concurrent users must be reported separately.
3. Mix customer/quote reads, quote creation/reopen, real PDF generation/download and 64 KiB–1 MiB uploads/downloads. Bound total data to the staging volume budget. Include long/multipage quotes and overlapping requests within and across tenants.
4. Measure per-operation p50/p95/p99, throughput, unexpected errors, connection waits, CPU/memory, storage and row-count/hash correctness. Stop escalation at any tenant leak, corrupt file, duplicate save, sustained 5xx/timeout, memory pressure or storage threshold.
5. Proposed acceptance targets, to be adopted before the run: zero unexpected errors/data-integrity faults; p95 reads ≤2s, saves ≤5s, PDFs ≤10s and 1 MiB uploads ≤10s. Hold each level and repeat the highest candidate level with a 30-minute soak and at least 1,000 completed mixed journeys. A short public-read burst is insufficient.
6. Publish a supported limit only from repeated passing runs with operational headroom. Include tested workload, release, hardware, duration and exclusions. Do not derive a limit from free RAM or API worker/connection counts.

Current upload storage is a volume on a single API replica. Do not add API replicas as a capacity shortcut without verifying that every replica can access the required file bytes.

## Release sequence

1. CI and review of the outcome/complimentary-display fix candidate.
2. Explicit approval to deploy the reviewed staging candidate, then readiness/migration checks.
3. Fresh mailbox onboarding, sandbox billing, approved matched recovery drill and representative capacity run.
4. Adopt legal/operator, retention, VAT/refund and support details; publish reviewed notices.
5. Deploy approved production release and repeat live smoke checks before handing over to external businesses.

Production promotion to 100 businesses remains on hold pending these gates.
