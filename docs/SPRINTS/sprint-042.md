# Sprint 042 — GeoCore Premium OS Plan 03: Master Materials & Supplier Catalogue + Stone Quote Engine V2

**Branch:** `sprint-042-master-catalogue-stone-quote-v2`
**Base:** `origin/main` @ `772551924af63311b15c41397b2dfe30dbee3b25` (Plan 02 merge, PR #43)
**Alembic head at branch point (verified, not assumed):** `bfed99c6fa8c`
**Status:** CODE-COMPLETE — not deployed, not merged

---

## 1. Mission

Build a professional Master Materials & Supplier Catalogue and a Stone Quote
Engine V2 that materially strengthens GeoCore for real stone fabricators — a real
Supplier → Manufacturer → Brand → Collection → Surface → Variant hierarchy, tenant
commercial data kept strictly separate from the shared global reference data, an
immutable commercial snapshot on every catalogue-priced quote line, and a custom
material fallback — while preserving GeoCore as a Stone + Construction OS:
construction (general) quoting continues to work exactly as before, with zero
catalogue involvement.

Authoritative sources, in priority order: the Master Spec
(`2026-09-17-geocore-premium-os-design-v3.md`), the Implementation Roadmap
(`2026-09-17-geocore-premium-os-implementation-roadmap.md`), then existing repo
contracts/tests as the compatibility authority. Plan 04 and every later roadmap
phase are explicitly out of scope for this sprint.

---

## 2. What was built, commit by commit

1. **`feat(catalogue): add master material hierarchy`** — the 7 new/extended
   tables (migration `709c9ed313cc`, parent `bfed99c6fa8c`): `catalogue_suppliers`,
   `catalogue_manufacturers`, `catalogue_brands`, `catalogue_collections`,
   `catalogue_surfaces` (global-or-tenant-private via the `WorkflowTemplate`
   `tenant_id IS NULL` idiom), `catalogue_surface_variants`,
   `tenant_catalogue_overrides` (the only place a price lives), plus
   `quote_items.catalogue_surface_id`/`catalogue_variant_id`/`catalogue_snapshot`
   (all nullable, additive).
2. **`feat(catalogue): add tenant commercial overrides + searchable surface API`** —
   `app/catalogue/` (models, dedupe scoring, service, CRUD, router):
   `GET /catalogue/surfaces` (search, backend-filtered/paginated),
   `GET /catalogue/surfaces/{id}` (detail, global-vs-tenant data distinguished),
   `PUT /catalogue/surfaces/{id}/override` (Owner-only), `POST
   /catalogue/custom-materials` (Owner/Staff). `QuoteCalculator` extended to price
   a catalogue-linked item from the tenant's own override, raising
   `CataloguePriceMissingError` (400) rather than ever fabricating a price.
3. **`feat(catalogue): add controlled catalogue seed pipeline`** —
   `app/catalogue/seed.py`, idempotent, offline-only, never wired into app
   startup (deliberately unlike `app/materials/seed.py`'s auto-seed) — see
   ADR-046. Seeds real, public supplier/manufacturer/brand names with no pricing.
4. **`feat(catalogue): ground AI catalogue search, never fabricate price`** —
   `app/catalogue/ai.py::search_for_ai`, an explicit `price_available: bool` on
   every result, mirroring `app/materials/search.py`'s existing contract.
5. **`feat(catalogue): add material catalogue UI`** — `/catalogue`
   (`apps/web/app/catalogue/`): search/filter, a detail panel distinguishing
   global reference data from the caller's own tenant pricing, and the "Can't
   find your stone? Add custom material" fallback (save-to-catalogue vs.
   quote-only).
6. **`feat(quotes): link stone quotes to catalogue surfaces`** — the stone quote
   builder (`apps/web/app/quotes/new/stone/`) accepts
   `catalogue_surface_id`/`catalogue_variant_id`/`material`/`thickness` as query
   params (arriving from `/catalogue`'s "Use in a stone quote"), pre-fills the
   first item, and sends the linkage through to `POST /quote`. A catalogue-linked
   row shows read-only with a "Change" escape hatch; every other row is
   unaffected.
7. **`feat(catalogue): let a tenant set their own price on a surface`** — the
   detail panel's "Set your price"/"Edit price" form
   (`PUT /catalogue/surfaces/{id}/override`), without which the tenant commercial
   layer had no write path from the UI at all.
8. **`fix(quotes): resolve a surface-level catalogue price for a variant-specific
   quote item`** + **`test(catalogue): add Sprint 042 Master Catalogue E2E journeys
   A-E`** — a real backend gap the new E2E suite found: a surface priced once
   (the common case, `surface_variant_id=NULL`) returned a fabricated-looking 400
   when quoted against a specific variant, because `QuoteCalculator` only ever
   looked up the override at an exact variant match. RED test added first
   (confirmed the 400), then the fix (fall back to the surface-level override),
   then GREEN — alongside `e2e/master-catalogue.spec.ts`'s five journeys.
9. **`docs(catalogue): document the Master Catalogue schema and
   ADR-044/045/046`** — this sprint's schema section and three ADRs.

---

## 3. Architecture

`Supplier → Manufacturer → Brand → Collection → Surface → Variant`, each a real
table, never collapsed — see ADR-044. A surface's `canonical_name` is explicitly
not a safe identity: `app/catalogue/dedupe.py::score_candidate_match` requires a
shared `material_family` as a hard prerequisite and caps a same-name-only match
(no shared supplier/manufacturer/brand/SKU) well below its duplicate threshold —
proven by `tests/test_catalogue.py`'s coexistence tests. The global catalogue
carries **zero pricing columns**; every commercial figure lives in
`tenant_catalogue_overrides`, scoped to one tenant, resolved via
`resolve_price_per_slab`'s precedence (explicit selling price > buy cost + markup
> buy cost / (1 - margin) > `None`, never fabricated). A quote's catalogue-derived
commercial data is snapshotted once, at creation, into `QuoteItem.catalogue_snapshot`
and never re-read afterwards (ADR-045) — proven by both a backend regression test
and Journey A's real-browser proof (reload the quote after changing the catalogue
price; the displayed price is unchanged).

Construction (general) quoting is untouched by construction, not by convention:
`GeneralQuoteLineRequest`/`QuoteService.create_general` never reference the
catalogue at all, and `tests/test_catalogue.py::test_general_construction_quote_never_touches_the_catalogue`
plus `e2e/master-catalogue.spec.ts`'s Journey E assert it directly, in the same
session as a stone catalogue quote.

No platform-admin role was invented (`UserRole` stays `OWNER`/`STAFF` — ADR-046).
The global catalogue is written only by the offline, idempotent
`python -m app.catalogue.seed`; a tenant's own private catalogue and pricing are
written through the ordinary authenticated API by that tenant's own users.

---

## 4. Known limitations

- **Custom material "quote-only" has no backend price-injection path.**
  `POST /catalogue/custom-materials` with `save_to_catalogue: false` creates
  nothing durable at all (by design — Task 9's contract), and returns no
  `surface_id`/`variant_id` for the quote to link against. `QuoteItemRequest` has
  no raw cost/price-override field for a free-text stone line, so a genuinely
  ad-hoc, never-saved custom material cannot currently carry a computed price
  into a quote through the catalogue path — the frontend surfaces this honestly
  ("was recorded for this quote only — it was not saved anywhere, so search
  won't find it again") rather than silently discarding the entered price or
  fabricating a workaround. The "save to my private catalogue" path (the
  common, recommended case, and what Journey C exercises) has no such gap.
- **The catalogue search UI has no supplier/brand/manufacturer/colour/finish
  filter controls beyond text search and material family** — the backend API
  (`GET /catalogue/surfaces`) already accepts `supplier_id`/`manufacturer_id`/
  `brand_id`/`collection_id`/`colour_family`, but the frontend only wires up
  `q` and `material_family`. A deliberate scope cut given the time budget: text
  search covers the common case (typing a stone or brand name), and the richer
  filter UI is additive follow-up work, not a redesign.
- **No pagination UI** — `searchCatalogueSurfaces` requests a bounded page
  (default 30) and the backend supports a `limit` param, but there is no
  "load more"/page-through control yet. Acceptable for the current seed-scale
  catalogue; a real thousands-of-surfaces catalogue would need one before the
  search UI is complete.
- **Analytics events (Task 18) were not added** — no analytics/PostHog
  infrastructure exists anywhere in this repository (confirmed during pre-flight
  discovery), so adding catalogue-specific events would mean introducing a new
  analytics vendor, which Plan 03's own instructions explicitly forbid. A no-op
  by the plan's own rule, not an oversight.
- **`alembic check` reports pre-existing schema drift unrelated to this
  sprint** (on `subscriptions`, `workflow_templates`, `project_workflow_history`,
  `processed_stripe_events`, `email_verification_tokens`,
  `password_reset_tokens` — none of them touched by Plan 03) — inherited from
  earlier sprints, confirmed to involve none of the 7 new/extended Sprint 042
  tables, and out of this plan's scope to fix. `alembic heads`/`current`/
  `upgrade head` (the more reliable checks per the plan's own instructions) are
  all clean: single head `709c9ed313cc`, upgrade is a no-op from this branch.

---

## 5. Full verification

- **Backend:** `pytest tests/ -q` — **1187 passed, 3 skipped, 0 failed**, including
  `tests/test_catalogue.py`'s 24 tests (23 from the earlier backend commits +
  the `_resolve_catalogue_item` surface-level-fallback regression test added
  with this sprint's fix) and `tests/test_catalogue_seed.py`'s 1
- **Frontend (apps/web):** `npx vitest run` — **210 passed, 0 failed**, up from
  193 before this sprint's frontend work (Sprint 041's own baseline) — 17 new:
  13 in `app/catalogue/page.test.tsx` (new file) and 4 in
  `app/quotes/new/stone/page.test.tsx`'s new catalogue-integration describe
  block; `check-types`/`lint` — clean
- **Marketing (apps/marketing):** untouched by this sprint —
  `test:indexability` (9), `test:logo-quality` (1), `test:positioning` (4),
  `test:trial-and-demo-contract` (7) — **21 passed, 0 failed**;
  `check-types`/`lint` clean
- **Monorepo build:** `npx turbo run check-types lint build` — **8/8 successful**
  across `apps/web` and `apps/marketing`, `/catalogue` present in the built route
  list
- **E2E:** `npx playwright test` — **50 passed, 0 failed** (45 pre-existing + 5
  new Plan 03 journeys: A stone catalogue quote + immutable-snapshot regression,
  B tenant price override, C custom material save-and-reuse, D tenant isolation,
  E construction regression alongside a stone catalogue quote in the same
  session)
- **Migration:** single clean head `709c9ed313cc`; `alembic upgrade head` is a
  no-op from this branch's own head; `alembic check` flags only pre-existing,
  unrelated drift (see §4)
- **Repo hygiene:** `git diff --check` clean; `git status --short` clean (no
  stray/untracked files); 25 files changed vs. `origin/main`, all attributable to
  this sprint's own work

---

## 6. Not deployed, not merged

No Railway deployment was performed, no production database was modified, and
this branch has not been merged to `main`. PR to be opened against `main`, not
merged.
