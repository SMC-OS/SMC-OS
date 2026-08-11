# Sprint 007 — Real Quote Persistence, Downloadable Invoices, Real Dashboard Stats

**Status:** ✅ Done, pending commit approval. Implemented and verified against the live local PostgreSQL 16 instance and a real headless-browser walkthrough (including manually inspecting a rendered invoice PDF); not yet committed to git.

## Objective

`docs/ROADMAP.md`'s Sprint 007 is "Invoice generator (proper PDF, VAT breakdown, downloadable); dashboard polish (Recent Activity reflects real DB events)." Both halves turned out to hinge on the same missing piece: quotes were calculated but never saved anywhere — the `quotes` table had existed empty since Sprint 002. Without persistence, there's no honest source for "Today's Quotes"/"Revenue" on the dashboard, and no permanent record to generate a re-downloadable invoice from.

**Confirmed with the user before implementation:** quotes get persisted for real this sprint, not left ephemeral — the only choice that makes both halves of the sprint's name true. Consequence, by the same reasoning Sprint 006 used for its own customer-linking upgrade: `/quotes/new` needed a customer picker, because the `quotes` table only supports linking via `customer_id` (FK), not a free-text name.

## What this unlocked / required

- The `quotes` table already had every column `QuoteCalculator` produces — **no migration needed**.
- `QuoteRequest.customer` (free-text name) stayed required and unchanged — `/estimate`'s regex path has no way to resolve a real customer, so a plain name had to keep working standalone. A new optional `customer_id` was added alongside it.
- Persistence lives in one new seam (`app/quotes/service.py`), not duplicated per route — both `/quote` and `/estimate` go through it.
- `POST /api/v1/quote/pdf` was retired outright, not kept alongside the new flow — replaced by `GET /api/v1/quotes/{id}/invoice`, downloadable now and again later, not just at calc-time.
- `/api/v1/quotes/*`'s *browsing* routes are auth-required (third enforced module, ADR-023) — but `POST /quote`/`/estimate` (creation) deliberately stay public, an intentional asymmetry explained in ADR-023, not an inconsistency.
- `GET /api/v1/dashboard` stays public (consistent with `/activity`) but now computes real numbers.

## Scope delivered

**Backend**
- `app/quotes/models.py` — `QuoteRequest` gains `customer_id: uuid.UUID | None`; new `QuoteOut`.
- New `app/quotes/service.py` — `QuoteService.create()`: calculates via the existing `QuoteCalculator`, persists via `crud.create_quote`, logs a real `ActivityEvent` (`quote_created`) server-side — same pattern Sprint 004/006 established for customers/projects.
- New `app/quotes/router.py` — `GET /quotes`, `GET /quotes/{id}`, `GET /quotes/{id}/invoice`, all `Depends(get_current_user)`.
- `app/quotes/pdf.py`, rewritten — letterhead, a real VAT breakdown table (material/thickness line, VAT, total), generated to `io.BytesIO()` and returned as a genuine `application/pdf` download with a `Content-Disposition` header, not written to local disk.
- `app/database/crud.py` — `create_quote`, `get_quote_by_id`, `list_quotes`, `count_quotes_today`, `sum_quotes_revenue`, plus `count_customers`/`count_projects` (needed by the now-real dashboard, hadn't existed yet).
- `app/api/v1/core.py` — `/quote` and `/estimate` now call `quote_service` instead of `QuoteCalculator` directly; `/quote/pdf` removed entirely; `/dashboard` gains `Depends(get_db)` and computes real numbers.
- `app/quotes/generator.py` marked superseded (no longer imported), left in place per ADR-008.

**Frontend**
- `/quotes` — replaced the activity-feed (`ModuleIndexPage`) pattern with a real list; auth-gated.
- New `/quotes/[id]` — full price breakdown, linked customer (if any), Download Invoice button; auth-gated.
- `/quotes/new` — adds a "Link to existing customer (optional)" picker (same UX as `/projects/new`'s); removes the frontend's `api.logActivity()` call (the backend logs it now); result panel gets a Download Invoice button, shown only when signed in (creating a quote itself stays available signed-out, matching `POST /quote`'s public status — but downloading needs a token, so the UI says so honestly instead of showing a button that would fail).
- `apps/web/lib/api.ts` — `getQuotes`, `getQuote`, `downloadInvoice` (fetches the PDF as a blob, triggers a real browser download via a synthetic `<a download>`, no new dependency).

## A real limitation, stated plainly

The `quotes` table has no text column for the customer's name — only `customer_id` (FK). A quote created without linking a real customer has its name echoed back in the calculation response but **not stored** anywhere; `GET /api/v1/quotes/{id}` for such a quote shows no customer at all, and its invoice says "No customer linked." This is a direct, honest consequence of the existing Sprint 002 schema (no migration was in scope this sprint) — flagged here rather than left to be discovered.

## Explicitly out of scope for this sprint (by decision, not oversight)

- **AI Quotation Generator v1** — still deferred (split out of Sprint 006, tracked separately in `docs/ROADMAP.md`, unrelated to this sprint).
- **No general quote update/delete** — list/detail/create(+invoice) only, matching the Customers precedent.
- **No schema change** — the customer-name gap above is a known limitation, not fixed this sprint.

## Audit results

| Check | Result |
|---|---|
| `pytest` (50 tests: 40 existing + 9 new in `test_quotes_api.py` + 1 new in `test_dashboard.py`) | ✅ All passing against the real local Postgres |
| Quote creation persists and is listed/fetchable | ✅ Confirmed |
| `customer_id` round-trips on create | ✅ Confirmed |
| Creating a quote logs a matching `ActivityEvent` | ✅ Confirmed |
| Invoice download: `Content-Type: application/pdf`, real `Content-Disposition`, `%PDF` magic bytes | ✅ Confirmed via `TestClient` and independently via a real Playwright download event |
| `401` on all 3 `/api/v1/quotes/*` routes without a token | ✅ Confirmed |
| `404` on an unknown quote id (detail and invoice) | ✅ Confirmed |
| Old `/api/v1/quote/pdf` route is gone | ✅ Confirmed `404` |
| Dashboard reflects real counts/revenue after creating a customer, project, and quote | ✅ Confirmed via `pytest` and manually in a real browser (`Today's Quotes` 0→1, `Revenue` £0→£5,352, `Customers`/`Projects` incremented) |
| Manually rendered invoice PDF inspected visually | ✅ Letterhead, VAT breakdown table, and totals all correct — checked by hand against the calculation |
| Test fixtures clean up after themselves | ✅ `quotes`/`customers`/`projects` back to 0 rows, `activity_log` back to its 6-row baseline |
| `tsc --noEmit` | ✅ 0 errors |
| `eslint .` | ✅ 0 errors, 0 warnings |
| `next build` | ✅ All 13 routes compile, including dynamic `/quotes/[id]` |
| Real browser walkthrough (Playwright, transient dev tooling, not a project dependency) | ✅ Login → create a customer → calculate a quote linked to it → download the invoice (captured via Playwright's real download event, verified `%PDF` magic bytes) → quotes list shows it → detail page shows the linked customer and full breakdown → dashboard stat cards updated. No console errors. Test data cleaned up, dev server stopped. |

## Follow-up items raised, not part of Sprint 007 scope

- A `quotes.customer_name` text fallback column, if unlinked-quote name retention ever becomes a real need — not built, flagged above.
- AI Quotation Generator v1 — still needs an `OPENAI_API_KEY` and a deliberate go-ahead on usage costs.
- Quote update/delete — no concrete need yet.
