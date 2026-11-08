# 08 — Legal, support, freeze and handover

An agent cannot give legal approval, VAT/ICO advice or confirmation that an inbox is monitored. Every such item below stays **BLOCKED** with a named owner.

## Facts on record (from `docs/LEGAL_REVIEW_CHECKLIST.md` at `63e8ac9`; not re-verified)

- Operator: Mohammad Al Kawarit trading as GeoCore, UK sole trader. No limited company and no Companies House number.
- Address: Suite RA01, 195-197 Wood Street, London, E17 3NU (LVA virtual office, business-address upgrade per owner, 3 Nov 2026). KYC, mail forwarding and legal-notice conditions are still to be confirmed.
- VAT number: none evidenced. Do not show one.

## Status

| Item | State | Owner |
|---|---|---|
| UK Terms, Privacy, DPA, cookies, subprocessors and transfer routes, cancellation, refunds, renewal, retention | BLOCKED: external professional review not evidenced | Owner + UK solicitor |
| ICO data-protection fee decision | BLOCKED | Owner |
| VAT and HMRC position | BLOCKED | Owner + accountant |
| Whether the live Stripe active subscription is a real customer | BLOCKED | Owner |
| Monitored support and privacy inboxes with real receipt confirmation | BLOCKED: needs a real mailbox test by the owner; provider "accepted" is not "delivered" | Owner |
| Support hours, response targets, escalation and incident runbook | BLOCKED: no adopted SLA found. Do not promise 24/7 support or any RTO/RPO | Owner |
| **Release freeze: server-side admission gate** | **Implemented on the QA branch (local tests pass); not deployed.** Closing admission is one setting: `NEW_ACCOUNT_ADMISSION=closed` | Owner sets it on staging and then production after review |
| Public marketing CTA ("Start 14-Day Free Trial") | NOT CHANGED. Marketing is a separate service (`legal/sole-trader-identity-20261102`). The app's sign-up page now shows the server's "not accepting new accounts" message and a "Request a demo" link on 403 | Owner decides on a marketing copy change |
| Customer handover pack (admin, staff, quote and project guides, SLA, terms, incident and restore runbooks, tested limits, release notes, known limitations) | NOT PRODUCED as customer-ready, because its inputs (SLA, approved terms, tested capacity and restore) do not exist yet | Owner, after the gates above |

## Closing admission safely (procedure for the owner)

1. Merge the reviewed admission commit into the release path; this needs an owner-approved promotion.
2. On staging, set `NEW_ACCOUNT_ADMISSION=closed` and redeploy.
3. Check that `GET /api/v1/auth/admission` returns `{"signups_open": false}`.
4. Check that `POST /api/v1/auth/signup` returns 403.
5. Check that an existing owner can still sign in.
6. Repeat on production in an owner-approved window.
7. Reopen by setting `open`. No data changes either way.
