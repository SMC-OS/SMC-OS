# Stone quote corrections — 22 October 2026

This candidate follows deployed merge 7c10189. It has not yet been deployed.

## Behaviour

- Splashback inclusion records a specification in the quote notes; it does not require dimensions or create an invented measured/charged line. Separate explicitly added splashback line items still use their own measurements. Measured upstands remain independent.
- The stone editor requires customer name, address and postcode. Email and phone are optional. Linked customer contact data is displayed from the customer record; editing the site address snapshots it on this quote rather than overwriting that record.
- Any typed stone name may save an authenticated draft. Missing prices produce null totals and a clear pricing-pending state, not a guessed price, £0 or a partial total. Explicit user slab prices and existing workspace prices still calculate normally. The legacy API remains strict unless `allow_unpriced` is explicitly enabled, with required site details.
- Adding prices in the same editor completes that pending draft in place. Replacement is tenant scoped, restricted to unpriced stone drafts, and replaces header/items in one database transaction. Priced/sent/general quotes cannot be overwritten through this path.
- Sending, marking sent and approving an unpriced draft are refused by the backend. Direct PDF downloads label it as a draft specification and show pricing pending.
- Material browsing supports company/supplier filtering, material family filtering and successive pages, with the company shown on each result. Y&S is provenance only, never a selectable company.

## Catalogue scope and provenance

`app/catalogue/supplier_references.json` contains 570 factual reference entries, with a source URL per entry. They are names/company relationships/material categories, not licensed photographs, marketing text, live stock, guaranteed thicknesses, slab dimensions or prices. The importer preserves existing rows/IDs, overrides and variant data. It creates no variants or prices. The original 38-material seed remains independently available.

| Company/reference grouping | Entries |
| --- | ---: |
| Classic Quartz Stone | 138 |
| Marble City | 123 |
| Cosentino (Silestone/Dekton) | 120 |
| Orient Quartz Stone | 29 |
| NobleStone | 18 |
| COMPAC | 11 |
| Cimstone, Radianz, Caesarstone, Cambria, Technistone, Lunastone, Arenastone | 10 each |
| Stone World | 4 |
| Natural stones with no verified supplier attribution | 57 |

The Y&S public quote form supplies brand and colour relationships; names from its misspelled Campria label are grouped under Cambria. Manufacturer collection pages, NobleStone's public sitemap/product pages, all 11 Marble City material pages, Classic Quartz range pages and Orient's collection supply the additional names. Onyx Ice from NobleStone is correctly quartz, not natural onyx. Dekton is sintered stone. Natural onyx has its own category.

Coverage limitations: this is a dated reference snapshot, not an exhaustive inventory or a supplier partnership claim. Stone World's external live inventory did not expose a usable public product list, so only its four named homepage references are included and left broadly classified as natural stone. Several NobleStone pages and dynamic/load-more collections did not yield a complete public dataset. No missing product names or availability have been fabricated. Generic natural-stone entries have no invented supplier. Further verified imports can extend the same pipeline.

## Release order

No schema migration is required: quote address fields, nullable totals and supplier catalogue tables already exist.

1. Run normal database-backed CI, frontend checks and browser journeys against this exact candidate.
2. Deploy the API first. Confirm `/health` and authenticated draft/save/reprice boundaries.
3. In the target API environment, preview the reference import:
   `python -m app.catalogue.import_supplier_references --dry-run`
4. Publish reference data explicitly (production requires this flag):
   `python -m app.catalogue.import_supplier_references --confirm-production`
5. Verify publication: `python -m app.catalogue.import_supplier_references --check` must report zero missing materials. The import is atomic and idempotent; it is deliberately not an application-startup side effect.
6. Deploy web, then verify mobile address validation, Carrara/company browsing, arbitrary-name draft save, pricing the same draft, splashback notes and drawing round trip. No test email/customer communication is sent.

Deployment and catalogue import must both be verified before calling the change live. A web-only deployment is insufficient because pending-price requests require this API candidate.
