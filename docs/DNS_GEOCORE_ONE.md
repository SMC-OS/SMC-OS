# geocore.one — proposed DNS change sheet (for owner review)

**Status:** PROPOSAL ONLY. Nothing here has been applied. No registrar or DNS
change has been made, no GoDaddy credential has been requested, stored, or
used, and none is needed to review this document.

**Registrar / DNS host:** GoDaddy
**Mail:** Microsoft 365, already live and outside this repository
**Target hosting:** Railway (two services — see `deploy/railway/`)

---

## 0. What was verified, and what you must verify

Be precise about this, because the "existing record conflict" column is only
as good as the zone it was checked against.

| Claim | Verified how | Confidence |
|---|---|---|
| The application sends **no email of any kind** | Read the whole backend: no SMTP client, no SendGrid/Resend/Postmark/SES integration, no `send_email` anywhere. `app/notifications/` is in-app only. | **Certain** — this is why nothing below touches a mail record |
| The repository contains **no public marketing site** | `apps/web/app/page.tsx` is the authenticated dashboard; it redirects to `/login`. There is no `robots.ts`, no `sitemap.ts`. | **Certain** — see §5, this changes the apex recommendation |
| Two hosted services are needed (web + API) | `deploy/railway/web.railway.toml`, `deploy/railway/api.railway.toml` | **Certain** |
| The **current live contents** of the geocore.one zone | **Not verified.** Outbound DNS resolvers are blocked from this environment, so the live zone could not be read. | **Unverified — you must check** |

Every "conflict" flagged below is therefore a *class* of conflict that is
near-universal on a GoDaddy domain, not a record I have observed on yours.
Run §6 before applying anything.

---

## 1. Records to ADD

Two of the three target values are issued by Railway when you add the custom
domain to the service — Railway shows the exact target in the "Add custom
domain" dialog. **Copy those verbatim; do not transcribe them from here or
from any other domain's setup.** I have deliberately not invented a value.

| # | Type | Host / Name | Target / Value | TTL | Action | Purpose | Existing record conflict |
|---|---|---|---|---|---|---|---|
| 1 | CNAME | `app` | *Railway target for the **web** service* (`<id>.up.railway.app`) | 600 | **ADD** | `app.geocore.one` → GeoCore application | None expected. Conflicts only if an `app` record already exists. |
| 2 | CNAME | `api` | *Railway target for the **api** service* (`<id>.up.railway.app`) | 600 | **ADD** | `api.geocore.one` → GeoCore API | None expected. Conflicts only if an `api` record already exists. |
| 3 | CNAME | `www` | `app.geocore.one` *(or the marketing host, see §5)* | 600 | **ADD / MODIFY** | Canonical `www` handling | **Likely conflict** — GoDaddy provisions a default `www` CNAME (usually to a parked/forwarding target) on most domains. See §2. |

Ordering note: add the domain in Railway **first**, then create the DNS
record. Railway issues the TLS certificate by validating the DNS record, so a
record created before the service knows about the hostname simply resolves to
a 404 until you complete the Railway side.

### The apex (`geocore.one`) is deliberately not in the table above

Two independent reasons, both of which need your decision before an apex
record makes sense:

1. **Technical (GoDaddy).** GoDaddy's nameservers support neither ALIAS/ANAME
   records nor CNAME flattening at the zone apex. A bare `geocore.one` can
   therefore only be an **A/AAAA record to a literal IP address** (or GoDaddy
   *Forwarding*, which is a redirect, not hosting). If Railway gives you an
   apex A-record IP in its custom-domain dialog, use that — an IP you find
   anywhere else will break silently when it changes.
2. **Product (more important).** See §5 — there is nothing to put there yet.

---

## 2. Records to MODIFY or DELETE (expected conflicts)

| # | Type | Host / Name | Current value (typical) | TTL | Action | Purpose | Notes |
|---|---|---|---|---|---|---|---|
| 4 | A | `@` | GoDaddy parking IP (commonly `Parked` / an `AfternicDNS` address) | 600 | **DELETE or MODIFY** | Frees the apex | Only once §5 is decided. A parked apex must not be left pointing at a parking page once the brand is live. |
| 5 | CNAME | `www` | GoDaddy default (parked / `_domainconnect` style target) | 600 | **MODIFY** | Replaced by record #3 | Standard GoDaddy default; check yours. |
| 6 | CAA | `@` | *(only if present)* | — | **REVIEW ONLY** | TLS issuance | If a CAA record exists and does not permit `letsencrypt.org`, Railway's certificate issuance will fail with no obvious error. If no CAA record exists, nothing to do — that is the common case. |

Records #4 and #5 are the only deletions proposed anywhere in this document,
and neither is mail-related.

---

## 3. Records that must NOT be changed — Microsoft 365 mail

**No change is proposed to any record below, and none is required.** The
application sends no email (§0), so the GeoCore production cutover has zero
overlap with your mail configuration. This section exists so that a record
here is never touched by accident during the cutover.

| Type | Host / Name | Purpose | Action |
|---|---|---|---|
| MX | `@` | Microsoft 365 mail routing (`geocore-one.mail.protection.outlook.com`) | **DO NOT TOUCH** |
| TXT | `@` | SPF (`v=spf1 include:spf.protection.outlook.com -all`) | **DO NOT TOUCH** |
| CNAME | `selector1._domainkey` | DKIM key 1 | **DO NOT TOUCH** |
| CNAME | `selector2._domainkey` | DKIM key 2 | **DO NOT TOUCH** |
| TXT | `_dmarc` | DMARC policy | **DO NOT TOUCH** |
| CNAME | `autodiscover` | Outlook autodiscover | **DO NOT TOUCH** |
| TXT | `@` | `MS=msXXXXXXXX` domain verification | **DO NOT TOUCH** |
| CNAME/SRV | `enterpriseregistration`, `enterpriseenrollment`, `_sip`, `_sipfederationtls`, `lyncdiscover` | Entra ID / Teams, if provisioned | **DO NOT TOUCH** |

**One specific trap.** A domain can hold only one SPF record. If GeoCore ever
starts sending transactional email from `geocore.one` (quote-ready emails,
portal-link notifications, password resets — none of which exist today), that
will require **modifying the existing SPF TXT record in place** to add the
provider's `include:`, never adding a second SPF record. Two SPF records is a
permanent-fail configuration that silently breaks Microsoft 365 delivery. That
change is out of scope here and would come back to you as its own proposal.

---

## 4. Complete proposed record table (single view)

| # | Type | Host | Target / Value | TTL | Action | Purpose | Conflict |
|---|---|---|---|---|---|---|---|
| 1 | CNAME | `app` | Railway web-service target | 600 | ADD | GeoCore application | Check `app` is free |
| 2 | CNAME | `api` | Railway api-service target | 600 | ADD | GeoCore API | Check `api` is free |
| 3 | CNAME | `www` | `app.geocore.one` or marketing host | 600 | ADD/MODIFY | Canonical www | Likely GoDaddy default present |
| 4 | A | `@` | *(pending §5 decision)* | 600 | MODIFY/DELETE | Frees apex from parking | Parking A record likely |
| 5 | CNAME | `www` | GoDaddy default | — | DELETE | Superseded by #3 | Same record as #3 |
| 6 | CAA | `@` | *(review only)* | — | NONE | TLS issuance check | Only if a CAA record exists |
| — | MX / SPF / DKIM / DMARC / autodiscover / MS= | various | unchanged | — | **NONE** | Microsoft 365 mail | Explicitly untouched |

**Net: 2 unambiguous additions, 1 www decision, 1 apex decision, 0 mail changes.**

---

## 5. The apex decision — a technical reason to deviate from the preferred structure

Your preferred structure is:

- `geocore.one` → public GeoCore website / landing page
- `app.geocore.one` → GeoCore application
- `api.geocore.one` → GeoCore API

**Records 1 and 2 match that exactly and should be applied as written.** The
apex is the part that needs a decision, because **this repository contains no
public website to serve from it.** `apps/web/app/page.tsx` is the authenticated
dashboard: an anonymous visitor is redirected to `/login`.

So pointing `geocore.one` at the web service today would make the root domain
resolve to a login redirect. That is the single worst outcome available for the
domain: the root is the strongest SEO asset the brand will ever have, and a
login wall gives a crawler nothing to index and nothing to rank — while
permanently associating the domain's first impression with a gate.

Three options, in order of preference:

| Option | What the apex serves | Effort | Recommendation |
|---|---|---|---|
| **A. Build a real marketing site** at the apex — positioning, product pages, pricing, case studies, blog | A genuine SEO surface | Highest | **Recommended.** This is the version of the structure you actually want, and the domain's ranking authority compounds from the day it exists rather than from whenever it is retrofitted. |
| **B. Static holding page** at the apex now, replaced by A later | A single indexable branded page | Low | Sound interim step. Keeps the apex out of a parking page and off a login redirect, and does not need to be undone. |
| **C. Apex → 301 redirect to `app.geocore.one`** | Nothing | Lowest | **Not recommended.** Concedes the root domain's authority to a page that will never rank, and is the hardest option to reverse cleanly once links accumulate. |

Until A or B exists, **hold records 4 and 5** and apply only 1 and 2. The
application and API go live on their own subdomains with no dependency on the
apex — nothing about the cutover is blocked by this decision.

Two related items, both application work rather than DNS, that should land
alongside the cutover: `app.geocore.one` and `api.geocore.one` need
`X-Robots-Tag: noindex` (there is no `robots.ts` in `apps/web` today), so the
application's own URLs never compete with the marketing site in search
results; and whichever host serves the apex needs a canonical tag and a
sitemap.

---

## 6. Pre-flight — run these before applying anything

Read-only. They confirm what is actually in the live zone, so the conflict
column above is checked rather than assumed.

```bash
# Every record currently on the apex and the two target subdomains
dig geocore.one            ANY   +noall +answer
dig www.geocore.one        CNAME +noall +answer
dig app.geocore.one        CNAME +noall +answer   # expect: empty
dig api.geocore.one        CNAME +noall +answer   # expect: empty

# Mail records — capture these BEFORE and compare AFTER; they must be identical
dig geocore.one            MX    +noall +answer
dig geocore.one            TXT   +noall +answer   # SPF + MS= verification
dig _dmarc.geocore.one     TXT   +noall +answer
dig selector1._domainkey.geocore.one CNAME +noall +answer
dig selector2._domainkey.geocore.one CNAME +noall +answer
dig autodiscover.geocore.one CNAME +noall +answer

# TLS issuance blocker
dig geocore.one            CAA   +noall +answer   # usually empty; that is fine
```

**Save the output of the mail block.** Re-running it after the change and
diffing against the saved copy is the actual proof that Microsoft 365 was not
disturbed — stronger than checking that mail still arrives, which can lag.

---

## 7. Application configuration that must land with the cutover

DNS alone does not complete this. These are enforced at startup by
`app/core/config.py` and `apps/web/lib/runtime-config.ts`, and a mismatch is a
hard failure, not a degraded mode:

| Service | Variable | Value |
|---|---|---|
| API | `CORS_ALLOWED_ORIGINS` | `https://app.geocore.one` (plus the apex host once §5 is decided). Must be HTTPS, scheme+host only, no `*`. |
| API | `FRONTEND_BASE_URL` | `https://app.geocore.one` — where Stripe Checkout returns to. |
| Web | `NEXT_PUBLIC_API_URL` | `https://api.geocore.one` — must be an absolute HTTPS origin when `APP_ENV=production`. |

Set these **before** repointing DNS. The web app throws on boot if
`NEXT_PUBLIC_API_URL` is missing under `APP_ENV=production`, and the API
rejects a non-HTTPS or wildcard CORS origin outright.

---

## 8. Rollback

| Change | Rollback | Recovery time |
|---|---|---|
| Records 1, 2 (ADD) | Delete the record | One TTL (600s) |
| Record 3 (`www`) | Restore the value captured in §6 | One TTL |
| Records 4, 5 (apex) | Restore the values captured in §6 | One TTL |
| Mail records | **N/A — not changed** | — |

Keep TTL at 600 through the cutover; raise it to 3600 once the records have
been stable for a week.

---

## 9. Sign-off

Applied by the domain owner only. Nothing in this document is executed
automatically, and no credential for the registrar is held by, or should be
given to, this repository or any assistant working in it.

- [ ] §6 pre-flight run; live zone captured; mail block saved
- [ ] §5 apex decision made (A / B / C)
- [ ] §7 environment variables set on both Railway services
- [ ] Custom domains added in Railway; exact targets copied into records 1–2
- [ ] Records applied
- [ ] §6 mail block re-run and diffed against the saved copy — no change
- [ ] `https://app.geocore.one` and `https://api.geocore.one` serve valid TLS
