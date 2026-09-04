# Sprint 034 — Tenant Company Identity, Brand Separation & Production Domain

Continuation of Sprint 033 (`v1.2.0`, merged `cbc17c2`, deployed and verified). Three workstreams; A is delivered, B and C are owner-gated by design and carry no code in this sprint.

- **A — Tenant company identity** (delivered): remove the hardcoded company letterhead from all customer-facing document rendering and make business identity tenant-configurable.
- **Phase 2 — Production rebrand** (delivered): rename the platform SIMO OS → GeoCore across every user-visible surface, and build the public marketing site the apex needs.
- **B — GeoCore brand assets** (owner-gated): brand-mark integration, blocked pending the approved asset files.
- **C — geocore.one production DNS** (owner-gated): change sheet prepared for review; no registrar change made.

## 1. Discovery

### 1.1 Workstream A — the defect

`app/quotes/pdf.py` hardcoded a single letterhead into every PDF the platform produced:

```python
story.append(Paragraph("SIMO MARBLE &amp; CONSTRUCTION LTD", styles["Heading1"]))
story.append(Paragraph("Unit 4, Riverside Trade Park, London", styles["Normal"]))
```

Both invoice endpoints — `GET /api/v1/quotes/{id}/invoice` (authenticated) and `GET /api/v1/portal-links/token/{token}/invoice/{id}` (public, customer-facing) — routed through it, so **every tenant's invoice carried one specific company's trading identity**, and a customer downloading their own invoice over a portal link received it too.

This is a cross-tenant leak in the one artefact that actually reaches a customer. It is worth being precise about why it survived Sprint 012's isolation sweep: that sprint audited *queries* — every business-data read is correctly filtered by `tenant_id`, and still is. The leak here was never in a query. It was a literal string in a render path, which no amount of query auditing would surface.

Two related instances of the same confusion were found in the same sweep:

- `apps/web/app/layout.tsx` described the platform as "AI Operating System for Simo Marble & Construction Ltd" — a tenant's identity in global chrome every tenant sees.
- `tenants` had no company-identity columns at all: `name` (the workspace label staff see) was the only company field in the schema, and it is not a legal or trading name.

### 1.2 The distinction this sprint enforces

| Concept | What it is | Where it may appear |
|---|---|---|
| **Platform brand** (GeoCore; "SIMO OS" in the current build) | The product a business subscribes to | Application chrome, marketing, billing |
| **Tenant business identity** (e.g. Simo Marble & Construction Ltd) | The company a customer is buying from | That tenant's own quotes, invoices, portal |

Simo Marble & Construction Ltd is a real operating company and **one tenant** of this platform. It is not the platform, and it is not a default. Equally, the platform brand must never render as a tenant's trading identity on a customer document — replacing one hardcoded company with another would be the same bug.

### 1.3 Workstream C — deployment shape

`deploy/railway/` defines two services (web, api). Two findings materially shaped the DNS proposal:

1. **The application sends no email of any kind.** No SMTP client, no email provider integration, no `send_email` anywhere in the backend; `app/notifications/` is in-app only. The production cutover therefore has *zero* overlap with the live Microsoft 365 configuration — no MX, SPF, DKIM, DMARC, autodiscover, or verification record needs to change.
2. **There is no public marketing site in this repository.** `apps/web/app/page.tsx` is the authenticated dashboard and redirects anonymous visitors to `/login`. The preferred `geocore.one = public website` cannot be served from this repo today.

## 2. Design

### 2.1 Schema

`tenants` gains 14 nullable columns: `legal_name`, `trading_name`, `address_line1`, `address_line2`, `city`, `postcode`, `country`, `contact_email`, `contact_phone`, `website`, `company_number`, `vat_number`, `logo_url`, `document_footer`.

All nullable. A tenant that has configured nothing falls back to its own workspace `name` — never to another tenant's details, and never to a global default.

### 2.2 `app/tenants/identity.py`

One module answers "whose business details go on this document?", and the answer is always the tenant that owns the document. It enforces three rules:

1. **Never the platform's brand.** No platform name is a candidate for a trading identity.
2. **Never another tenant's details.** The fallback chain is `trading_name → legal_name → workspace name`, and terminates there by design.
3. **Never a fabricated statutory number.** `company_number`/`vat_number` render only when actually supplied. An absent VAT number means the line is omitted, not filled with a placeholder.

`resolve()` reads attributes only and takes no `Session`, so the PDF layer never touches the database.

### 2.3 Rendering

`app/quotes/pdf.py` now renders whatever `CompanyIdentity` its caller passes and holds no company name, address, or registration number of its own. A caller passing none produces a document with **no letterhead**, which is the correct failure mode: an unattributed invoice is recoverable; one carrying the wrong company's name is not.

Tenant-supplied text is escaped — ReportLab paragraphs are mini-HTML, and "Simo Marble & Construction Ltd" is an ordinary company name that would otherwise abort the render.

The portal endpoint resolves the tenant from `quote.tenant_id`, not from caller context, because there is no authenticated user on a portal route.

### 2.4 API

`GET`/`PATCH /api/v1/tenants/me/profile`. Read is any authenticated member; write is Owner-only (statutory details on customer-facing invoices belong with billing and team management, not general settings).

Both are hard-scoped to the caller's own tenant — there is no `tenant_id` parameter to tamper with, so no cross-tenant write is expressible through the API at all. This is ADR-029's posture enforced by construction rather than by a check.

Declared before `/{tenant_id}`: FastAPI matches in declaration order, and `me` would otherwise be parsed as a UUID and 422 before reaching the handler.

`PATCH` writes only fields actually present in the request, so a client that knows about fewer fields than the server cannot blank the rest. An empty string clears a field; an omitted one leaves it untouched.

### 2.5 Migration and the existing SMC tenant

The delicate part. Every existing invoice already renders the Simo letterhead, so leaving the real operating tenant blank would silently change what its customers see — the opposite of "preserve historical document behaviour".

Two conservative backfill rules:

1. **Exactly one tenant in the database** → backfill it. With one tenant, that tenant *is* the operating business whose identity those PDFs have always shown, and there is no second tenant that could wrongly inherit it. This rule matters because the production tenant may well be named "Default Workspace" (`app/auth/seed.py` creates it under that name), so a name match alone would miss it.
2. **Otherwise** → backfill only tenants whose name/slug identifies them as Simo Marble & Construction. A generically-named co-tenant is left alone rather than guessed at.

Only the two facts the letterhead already printed are backfilled — legal name and address — character-for-character, so a backfilled tenant's PDF renders exactly what it rendered before.

**`company_number` and `vat_number` are deliberately left NULL.** No accurate value for either exists anywhere in this repository. A fabricated company registration or VAT number on a UK invoice is a legal defect, not a cosmetic one, so the invoice omits those lines until the owner supplies real ones.

### 2.6 Owner path to the real details

- **Settings → Company identity** (Owner-only) is the normal route.
- `scripts/production/set_tenant_identity.py` covers the one case the UI cannot: configuring the operating tenant immediately after deploy, before anyone has logged in to correct it. Dry-run by default, exact-identifier match only (uuid or exact slug — no wildcard or prefix scan), idempotent, partial, and it never prints `DATABASE_URL` or any credential. Matches the constraints `scripts/production/cleanup_launch_qa.py` established in Sprint 031.

## 3. Verification

### Tests

**708 backend passed, 3 skipped** (was 685 + 4 from Sprint 033's baseline of 689 at branch point). **100 frontend passed** (was 94). Frontend `tsc --noEmit` and `eslint` both clean.

New coverage — `tests/test_tenant_identity.py` (18 tests) and one addition to `tests/test_portal.py`:

- The resolver's fallback chain, address joining, whitespace handling, and the rule that a missing statutory number produces no line.
- **PDF assertions read the rendered text back out of the generated bytes.** ReportLab writes content streams ASCII85-then-Flate, so visible text is not present in the raw bytes — a naive `b"Acme" in pdf` check would pass vacuously against *any* document, including a wrong one. Decoding both layers is what makes "the right name is on the page a customer opens" an actual assertion rather than "the right dict reached the generator".
- The original bug as an explicit test: a second tenant creates a quote and downloads its invoice; the PDF must contain that tenant's own identity and must not contain `SIMO MARBLE` or `Riverside Trade Park`.
- The same assertion for the portal (customer-facing, unauthenticated) route.
- `tests/test_rbac_matrix.py` gains both new routes, so the Owner-only gate on the write is enforced by the sweep rather than by inspection.

### Migration

Verified against scratch databases, both branches:

| Scenario | Result |
|---|---|
| Single tenant named "Default Workspace" | Backfilled with the legacy legal name and address; `company_number`/`vat_number` left NULL |
| Three tenants (Simo + "Northern Granite Ltd" + "Default Workspace") | Only the Simo row backfilled; the other two untouched |
| `alembic downgrade -1` | All 14 columns dropped cleanly; re-upgrade succeeds |

### Ops script

Dry-run, `--confirm`, and idempotent re-run all exercised against a live database.

## 3A. Phase 2 — production rebrand SIMO OS → GeoCore

Full rationale in ADR-037 and ADR-038.

### 3A.1 What was renamed

Application chrome (sidebar, page title/metadata), dashboard/login/signup/pricing copy, the API-unreachable status message, and subscription plan names (`GeoCore Pro`, `GeoCore Business`, in both `app/billing/router.py` and the Settings display map). Living documentation and the README — which was still unmodified Turborepo starter boilerplate — were rewritten.

Historical sprint records in `docs/SPRINTS/` were **not** rewritten. They are an execution record of what happened, and Sprint 018 genuinely did ship a product called SIMO OS. Two other pre-rebrand strings are also preserved deliberately: the v1.0.2 incident entry in `docs/PRODUCTION_RUNBOOK.md` quotes the literal error message users saw at the time, and `docs/STAGING_RUNBOOK.md` names a real Google Drive folder that still has that name.

### 3A.2 The part that could have caused an outage

Three `localStorage` keys already exist in real browsers, and one of them holds the JWT.

A naive rename of `simo-os-token` would have signed out every logged-in user the instant the rebrand deployed. From the outside that is indistinguishable from a broken authentication system, and it would have arrived at exactly the moment the brand was being introduced.

All three keys are therefore read through `readMigratedValue()` (`apps/web/lib/storage-keys.ts`): prefer the new key, fall back to the legacy one exactly once, carry the value forward, drop the old key. Three details that are easy to miss and each have their own test:

- `clearToken()` clears **both** keys. Otherwise signing out would leave a valid JWT under the old name for the very next `getToken()` to migrate straight back in — a sign-out that doesn't.
- The pre-hydration theme script in `app/layout.tsx` reads both keys. It runs before React, so without the fallback a returning dark-mode user would flash light on their first post-deploy load.
- Every accessor is wrapped in `try/catch`. `localStorage` itself throws in Safari private mode and under "block all cookies"; a throwing read during module init would take the whole app down rather than degrade to a signed-out state.

### 3A.3 What was deliberately not renamed

| Identifier | Why |
|---|---|
| `/var/lib/simo-os/uploads` | The production persistent-volume mount. Renaming orphans every uploaded client-portal document. |
| Logger name `simo_os` | Silently breaks any log-based alerting keyed to it. Invisible to customers, live hazard to change. |
| Database name `simo_os`, tables, columns | A downtime migration for zero customer-visible effect. |

Recorded in ADR-037 and in the README so a future contributor finding `simo-os` in these places knows it is a decision.

One safety guard was **widened** rather than moved: the production config check now rejects both the new development seed default (`owner@geocore.local`) and its predecessor (`owner@simo-os.local`). A deployment carrying the old value through the rename must not start passing a safety check merely because a constant changed.

## 3B. Phase 2 — the public site (`apps/marketing`)

`geocore.one` now has something real to serve. `apps/marketing` is a separate Next.js application, statically prerendered, with canonical tag, Open Graph metadata, JSON-LD (`Organization` / `WebSite` / `SoftwareApplication`), `robots.txt`, `sitemap.xml`, the security headers `apps/web` already sends, and the approved GeoCore palette.

It is an interim holding page in content only — it states what GeoCore is, who it is for, and where to sign in — but it is a fully indexable page from day one, not a "coming soon" splash. The apex is the strongest SEO asset the brand will ever own; there is no reason for it to sit idle while the full site is written.

**No logo mark is used.** The approved GeoCore assets have not been supplied, and neither inventing a mark nor reusing the application's placeholder `S` would be right on the brand's own front door. A text wordmark carries it until the real assets arrive.

Indexability is asymmetric and deliberate: `apps/marketing` invites crawling only when `APP_ENV=production` **and** its canonical origin is `https://geocore.one`, so a staging deploy of the same image excludes itself. `apps/web` returns `Disallow: /` unconditionally — the login page must not outrank the marketing site for brand queries, and token-scoped portal/invite URLs are capability tokens rather than login-protected pages, so they must not be crawled and archived.

**One trap, caught by a test.** Next prerenders `robots.txt`, the robots meta tag and the canonical URL at *build* time. If `APP_ENV=production` were ever dropped from `apps/marketing/Dockerfile`, the production image would ship `noindex, nofollow` and `Disallow: /`: the site comes up, every page returns 200, nothing errors, and geocore.one never appears in search results. This was found while smoke-testing the built container — the first local build emitted exactly that — and is now asserted in CI by `apps/marketing/indexability.test.mjs`.

A pre-existing CI gap was also closed: `apps/web` had no `check-types` script, so the workspace-wide `pnpm check-types` in CI silently skipped the main application. It now has one.

## 4. Workstream B — GeoCore brand assets (owner-gated)

The approved brand board defines the mark, wordmark, light/dark variants, and palette (`#0F2E23`, `#355E4B`, `#A7C0A0`, `#DCC6A0`, `#F8F6EE`). **No logo change was made.** The current hardcoded `S` mark (`apps/web/components/layout/Sidebar.tsx`) stays until the approved asset files are supplied, per the owner boundary. Integration points, when the asset arrives:

| Context | Asset |
|---|---|
| `apps/web/app/favicon.ico`, app icon | Standalone `G` mark |
| Sidebar / header (`Sidebar.tsx`) | Horizontal GeoCore logo |
| Light / dark surfaces | Respective variants |

The GeoCore name is preserved exactly and the logo is not to be redesigned.

The platform rename itself is done (§3A) — it was a distinct decision from integrating the mark, and the owner confirmed it separately. What remains gated here is only the artwork.

## 5. Workstream C — geocore.one DNS (owner-gated)

Full proposal in **`docs/DNS_GEOCORE_ONE.md`**. Nothing applied; no registrar credential requested, stored, or used.

Summary: **2 unambiguous additions, 1 `www` decision, 1 apex decision, 0 mail changes.** `app.geocore.one` and `api.geocore.one` are straightforward CNAMEs to the two Railway services. Every Microsoft 365 record is explicitly out of scope and untouched — which is not a compromise but a consequence of §1.3's finding that the application sends no email.

The apex is the one deviation from the preferred structure, and the reason is technical: there is no public site to serve there, so pointing `geocore.one` at the web service would resolve the root domain to a login redirect — the worst available outcome for the domain's search authority. The recommendation is a marketing site (or an interim holding page) at the apex, and to hold the apex records until then. Nothing about the application cutover depends on that decision.

## 6. Known limitations

1. **The production tenant's statutory details are not set.** The migration backfills only the legal name and address that were already being printed. `company_number` and `vat_number` are NULL and the invoice omits those lines until the owner enters real values. This is deliberate — see §2.5.
2. **The live geocore.one zone was not read.** Outbound DNS resolvers are blocked from the build environment, so every conflict in the change sheet is a near-universal *class* of GoDaddy conflict, not an observed record. §6 of the change sheet is the pre-flight that turns those into verified facts.
3. **`logo_url` is stored and returned but not yet rendered on the PDF.** The column and the Settings field exist; wiring an image into the ReportLab letterhead (with fetch/size/format validation for a tenant-supplied URL) is deliberately separate — an unvalidated remote image in a server-side render path is its own security surface.
4. **No tenant-branded styling beyond the letterhead.** Colours, fonts, and layout of the PDF remain uniform across tenants.
5. **Platform rename not performed** — see §4.

## 7. Recommended next

1. Owner enters the real Simo Marble & Construction Ltd company number, VAT number, and registered address via Settings → Company identity immediately after deploy.
2. Owner reviews `docs/DNS_GEOCORE_ONE.md` and makes the §5 apex decision.
3. Marketing site at the apex — the highest-leverage item on this list for organic growth, and the blocker for the preferred domain structure.
4. `robots`/`noindex` on `app.` and `api.`, plus canonical and sitemap on whichever host serves the apex.
5. Tenant logo rendering on the PDF (limitation 3), with validation.

## Final status

**Workstream A: COMPLETE and verified.** Workstreams B and C: prepared, owner-gated, no code or configuration changed.
