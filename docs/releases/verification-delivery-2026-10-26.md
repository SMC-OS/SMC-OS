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
