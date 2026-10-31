# Verification email incident — 26 October 2026

## Confirmed application defect

At production source 806ffcd, verification_service ignored the Communication return value and swallowed provider exceptions. The resend endpoint unconditionally reported sent, and the frontend rendered a green success message for any HTTP 200. This concealed real failures. A missing outcome field from an older backend must not be treated as evidence of acceptance.

The patch returns the communication outcome, reports sent (provider acceptance only), failed, suppressed or pending, and presents the outcome in the UI. The initial holding screen no longer assumes signup delivery succeeded. Signup remains recoverable, tokens stay single-use, the cooldown remains enforced, and vendor details are not returned to the user. Existing verification is never bypassed.

## Provider / inbox investigation remains open

Read-only Cloudflare inspection found DKIM TXT records for resend._domainkey.send.geocore.one and resend._domainkey.geocore.one, DNS-only Resend CNAMEs, Microsoft 365 apex SPF/MX, and apex DMARC p=quarantine with relaxed alignment. These records are configuration evidence, not proof of successful per-message authentication, active provider credentials, sender verification in the correct Resend account, or inbox delivery.

No DNS policy was weakened or changed. No API key, cookie, verification token, or email body was read. No test messages were sent.

Read the affected address's communications ledger: status, failure_category/detail, provider_message_id and timestamps; inspect the corresponding Resend event. For an email in junk, inspect Authentication-Results, DKIM-Signature d= and Return-Path plus the receiver's spam verdict. Do not infer missing credentials vs domain failure from an HTTP 200.

Outstanding: production per-address rows and provider events; Gmail/Outlook mailbox outcomes; message-header authentication and filtering verdict. The reporting fix does not establish or repair the underlying provider/recipient fault on its own.

## Release

No migration needed. API first, then web. Verify one owner-requested resend using the affected signed-in account, record the ledger/provider outcome and recipient observation. Provider accepted is not inbox delivered. Maintain Microsoft 365 DNS and DMARC protection.

## Owner-provided production ledger evidence

On 26 October the owner ran a read-only query in the production API container. The latest eight verification attempts for the support address (both case-distinct accounts/tenants), dated 16–26 October, all returned failed/permanent with provider HTTP 403 and no provider message ID. The latest was 2026-10-26 03:17:10 UTC. No suppression row appeared in the query output. Resend rejected these attempts before acceptance. The exact provider error name/body remains missing: 403 alone does not distinguish sender-domain verification, testing restrictions, inactive/suspended credentials or permission issues. Inspect Resend Logs for POST /emails at that timestamp; do not fabricate a narrower diagnosis. The separate junk-folder issue still needs accepted-message headers.

CI at 93945ca: backend and frontend passed; browser suite had 73 pass and one old success-copy assertion fail in email-verification.spec.ts:98. Updated that journey to assert the real no-provider failure outcome and visible alert, while still verifying the token-recovery flow. Rerun required.
