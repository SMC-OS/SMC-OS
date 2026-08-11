# Sprint 005 — Full Material Library + Accurate Slab-Yield Calculator

**Status:** ✅ Done, pending commit approval. Implemented and verified against the live local PostgreSQL 16 instance and a real headless-browser walkthrough; not yet committed to git.

## Objective

Deliver the roadmap's Sprint 005 item — "Full Material Library (quartz/granite/marble/porcelain/Dekton, real supplier pricing) + accurate slab-yield calculator (replaces the 'temporary estimate' in `slab_calculator.py`)."

Three scope decisions were confirmed before implementation:
- **Materials moved into the database** (`app/materials/`, seeded) rather than staying a bigger hardcoded dict — matching the `materials` table's original intent and the `app/customers/` precedent from Sprint 004.
- **No new API endpoints.** The catalogue stays internal, consumed by `/api/v1/quote`, `/api/v1/estimate`, `/api/v1/process` — not exposed as `/api/v1/materials`.
- **Worktop depth is a hardcoded standard (650mm)**, not a new request field — `QuoteRequest`'s contract and the quote form stay untouched.

## Honesty notes (read before trusting these numbers commercially)

- **"Real supplier pricing" means an internally consistent, clearly-labelled reference catalogue** — not data sourced from a live supplier feed. No such data source exists in this project. Every price in `app/materials/seed.py` is illustrative; an operator should edit them to match actual supplier costs before relying on them for real quotes.
- **"Accurate slab-yield calculator" means a real area-based formula with a documented wastage allowance** — not a fabrication-grade cutting/nesting optimizer. A true nesting algorithm (seam placement, grain/pattern matching, actual slab defects) is a materially larger, separate problem, out of scope here.
- **`ISLAND_EXTRA_RUN_M = 1.8`** carries forward a pre-existing assumption from the Sprint 001 placeholder (previously an unexplained magic number) — now named and documented, but still not derived from real job data (none exists in this project yet).

## Scope delivered

**Backend — `app/materials/` (new module)**
- `service.py` — `MaterialService.list_all()`/`get_by_name_and_thickness()`.
- `seed.py` — seeds ~30 rows (15 named materials × 2 thicknesses) across the 5 roadmap categories if `materials` is empty, guarded like every other seed. 30mm price = 20mm price × a single documented markup constant (`THICKNESS_30MM_MARKUP = 1.35`), not hand-picked per row.
- `app/database/crud.py` — `create_material`, `list_materials`, `get_material_by_name_and_thickness` added.
- No migration — the `materials` table (Sprint 002) already had everything needed; one row per (name, thickness).

**Backend — the yield formula (`app/quotes/slab_calculator.py`, rewritten)**
Real geometry, documented constants: standard 650mm depth, 15% wastage allowance, named per-extra areas for waterfall/splashback/upstands, island adds a documented extra run. Replaces `if total_length > 3.2: slabs = 2 else: slabs = 1`.

**Backend — thickness-aware pricing (a real bug fix, not planned scope, fell out of the DB move)**
`thickness` had been collected on every quote request since Sprint 001 and silently ignored — price was looked up by material name only. `QuoteCalculator` now looks up `(material, thickness)`, so 30mm actually costs more than 20mm for the first time.

**Backend — the db-threading ripple**
Moving from a synchronous dict to a DB query meant every consumer needed a `Session`: `QuoteCalculator.calculate(db, quote)`, `QuoteGenerator.generate(db, request)`, `SalesAssistant.reply(db, text)`, `SearchAssistant.search(db, text)`, `BrainManager.process(db, text)`, and `/api/v1/process`/`/quote`/`/estimate`/`/quote/pdf` all gained `Depends(get_db)`. `app/assistant/estimator.py` was **not** touched — its 3 hardcoded material-name checks are independent of the catalogue and remain valid entries in the new one; making free-text parsing fully catalogue-driven is Sprint 006 territory ("AI Quotation Generator v1"), not this sprint.

**Error handling — unchanged, same seam reused.** A missing `(material, thickness)` combination raises `KeyError`, exactly as the old dict-subscript miss did, so Sprint 003's global `KeyError → 400` handler needed no changes.

**`app/data/materials.py`/`pricing.py`** — superseded, left in place with a comment (ADR-008: archive, don't delete without approval), no longer imported anywhere.

**Frontend**
- `apps/web/types/quote.ts` — `MATERIAL_OPTIONS` expanded from 3 to all 15 seeded material names.
- `apps/web/app/quotes/new/page.tsx` — stale "3-material catalogue" copy corrected.

## Explicitly out of scope for this sprint (by decision, not oversight)

- **No `/api/v1/materials` endpoint** — catalogue stays internal.
- **No per-material slab size** — every seeded row uses the standard `3200x1600`; the column supports per-row overrides later.
- **No editable worktop depth** — hardcoded 650mm, not a new `QuoteRequest` field.
- **`app/assistant/estimator.py` untouched** — still 3 hardcoded material names, not catalogue-driven.

## Audit results

| Check | Result |
|---|---|
| `pytest` (30 tests: 23 existing + 5 new in `test_materials.py` + 2 new in `test_quotes.py`) | ✅ All passing against the real local Postgres |
| Catalogue seeded, all 5 categories present | ✅ Confirmed via `psql`: Quartz 10 rows, Granite 6, Marble 6, Porcelain 4, Dekton 4 (30 total) |
| Thickness pricing differs | ✅ Calacatta Gold: £2,650 (20mm) → £3,580 (30mm); Absolute Black: £3,100 → £4,180 |
| Unrecognised material/thickness still `400` | ✅ Confirmed via `TestClient` |
| `/api/v1/process` sales + search paths work against the new catalogue | ✅ Confirmed manually (Dekton Sirocco lookup, granite search) |
| `/api/v1/estimate` free-text parsing still works | ✅ "3.5m kitchen in calacatta oro with island" → correct quote |
| `tsc --noEmit` | ✅ 0 errors |
| `eslint .` | ✅ 0 errors, 0 warnings |
| `next build` | ✅ All 13 routes compile |
| Real browser walkthrough (Playwright, transient dev tooling, not a project dependency) | ✅ Dropdown shows all 15 materials; submitted a real quote (30mm Absolute Black, 4.2m run, island) — result verified by hand against the formula: total run 6.0m × 0.65m depth × 1.15 wastage = 4.485m² → 1 slab; £4,180 × 1 + £450 island = £4,630 subtotal → £5,556 total. Exact match. No console errors. Test data cleaned up afterward, dev server stopped. |

## Follow-up items raised, not part of Sprint 005 scope

- Replacing the reference pricing with real supplier costs is an operator task, not an engineering one — flagged, not actioned.
- A true cutting/nesting optimizer, if ever needed, is separate, larger scope.
- `app/assistant/estimator.py` becoming catalogue-driven (or LLM-based) is Sprint 006's territory.
- Per-material slab sizes (natural stone slabs vary more than manufactured quartz/porcelain) — the schema already supports it, just not populated with varied data this sprint.
