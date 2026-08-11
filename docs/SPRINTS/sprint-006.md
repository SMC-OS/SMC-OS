# Sprint 006 — Projects Module (Job Pipeline)

**Status:** ✅ Done, pending commit approval. Implemented and verified against the live local PostgreSQL 16 instance and a real headless-browser walkthrough; not yet committed to git.

## Objective

`docs/ROADMAP.md`'s Sprint 006 originally bundled two items: "AI Quotation Generator v1" (LLM-assisted text→quote via OpenAI) and the "Projects module" (job pipeline, replacing `/projects/new`'s activity-log-only form). No `OPENAI_API_KEY` is configured anywhere in this project, and real LLM calls cost real money per request — confirmed with the person building this that **AI Quotation Generator is deferred to its own future sprint**, tracked separately in `docs/ROADMAP.md` as unscheduled. **This sprint is Projects module only.**

The `projects` table had existed, empty, since Sprint 002. It had no `status` column, so a real "job pipeline" needed one added — the first migration since Sprint 003's `password_hash` column.

Two decisions were confirmed before implementation:
- **Auth is required** on all `/api/v1/projects/*` routes, consistent with `/api/v1/customers/*` (ADR-021's reasoning applies equally — real business data).
- **AI Quotation Generator is out of scope entirely**, not stubbed or mocked — a clean deferral.

**One necessary deviation from the Sprint 004 Customers precedent, decided by reasoning:** Customers shipped list/detail/create only, no update. A job pipeline is meaningless without the ability to move a project between stages, so this sprint adds one narrow update capability — `PATCH /api/v1/projects/{id}/status` — not a general-purpose edit-everything endpoint.

**Also decided by reasoning:** since customers are now real (Sprint 004), the new-project form links to an actual customer via `customer_id` (a `<select>` backed by `api.getCustomers()`) instead of the previous free-text `customer` field.

## Scope delivered

**Backend — one migration.** `786f58ce4406` adds `status` (`String`, `NOT NULL`, `server_default="enquiry"`) to `Project` — safe, the table had 0 rows, confirmed live.

**Backend — `app/projects/` (new module)**
- `models.py` — `ProjectStatus` (7-stage `str, Enum`: `enquiry`, `quoted`, `booked`, `templated`, `fabricated`, `installed`, `complete` — same convention as `ActivityType`/`NotificationType`, stored as a plain `String` column), `ProjectCreate`, `ProjectOut`, `ProjectStatusUpdate`.
- `service.py` — `ProjectService.list_all()/get()/create()/update_status()`. `create()` logs a real `ActivityEvent` server-side (`project_created`), same pattern Sprint 004 established for customers.
- `router.py` — `GET/POST /projects`, `GET /projects/{id}`, `PATCH /projects/{id}/status`, all `Depends(get_current_user)` — the **second auth-enforced module** (ADR-022).
- `app/database/crud.py` — `create_project`, `get_project_by_id`, `list_projects`, `update_project_status` added.

**Frontend**
- New `types/project.ts`, `lib/projects.ts` (status label + `Badge` tone mapping, mirroring `lib/activity.ts`'s per-type mapping convention).
- `lib/api.ts` — `getProjects`, `getProject`, `createProject`, `updateProjectStatus` added.
- `/projects` — real list from the database, each row shows its current stage as a `Badge`.
- New `/projects/[id]` — detail view: linked customer (if any, links through to `/customers/[id]`), notes, current stage, and an "Advance to \<next stage\>" button (offers only the single next pipeline stage, not a free-for-all dropdown — keeps the pipeline meaningful).
- `/projects/new` — real persistence via `POST /api/v1/projects`; customer field is now a `<select>` of real customers instead of free text; redirects to the new project's detail page.

## Explicitly out of scope for this sprint (by decision, not oversight)

- **AI Quotation Generator v1** — no OpenAI integration, no key, no cost incurred. Tracked as its own unscheduled roadmap item.
- **No general project update/delete** — only `status` can be changed via the API.
- **No Next.js middleware/SSR-level route protection** — same client-side check-on-mount guard pattern as `/customers`.

## Audit results

| Check | Result |
|---|---|
| `alembic upgrade head` against the live local Postgres | ✅ Migration `786f58ce4406` applies cleanly, `status` confirmed via `\d projects` |
| `pytest` (40 tests: 30 existing + 10 new in `test_projects.py`) | ✅ All passing |
| Full pipeline walk (`enquiry` → ... → `complete`) via `PATCH .../status` | ✅ Confirmed manually via `TestClient`, all 6 transitions return `200` with the correct new status |
| Invalid status value | ✅ `422` |
| `401` without a token on all 4 routes | ✅ Confirmed |
| `404` on an unknown project id (GET and PATCH) | ✅ Confirmed |
| `customer_id` round-trips on create | ✅ Confirmed |
| Test fixtures clean up after themselves | ✅ `projects`/`customers` back to 0 rows, `activity_log` back to its real 6-row baseline |
| `tsc --noEmit` | ✅ 0 errors |
| `eslint .` | ✅ 0 errors, 0 warnings |
| `next build` | ✅ All 13 routes compile, including dynamic `/projects/[id]` |
| Real browser walkthrough (Playwright, transient dev tooling, not a project dependency) | ✅ Login → create a customer → create a project linked to it → detail page shows correct name, "Enquiry" status, linked customer, and notes → "Advance to Quoted" works → list view reflects the updated stage. No console errors. Test data (1 project, 1 customer, their activity rows) cleaned up afterward; dev server stopped. |

## A stray cleanup found along the way

While verifying `activity_log` row counts, found a leftover row from Sprint 003's very first manual smoke test (`user_login` / "smoke test" / "x") that had been sitting in the table since that sprint — removed. Also found and fixed a genuine gap in this sprint's own test cleanup (a linked test customer's `ActivityEvent` wasn't being deleted by `test_projects.py`'s fixture) before it could leave similar residue. `activity_log`'s real seeded baseline is **6** rows, not 7 as informally assumed in a couple of earlier sprints' verification notes.

## Follow-up items raised, not part of Sprint 006 scope

- AI Quotation Generator v1 — needs an `OPENAI_API_KEY` and a deliberate go-ahead on incurring usage costs before it can start.
- General project update (name/notes edit) and delete — no concrete need yet, not built.
- Quote persistence (the `quotes` table) — still schema-only, no sprint currently scheduled for it.
