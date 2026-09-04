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
| A public marketing site now exists for the apex | `apps/marketing` — a statically prerendered, indexable GeoCore site. Built and served locally; `robots.txt`, `sitemap.xml`, canonical tag and JSON-LD all verified in the rendered output. | **Certain** — resolves the apex question raised in the previous revision |
| The application host must not be indexed | `apps/web/app/robots.ts` returns `Disallow: /` unconditionally; asserted by `apps/web/app/robots.test.mjs` | **Certain** |
| **Three** hosted services are needed (marketing + web + API) | `deploy/railway/marketing.railway.toml`, `web.railway.toml`, `api.railway.toml` | **Certain** |
| The **current live contents** of the geocore.one zone | **Not verified.** The egress proxy denies every public DNS resolver (`dns.google`, `cloudflare-dns.com`) *and* `geocore.one` itself. Re-tested at Phase 3; still blocked. | **Unverified — you must check (§6)** |
| The **Railway targets** for each custom domain | **Not obtainable.** The egress proxy denies `railway.com` and `backboard.railway.app`; no Railway CLI or credential exists in this environment. | **Owner-supplied (§5A)** |
| Whether `sales@geocore.one` exists | **Not verifiable.** No route to Microsoft 365 from this environment. The pricing page no longer hardcodes it — see §7. | **Owner action** |
| Every application-side behaviour listed in §7 | **Verified** against real running services (API + web + marketing, production builds, real Chromium): 66 checks including tenant isolation, PDF letterheads, portal downloads, robots, canonical, sitemap and the pre-rebrand session migration. | **Certain** |

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
| 3 | A | `@` | *Railway apex target for the **marketing** service* | 600 | **ADD / MODIFY** | `geocore.one` → GeoCore public website | **Likely conflict** — a GoDaddy parking A record. See §2. |
| 4 | — | `www` | Redirect `www.geocore.one` → `https://geocore.one` (301) | — | **ADD / MODIFY** | Canonical host consolidation | **Likely conflict** — GoDaddy provisions a default `www` CNAME. See §2 and the note below. |

### On record 4 (`www` → apex redirect)

The owner-approved structure is `www.geocore.one` **redirecting to the apex**, not resolving alongside it. Two ways to implement, in order of preference:

1. **Add `www.geocore.one` as a second custom domain on the marketing service** and let it 301 to the apex. Preferred: one TLS certificate flow, one place to reason about, and the redirect is a real HTTP 301 that consolidates link equity onto the canonical host.
2. **GoDaddy Forwarding** (`www` → `https://geocore.one`, permanent/301, forward with masking **off**). Acceptable fallback. Masking must be off — a masked forward serves the apex inside a frame, which is invisible to search engines and would waste the redirect entirely.

Either way the marketing app already emits `<link rel="canonical" href="https://geocore.one">`, so the apex is unambiguously the canonical host even before the redirect lands.

Ordering note: add the domain in Railway **first**, then create the DNS
record. Railway issues the TLS certificate by validating the DNS record, so a
record created before the service knows about the hostname simply resolves to
a 404 until you complete the Railway side.

### The apex (`geocore.one`) — decided

Two independent reasons, both of which need your decision before an apex
record makes sense:

1. **Technical (GoDaddy).** GoDaddy's nameservers support neither ALIAS/ANAME
   records nor CNAME flattening at the zone apex. A bare `geocore.one` can
   therefore only be an **A/AAAA record to a literal IP address** (or GoDaddy
   *Forwarding*, which is a redirect, not hosting). If Railway gives you an
   apex A-record IP in its custom-domain dialog, use that — an IP you find
   anywhere else will break silently when it changes.
2. **Product — now resolved.** §5 previously flagged that this repository had no public site to serve at the apex. It does now: `apps/marketing` is a real, indexable GeoCore site with its own Dockerfile and Railway configuration. The apex serves that, never the application.

---

## 2. Records to MODIFY or DELETE (expected conflicts)

| # | Type | Host / Name | Current value (typical) | TTL | Action | Purpose | Notes |
|---|---|---|---|---|---|---|---|
| 3 | A | `@` | GoDaddy parking IP (commonly `Parked` / an `AfternicDNS` address) | 600 | **MODIFY** | Apex now serves the GeoCore marketing site | A parked apex must not be left in place once the brand is live. |
| 4 | CNAME | `www` | GoDaddy default (parked / `_domainconnect` style target) | 600 | **MODIFY or DELETE** | Replaced by the 301 redirect to the apex | Standard GoDaddy default; check yours. If you implement the redirect as a Railway custom domain, this record becomes a CNAME to the marketing service; if you use GoDaddy Forwarding, GoDaddy manages the record itself. |
| 5 | CAA | `@` | *(only if present)* | — | **REVIEW ONLY** | TLS issuance | If a CAA record exists and does not permit `letsencrypt.org`, Railway's certificate issuance for all three hosts fails with no obvious error. If no CAA record exists, nothing to do — that is the common case. |

Records #3 and #4 are the only existing records this document proposes
touching at all, and neither is mail-related.

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
| 1 | CNAME | `app` | Railway **web** target | 600 | ADD | GeoCore application | Check `app` is free |
| 2 | CNAME | `api` | Railway **api** target | 600 | ADD | GeoCore API | Check `api` is free |
| 3 | A | `@` | Railway apex target for **marketing** | 600 | ADD/MODIFY | GeoCore public website | Parking A record likely |
| 4 | — | `www` | 301 → `https://geocore.one` | — | ADD/MODIFY | Canonical consolidation | GoDaddy default `www` CNAME likely |
| 5 | CAA | `@` | *(review only)* | — | NONE | TLS issuance check | Only if a CAA record exists |
| — | MX / SPF / DKIM / DMARC / autodiscover / `MS=` | various | unchanged | — | **NONE** | Microsoft 365 mail | Explicitly untouched |

**Net: 3 additions, 1 redirect, 0 mail changes.**

Apply in this order, so nothing is ever pointed at a service that is not ready:

1. Deploy the three Railway services and set every variable in §7.
2. Add each custom domain in Railway **first** — it issues the TLS certificate by validating DNS, so the record has to exist for a hostname the service already knows about.
3. Records 1 and 2 (`app`, `api`). Verify both serve valid TLS.
4. Record 3 (apex). Verify `https://geocore.one` serves the marketing site.
5. Record 4 (`www` redirect). Verify it 301s to the apex.
6. Re-run the §6 mail block and diff against the saved copy.

## 5. Domain structure (owner-approved)

| Host | Serves | Railway service | Indexable |
|---|---|---|---|
| `geocore.one` | Public GeoCore website | `marketing` (`apps/marketing`) | **Yes** — canonical host |
| `www.geocore.one` | 301 → apex | — | n/a |
| `app.geocore.one` | Authenticated GeoCore platform | `web` (`apps/web`) | **No** — `Disallow: /` |
| `api.geocore.one` | Production API | `api` (FastAPI) | **No** — JSON API, no HTML surface |

The apex concern raised in the previous revision of this document is resolved. `apps/marketing` now exists: a real, statically prerendered, fully indexable GeoCore site with canonical tag, Open Graph metadata, JSON-LD (`Organization` / `WebSite` / `SoftwareApplication`), `robots.txt` and `sitemap.xml`. The apex serves that. **The apex is never redirected to the login page.**

`app.geocore.one` returns `Disallow: /` unconditionally (`apps/web/app/robots.ts`). That is not tidiness — it stops the login page outranking the marketing site for brand queries, and stops token-scoped portal and invite URLs, which are capability tokens rather than login-protected pages, being crawled and archived.

**One build-time trap, guarded by a test.** The marketing site's indexability is baked into the image at build time, not read at runtime. If `APP_ENV=production` were ever dropped from `apps/marketing/Dockerfile`, the production image would ship `noindex, nofollow` and `Disallow: /` — the site would come up, every page would return 200, nothing would error, and geocore.one would simply never appear in search results. `apps/marketing/indexability.test.mjs` asserts that contract in CI.


## 5A. Before / after — the approval table

**Nothing in this table has been applied.** Two columns are marked
`OWNER-SUPPLIED` because they cannot be obtained from the build environment:
the egress proxy denies every public DNS resolver *and* railway.com, so the
current zone could not be read and the Railway targets could not be fetched.
Fill those two in, then approve.

### Before (current live zone) — TO BE CONFIRMED BY OWNER

Run §6 and paste the output here. The "typical" column is what a GoDaddy
domain with live Microsoft 365 mail normally holds — it is a prediction to
check against, **not** an observation of your zone.

| Type | Host | Typical current value | Confirmed? |
|---|---|---|---|
| A | `@` | GoDaddy parking IP (`Parked` / `AfternicDNS`) | ☐ |
| CNAME | `www` | GoDaddy default (`_domainconnect` / parked) | ☐ |
| MX | `@` | `geocore-one.mail.protection.outlook.com` | ☐ |
| TXT | `@` | `v=spf1 include:spf.protection.outlook.com -all` | ☐ |
| TXT | `@` | `MS=msXXXXXXXX` (domain verification) | ☐ |
| TXT | `_dmarc` | `v=DMARC1; p=...` | ☐ |
| CNAME | `selector1._domainkey` | `selector1-geocore-one._domainkey.<tenant>.onmicrosoft.com` | ☐ |
| CNAME | `selector2._domainkey` | `selector2-geocore-one._domainkey.<tenant>.onmicrosoft.com` | ☐ |
| CNAME | `autodiscover` | `autodiscover.outlook.com` | ☐ |
| CAA | `@` | *(usually absent)* | ☐ |
| — | `app`, `api` | *(expected absent)* | ☐ |

### After (proposed)

| # | Type | Host | Value | TTL | Action | Purpose |
|---|---|---|---|---|---|---|
| 1 | CNAME | `app` | `OWNER-SUPPLIED` — Railway **web** target | 600 | **ADD** | GeoCore application |
| 2 | CNAME | `api` | `OWNER-SUPPLIED` — Railway **api** target | 600 | **ADD** | GeoCore API |
| 3 | A | `@` | `OWNER-SUPPLIED` — Railway apex target for **marketing** | 600 | **MODIFY** (replaces parking) | GeoCore public website |
| 4 | — | `www` | 301 → `https://geocore.one` | — | **MODIFY** (replaces GoDaddy default) | Canonical consolidation |
| 5 | MX | `@` | *unchanged* | — | **NONE** | Microsoft 365 mail |
| 6 | TXT | `@` (SPF) | *unchanged* | — | **NONE** | Microsoft 365 mail |
| 7 | TXT | `@` (`MS=`) | *unchanged* | — | **NONE** | Microsoft 365 verification |
| 8 | TXT | `_dmarc` | *unchanged* | — | **NONE** | Microsoft 365 mail |
| 9 | CNAME | `selector1._domainkey` | *unchanged* | — | **NONE** | Microsoft 365 DKIM |
| 10 | CNAME | `selector2._domainkey` | *unchanged* | — | **NONE** | Microsoft 365 DKIM |
| 11 | CNAME | `autodiscover` | *unchanged* | — | **NONE** | Microsoft 365 |
| 12 | CAA | `@` | *review only* | — | **NONE** | Blocks TLS issuance if present and restrictive |

**Net: 2 records added, 2 modified, 0 deleted, 0 mail records touched.**

### Where the Railway targets come from

Add each custom domain in the Railway dashboard **first** — Railway issues the
TLS certificate by validating DNS, so the hostname must already be known to
the service. Railway then displays the exact target for that domain. Copy it
verbatim into the table above. Do not transcribe a target from another
domain's setup or infer one; a wrong target fails certificate issuance with
no obvious error.

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

| Service | Variable | Value | Enforced by |
|---|---|---|---|
| **api** | `APP_ENV` | `production` | `app/core/config.py` |
| **api** | `CORS_ALLOWED_ORIGINS` | `https://app.geocore.one` — HTTPS, scheme+host only, no `*`, no trailing path. The marketing site makes no API calls, so the apex is deliberately **not** listed. | `app/core/config.py` |
| **api** | `FRONTEND_BASE_URL` | `https://app.geocore.one` — where Stripe Checkout returns to | `app/billing/` |
| **api** | `SEED_DATA_ENABLED` | `false` (production seeding is forbidden) | `app/core/config.py` |
| **api** | `SEED_ADMIN_EMAIL` | A real address. The development default `owner@geocore.local` **and** its pre-rebrand predecessor `owner@simo-os.local` are both rejected in production. | `app/core/config.py` |
| **web** | `APP_ENV` | `production` | `apps/web/lib/runtime-config.ts` |
| **web** | `NEXT_PUBLIC_API_URL` | `https://api.geocore.one` — must be an absolute HTTPS origin | `apps/web/lib/runtime-config.ts` |
| **marketing** | `APP_ENV` (build arg) | `production` — **already set in `apps/marketing/Dockerfile`.** Without it the image ships `noindex`. | `apps/marketing/indexability.test.mjs` |
| **marketing** | `NEXT_PUBLIC_SITE_URL` (build arg) | `https://geocore.one` — must match exactly or the site self-excludes from the index | `apps/marketing/lib/site.ts` |
| **marketing** | `NEXT_PUBLIC_APP_URL` (build arg) | `https://app.geocore.one` — where the site's sign-in links point | `apps/marketing/lib/site.ts` |

Set these **before** repointing DNS. The web app throws on boot if
`NEXT_PUBLIC_API_URL` is missing under `APP_ENV=production`, and the API
rejects a non-HTTPS or wildcard CORS origin outright — so a misconfigured
service fails its health check and Railway keeps the previous revision
serving, rather than going live broken.

The three `marketing` variables are **build arguments, not runtime
variables.** Changing them requires a rebuild, not a restart. On Railway,
set them as service variables and trigger a redeploy.

| **web** | `NEXT_PUBLIC_SALES_EMAIL` (build arg) | **Optional.** The Enterprise "Contact sales" address. Set it *only* once you have confirmed the mailbox exists. Left unset, the CTA routes to signup instead — no broken `mailto:` ships either way. |

### One item that needs you, not a deploy

The Enterprise CTA on `apps/web/app/pricing/page.tsx` no longer hardcodes an
address. It renders a `mailto:` only when `NEXT_PUBLIC_SALES_EMAIL` is set,
and otherwise routes to signup.

This was changed because the mailbox could not be verified from the build
environment, and an unverified `mailto:` on a public pricing page is a silent
failure: an enterprise enquiry bounces, nobody sees an error, and the lead is
simply lost. (The pre-rebrand page linked `sales@simo-os.com` — a domain the
business does not own — so that failure had already shipped once.)

**Action:** confirm or create `sales@geocore.one` in Microsoft 365, then set
`NEXT_PUBLIC_SALES_EMAIL=sales@geocore.one` on the web service and redeploy.
It is a build argument, so a restart will not pick it up. No DNS change is
involved; this is a mailbox, not a record.

---

## 8. Rollback

| Change | Rollback | Recovery time |
|---|---|---|
| Records 1, 2 (`app`, `api`) | Delete the record | One TTL (600s) |
| Record 3 (apex A) | Restore the value captured in §6 | One TTL |
| Record 4 (`www` redirect) | Restore the value captured in §6 | One TTL |
| Mail records | **N/A — not changed** | — |

Keep TTL at 600 through the cutover; raise it to 3600 once the records have
been stable for a week.

---

## 9. Sign-off

Applied by the domain owner only. Nothing in this document is executed
automatically, and no credential for the registrar is held by, or should be
given to, this repository or any assistant working in it.

- [ ] §6 pre-flight run; live zone captured; **mail block output saved to a file**
- [ ] `sales@geocore.one` mailbox or alias confirmed to exist (§7)
- [ ] §7 variables set on all three Railway services; marketing redeployed so its build args take effect
- [ ] Custom domains added in Railway first; exact targets copied verbatim into records 1–3
- [ ] Records applied in the §4 order
- [ ] `https://geocore.one` serves the marketing site (not a login redirect)
- [ ] `https://geocore.one/robots.txt` says `Allow: /` and names the sitemap
- [ ] `https://app.geocore.one/robots.txt` says `Disallow: /`
- [ ] `https://www.geocore.one` 301s to the apex (not a masked frame)
- [ ] `app.` and `api.` serve valid TLS
- [ ] §6 mail block re-run and **diffed against the saved copy — no change**
- [ ] Microsoft 365 mail send/receive spot-checked
