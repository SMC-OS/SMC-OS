# geocore.one — DNS change sheet (for owner review)

**Status:** PROPOSAL, verified against live infrastructure. Nothing has been
applied to the registrar. No GoDaddy credential has been requested, stored,
or used, and none is needed to apply this sheet — the owner applies it
directly in the GoDaddy DNS panel.

**Registrar / DNS host:** GoDaddy (confirmed live: nameservers
`ns43.domaincontrol.com` / `dns.jomax.net`)
**Mail:** Microsoft 365, GoDaddy-brokered ("GoDaddy 365"), already live —
outside this repository
**Target hosting:** Railway, three services — `app` (`apps/web`), `api`
(FastAPI), `marketing` (`apps/marketing`)

This revision (Sprint 035) replaces the previous one entirely. Two things
changed since the last version, both because this session has live Railway
and live DNS access that an earlier build environment did not:

1. **The apex cannot be a direct Railway target.** Confirmed by actually
   attaching `geocore.one` as a custom domain in Railway: it always returns
   a **CNAME** target, never a literal IP, for any custom domain including
   the apex. GoDaddy does not support CNAME/ALIAS/ANAME at a zone apex (a
   CNAME cannot coexist with the NS/SOA records every zone apex must have).
   So the plan in the previous revision — "if Railway gives an apex A
   record, use it" — cannot be satisfied on this registrar. See §2.
2. **The live zone has been read, and the mail block captured for real**
   (§3). Every record below is what is actually on `geocore.one` today, not
   a predicted "typical GoDaddy zone."

## 1. Records to ADD or MODIFY

| # | Type | Host | Current value | New value | TTL | Action | Purpose |
|---|---|---|---|---|---|---|---|
| 1 | CNAME | `app` | *(none — confirmed empty)* | `0dmh8di9.up.railway.app` | 600 | **ADD** | `app.geocore.one` → GeoCore application |
| 2 | CNAME | `api` | *(none — confirmed empty)* | `a2d9n99k.up.railway.app` | 600 | **ADD** | `api.geocore.one` → GeoCore API |
| 3 | CNAME | `www` | `geocore.one` (self-referencing GoDaddy default) | `g2rtd03f.up.railway.app` | 600 | **MODIFY** | `www.geocore.one` → GeoCore marketing site (this becomes the real, canonical, indexed host — see §2) |
| 4 | A | `@` | `3.33.130.190`, `15.197.148.33` (GoDaddy parking) | *(GoDaddy Domain Forwarding, not a DNS record — see §2)* | — | **REPLACE with Forwarding** | Apex redirects to `https://www.geocore.one` |
| 5 | CAA | `@` | *(confirmed absent)* | — | — | **NONE** | Nothing to do — absence is the good case |

Targets 1–3 are exact, live Railway values (captured directly, not
transcribed or guessed). **Do not reuse them for a different domain** if
this sheet is ever adapted — regenerate via Railway for the actual domain
in question.

Add each custom domain in Railway **before** creating its DNS record —
Railway validates DNS to issue the TLS certificate, so the record needs a
service that already expects that hostname. All three (`app`, `api`,
`www.geocore.one`) are already added as of this sheet; only the DNS side
is pending.

## 2. The apex — why `www` hosts the site, not `geocore.one` directly

Two constraints, confirmed live rather than assumed:

- **GoDaddy** cannot point the bare apex at a CNAME (standard DNS rule, not
  a GoDaddy limitation specifically — every zone apex needs NS/SOA records,
  which cannot coexist with a CNAME at the same name).
- **Railway** only ever hands out a CNAME target for a custom domain — this
  session attached `geocore.one` directly and confirmed it, no A-record
  option was offered.

Those two facts are incompatible for hosting real content directly at the
bare apex on this registrar. The resolution: `www.geocore.one` is a normal
subdomain, so it takes the Railway CNAME with no restriction, and becomes
the actual, indexed, canonical host. The apex uses **GoDaddy Domain
Forwarding** — a 301 redirect GoDaddy serves itself, not a Railway target —
to send `https://geocore.one` → `https://www.geocore.one`. This is a common,
fully supported pattern (bare-domain-redirects-to-www) and needs no
registrar migration.

**Application code already reflects this** (`apps/marketing/lib/site.ts`):
the canonical URL, `IS_INDEXABLE` check, sitemap, and Open Graph tags all
key off `https://www.geocore.one`, verified by
`apps/marketing/indexability.test.mjs`.

**The alternative**, for the record: migrating `geocore.one`'s nameservers
from GoDaddy to a provider that supports apex ALIAS/CNAME-flattening (e.g.
Cloudflare, kept free, with GoDaddy remaining the registrar) would allow the
bare apex to host directly. That is a bigger, separate decision — a
nameserver change is more consequential than the record changes in this
sheet — and is not required for anything in this sprint to work. Flagging
it here as an option, not a recommendation either way; the `www`-hosts /
apex-forwards approach above needs no such migration and is what's proposed.

### GoDaddy Forwarding setup (apex)

In the GoDaddy DNS panel for `geocore.one`: **Forwarding → Domain →
Add** → forward to `https://www.geocore.one`, type **Permanent (301)**,
masking **off**. Masking must be off — a masked forward serves the target
inside a frame, invisible to search engines, defeating the redirect.

## 3. Records that must NOT be changed — Microsoft 365 mail (GoDaddy-brokered)

**Captured live, this session** (`docs/DNS_GEOCORE_ONE.md` §6 pre-flight,
via DNS-over-HTTPS — the raw values, redacted of nothing, are what's below).
Confirms this is a **GoDaddy-managed Microsoft 365** subscription
specifically (not a self-managed tenant pointed straight at Microsoft): the
SPF include and DMARC report address are GoDaddy's own domains, not
Microsoft's directly. That is a normal GoDaddy product, not a
misconfiguration — the MX and DKIM targets are still genuinely Microsoft's.

| Type | Host | Live value | Action |
|---|---|---|---|
| MX | `@` | `0 geocore-one.mail.protection.outlook.com.` | **DO NOT TOUCH** |
| TXT | `@` (SPF) | `v=spf1 include:secureserver.net -all` | **DO NOT TOUCH** |
| TXT | `@` (verification) | `NETORGFT21096048.onmicrosoft.com` | **DO NOT TOUCH** |
| TXT | `_dmarc` | `v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;` | **DO NOT TOUCH** |
| CNAME | `selector1._domainkey` | `selector1-geocore-one._domainkey.netorgft21096048.w-v1.dkim.mail.microsoft.` | **DO NOT TOUCH** |
| CNAME | `selector2._domainkey` | `selector2-geocore-one._domainkey.netorgft21096048.w-v1.dkim.mail.microsoft.` | **DO NOT TOUCH** |
| CNAME | `autodiscover` | `autodiscover.outlook.com.` | **DO NOT TOUCH** |

None of these share a name with any record in §1 — `app`, `api`, `www`, and
the apex forwarding target are disjoint from `@`, `_dmarc`, `selector1._domainkey`,
`selector2._domainkey`, and `autodiscover`. There is no name collision for
the cutover to get wrong.

**The SPF trap still applies.** A zone holds only one SPF TXT record. If
GeoCore ever sends transactional email itself (it does not today — no SMTP
client, no email-provider integration anywhere in `app/`), adding a second
SPF record breaks delivery outright; the existing one would need modifying
in place to add the new `include:`. Out of scope here.

## 4. Complete record table (single view, apply in this order)

| # | Type | Host | Value | TTL | Action |
|---|---|---|---|---|---|
| 1 | CNAME | `app` | `0dmh8di9.up.railway.app` | 600 | ADD |
| 2 | CNAME | `api` | `a2d9n99k.up.railway.app` | 600 | ADD |
| 3 | CNAME | `www` | `g2rtd03f.up.railway.app` | 600 | MODIFY (was self-referencing `geocore.one`) |
| 4 | Forwarding | `@` (apex) | 301 → `https://www.geocore.one`, masking off | — | REPLACE existing A/parking with Forwarding |
| — | MX / SPF / verification / DMARC / DKIM×2 / autodiscover | various | unchanged (§3) | — | **NONE** |

**Net: 2 additions, 1 CNAME modification, 1 A-record replaced by
Forwarding, 0 mail records touched.**

## 5. Domain structure (current, corrected)

| Host | Serves | Railway service | Indexable |
|---|---|---|---|
| `www.geocore.one` | Public GeoCore website | `marketing` (`simo-marketing-production`) | **Yes** — canonical host |
| `geocore.one` | 301 → `www` (GoDaddy Forwarding) | — | n/a |
| `app.geocore.one` | Authenticated GeoCore platform | `web` (`simo-web-production`) | **No** — `Disallow: /` |
| `api.geocore.one` | Production API | `api` (`simo-api-production`) | **No** — JSON API |

## 6. Pre-flight — already run, this session (DNS-over-HTTPS, live)

Standard `dig`/public-resolver access was blocked from this environment too
(confirmed again), but DNS-over-HTTPS to `cloudflare-dns.com` was not, and
returned real, authoritative answers — cross-checked against the live MX
above, which matches Microsoft 365 exactly. This is how §3 and the apex
finding in §2 were obtained; not a repeatable owner step, just the method
used to produce this sheet's numbers.

## 7. Application configuration — status

Per `app/core/config.py` / `apps/web/lib/runtime-config.ts` / this sprint's
Railway checks:

| Service | Variable | Current value | Target value | When to flip |
|---|---|---|---|---|
| **api** | `CORS_ALLOWED_ORIGINS` | `https://simo-web-production-production.up.railway.app,https://app.geocore.one` | *(unchanged — already includes the target)* | Already correct |
| **web** | `NEXT_PUBLIC_API_URL` | `https://simo-api-production-production.up.railway.app` | `https://api.geocore.one` | **After** `api.geocore.one` resolves and its TLS certificate is issued — flipping before that breaks every browser call |
| **marketing** | `NEXT_PUBLIC_SITE_URL` (build arg) | `https://www.geocore.one` | *(already set to the target — deployed this sprint)* | Already correct |
| **marketing** | `NEXT_PUBLIC_APP_URL` (build arg) | `https://app.geocore.one` | *(already set to the target)* | Already correct |
| **marketing** | `APP_ENV` (build arg) | `production` | *(already set)* | Already correct |

Only `NEXT_PUBLIC_API_URL` on the `web` service still needs flipping, and
only after DNS + TLS for `api.geocore.one` are live — flipping it earlier
would 100% break the application for every user immediately (DNS for the
new host wouldn't resolve yet). This is the one step that happens **after**
the owner applies §4, not before.

## 8. Rollback

| Change | Rollback | Recovery time |
|---|---|---|
| Records 1, 2 (`app`, `api`) | Delete the record | One TTL (600s) |
| Record 3 (`www`) | Point back to `geocore.one` (its prior self-reference) | One TTL |
| Apex Forwarding | Remove the forward, restore the A record to `3.33.130.190` / `15.197.148.33` | Immediate (GoDaddy-side) |
| `NEXT_PUBLIC_API_URL` flip | Revert to the `.up.railway.app` origin, redeploy `web` | One deploy (~1 min) |
| Mail records | **N/A — not changed** | — |

Keep TTL at 600 through the cutover; raise it to 3600 once stable for a week.

## 9. Sign-off

Applied by the domain owner only, in the GoDaddy DNS panel. No credential
for GoDaddy or Railway beyond what this session already had is needed.

- [ ] `app` CNAME added (`0dmh8di9.up.railway.app`)
- [ ] `api` CNAME added (`a2d9n99k.up.railway.app`)
- [ ] `www` CNAME modified (`g2rtd03f.up.railway.app`)
- [ ] Apex Forwarding configured (301, masking off, → `https://www.geocore.one`)
- [ ] `https://www.geocore.one` serves the marketing site
- [ ] `https://geocore.one` redirects (301) to `https://www.geocore.one`
- [ ] `https://www.geocore.one/robots.txt` says `Allow` and names the sitemap
- [ ] `https://app.geocore.one/robots.txt` says `Disallow: /`
- [ ] `app.` and `api.` serve valid TLS (Railway issues automatically once DNS resolves)
- [ ] Mail block (§3) re-queried and diffed against this sheet — no change
- [ ] Microsoft 365 mail send/receive spot-checked
- [ ] **Only after all of the above:** `NEXT_PUBLIC_API_URL=https://api.geocore.one` set on `web`, service redeployed
