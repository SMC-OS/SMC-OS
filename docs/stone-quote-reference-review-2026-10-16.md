# Stone quote builder: reference implementation draft

Reference: https://yandsmarble.co.uk/online-quote/#f1p1

The owner rejected the small decorative layout picker and approved replacing
the stone quote experience using this reference. This change is a draft for
review, not a claim of exact visual or functional parity.

## Implemented

- Four guided sections: material/customer, layout, design details, review.
- Eight reference layout combinations, plus the existing peninsula/custom path.
- Original, large vector plans with individually labelled A/B/C/D pieces.
- Independent dimensions for every active piece; existing quote API receives
  one measured line per piece. Values survive step and layout changes.
- Sink mounting, hob cut-outs and tap-hole specifications.
- Measured upstands and splashbacks generate their own priced stone lines.
- PDF/JPG/PNG drawing upload (5 MB UI limit) through the existing authenticated,
  tenant-scoped customer-document API. The resulting document ID and filename
  are recorded in the quote notes. Upload requires a linked customer and saves
  the document immediately; replacing the reference does not delete that file.
- Customer selection is carried from the general quote link to the stone form.
- Existing AI draft, catalogue/custom-material handoffs and quote/PDF actions
  remain available. AI drafting is an optional disclosure.

## Reference differences and release limits

- The catalogue schema has no material image field and the repository has no
  product photographs. Photo/colour-card catalogue selection is **not built**;
  the real catalogue search remains. No competitor product imagery, prices or
  stock are imported or invented. This prevents calling the requested exact
  reference replacement complete.
- GeoCore branding is retained. This is not a pixel-identical site clone.
- The existing calculator rounds slab estimates separately for each line,
  including newly measured pieces and upstands/splashbacks. It does not share
  slabs across pieces or perform cutting/nesting optimization. The editor and
  review explicitly disclose this; prices require business review before use.
- Sink/hob/tap-hole/edge selections are recorded specifications; this patch
  does not invent fabrication rates or add those charges.
- Drawing files belong to the linked customer's document library; there is no
  new quote-attachment database relation in this patch.

## Verification

- New behavior tests were observed failing before implementation.
- Focused editor and layout tests: 24 passed.
- Final full web suite, including the optional-AI disclosure: 380 passed, 0 failed.
- TypeScript check, changed-file ESLint and Next.js production build passed.
- Rendered actual editor source in a synthetic-data preview (API/auth adapters
  mocked, no production connection). Checked the desktop four-piece diagram,
  navigation into details, and a 390px iframe rendering of the L+island layout.
  This is UI evidence, not a live production/API or real-device end-to-end test.
- No production deployment, customer communication, billing or data changes.

Keep the pull request draft until the missing material-photo experience and
business pricing expectations have been resolved and the owner has reviewed
the resulting experience against the reference.
