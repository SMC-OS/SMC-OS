# Stone quote builder: reference implementation and repair

Reference: https://yandsmarble.co.uk/online-quote/#f1p1

The owner rejected the decorative layout picker and approved replacing the
stone quote experience using this reference. GeoCore branding is retained;
this is not a pixel-identical copy of the third-party site.

## Implemented experience

- Four guided sections: material/customer, layout, design details, review.
- Eight reference layout combinations, plus the existing peninsula/custom path.
- Original large vector plans with individually labelled A/B/C/D pieces and
  independent dimensions, preserved through navigation and layout changes.
- Sink mounting, hob cut-outs and tap-hole specifications.
- Measured upstands and splashbacks generate their own priced stone lines.
- PDF/JPG/PNG drawing upload through the existing authenticated customer-document
  API (5 MB UI limit), referenced in the quote notes. The upload saves immediately
  to the linked customer; replacing a reference does not delete the document.
- Customer handoff, catalogue/custom-material links, AI drafting and PDF actions
  remain available. AI drafting is an optional disclosure.
- Browse material cards by family, with workspace-supplied photographs. An Owner
  can set a public HTTPS photo URL in Catalogue > material > pricing form.
  Photos are stored in the tenant override, never in the global reference data.
  Missing/broken images show "Photo not supplied"; no sample texture is passed
  off as the actual stone. Existing catalogue content needs its own images.

## Shared slab pricing

The wizard explicitly groups the pieces of each selected layout, including its
measured upstand/splashback lines. The server requires the same resolved material,
thickness, catalogue variant, slab dimensions and price within a group. It pools
quantity-adjusted areas, applies the existing 15% waste allowance and rounds slabs
once per group. Installation surcharges remain per physical line/quantity.

Material cost is allocated in whole pennies across the lines; the last line gets
the rounding remainder, so line totals reconcile exactly to the quote. Allocation
metadata is persisted in each line's immutable catalogue snapshot and returned on
reopen; PDFs identify the shared estimate. Ungrouped legacy requests/quotes keep
their original calculation.

This is an area-and-waste estimate, not rectangle nesting, seam placement or
vein/grain matching. The editor/review explain that the cutting plan requires
review before issuing a final price. Cut-out, tap-hole and edge requirements are
recorded specifications; this patch does not invent fabrication rates.

## Browser failure diagnosis and verification

The nine initial CI failures were caused by browser journeys using the former
single-page form: attempting hidden measurements or a collapsed AI textarea and
clicking removed layout radio buttons. Tests now navigate the visible wizard;
existing cross-item regressions explicitly exercise the supported all-sections
mode. The layout journey checks all three piece dimensions and the saved result,
not just form labels. No assertions were removed and no timeouts were increased.

The browser-only repair, commit `8ff8919d1e65fd04a5b3ae12491d37a8d98a9389`, passed
all three hosted CI jobs: backend, frontend and E2E (run 39052474607).

Additional pricing/photo changes were locally checked with:

- 381/381 web tests, successful full-suite result.
- 11/11 focused backend tests: grouping, legacy compatibility, incompatible
  materials/thicknesses, quantity/surcharges, penny reconciliation, PDF labelling
  and safe photo-URL input.
- TypeScript, changed-file ESLint and the Next.js production build.
- New database-backed regressions cover allocation round-trip and workspace-photo
  isolation/preservation; hosted CI provides their PostgreSQL execution.
- A new browser check verifies a saved photo in the catalogue selection card,
  using a synthetic image fixture; the U-shape journey checks shared slab totals.

Local PostgreSQL could not start because the container cannot create/switch to
an unprivileged server account. No production database was substituted. Hosted
CI uses its dedicated PostgreSQL service. The additive photo migration was also
checked as generated SQL from the previous migration head.

## Release sequence and limits

1. Require all hosted CI checks on the latest PR head, including migration,
   tenant-isolation, pricing and browser regressions.
2. Apply migration `83d4e5f6a7b8` before the new API; then release the web app.
   Do not deploy the new grouped-quote frontend against the old API, which would
   ignore the optional group field and retain per-piece slab rounding.
3. Verify one controlled quote, its reopened allocation and PDF after deployment.

No production deployment, billing action or customer communication was performed
in this repair. The existing production audit evidence is not replaced by these
local/CI checks. Photographs must be supplied by the workspace or an authorised
source; none are scraped or seeded from the reference site.
