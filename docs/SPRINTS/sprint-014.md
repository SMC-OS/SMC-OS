# Sprint 014 — Portal Link Activity Logging + Management UI

**Status:** ✅ Done. Implemented and verified against the real backend test suite, the frontend build/lint/typecheck, `alembic check`, and a manual smoke test against the real running app (uvicorn + local PostgreSQL 16). Code committed (`2da7202`, `29fec14`, `1ea95ef`); this completion record not yet committed as of this writing.

## Objective

`docs/ROADMAP.md`'s v1.0 table lists Sprint 014 as "Contracts + digital signatures; Payment tracking (Stripe/GoCardless)." That line is stale — `sprint-013.md` and `sprint-008.md` both already flag the roadmap's Sprint 008–016 table as a pre-SaaS-replan draft that actual sprint numbering diverged from long ago. Nothing in this sprint (or any sprint since the replan) touches contracts, signatures, or payments, and that original scope remains entirely unaddressed and unscheduled under any sprint number — reconciling the roadmap table itself stays a separate, out-of-scope documentation decision, not touched here.

Sprint 014 closes two related gaps: the one item `sprint-013.md`'s "Follow-up items raised, not part of Sprint 013 scope" section named explicitly, plus a second gap found during this sprint's own planning:

1. Portal link creation didn't log an `ActivityEvent` — every other creation flow (customers/projects/quotes/tenants) does. (Found during this sprint's planning, not named in `sprint-013.md`.)
2. The `GET`/`DELETE /api/v1/portal-links` routes shipped in Sprint 013 with no frontend consumer. (Named explicitly in `sprint-013.md`'s follow-up list.)

This was confirmed with the user during planning (`docs/superpowers/specs/2026-08-15-sprint-014-portal-followups-design.md`), including the explicit decision that Sprint 014 = finishing this in-flight portal follow-up work, not the roadmap's stale Contracts+Payments line.

## Scope delivered

**Backend**
- `ActivityType.PORTAL_LINK_CREATED` enum value added (`app/activity/models.py`).
- `PortalService.create_link()` (`app/portal/service.py`) now calls `activity_service.log()` after the row is created — title "Portal link shared", description set to the customer's name, `tenant_id` passed explicitly (same shape every other creation flow uses).
- Revoke deliberately does **not** log an activity event — matches `revoke_invitation()`'s create-only-logs precedent.
- No new routes. No new migration: `ActivityLog.type` is a plain `String` column (`app/database/models.py`), not a Postgres-native enum, confirmed directly — adding a new Python-side enum value requires zero schema change.

**Frontend**
- `apps/web/app/customers/[id]/page.tsx`'s existing "Client portal" card (Sprint 013) gained a list of existing portal links: created/expires dates, a status `Badge` (`active`=success, `revoked`=neutral, `expired`=warning), and a "Revoke" button shown only on active links.
- Consumes the pre-existing (Sprint 013) `api.getPortalLinks`/`api.revokePortalLink` client methods — no new API client code was needed.
- One fix-round during review: `loadPortalLinks` wasn't clearing a stale `linksError` on reload, which could leave a prior failed load's error message on screen even after a subsequent successful load (e.g. after creating a new link). Fixed by adding `setLinksError(null)` at the top of `loadPortalLinks`, covering all three call sites (mount, after-create, after-revoke) with one change.

**Docs**
- `docs/SYSTEM_ARCHITECTURE.md` — two clauses added: the `app/portal/service.py` folder-tree comment now notes `create_link()` logs an ActivityEvent (and that revoke deliberately does not), and the `/customers/[id]` frontend route-table row now notes the portal-link card lists/revokes existing links as of this sprint.
- `docs/USER_ROLES.md` — inspected, not changed: its one portal-related sentence (the "Customer (client portal)" row) only names document/invoice-download and messaging as deferred: it never claimed there was no activity logging or no list/revoke UI, so it needed no correction.
- `docs/ROADMAP.md` — **not touched**, same precedent as Sprints 012/013: reconciling the stale Sprint 008–016 table remains a separate, out-of-scope decision.

## Test-suite coverage

2 new tests added to `tests/test_portal.py`:
- `test_create_portal_link_logs_activity` — creates a portal link, then fetches `/api/v1/activity?limit=50&type=portal_link_created` and asserts the resulting event has description equal to the customer's name and title "Portal link shared". Filtered by `?type=portal_link_created` specifically because the test customer's own setup already logs a `customer_added` event with that same description — without the filter the assertion could pass for the wrong reason.
- `test_create_portal_link_activity_not_visible_to_other_tenant` — creates a portal link under one tenant, then asserts a second tenant's activity feed (filtered the same way) does not contain that event. A real tenant-isolation check, following the ADR-029 convention.

## Audit results

| Check | Result |
|---|---|
| `pytest` (136 tests: 134 pre-existing + 2 new) | ✅ 136 passed, 173 warnings (pre-existing deprecation warnings, unrelated to this sprint) — run twice, once after Task 1 and again after both Task 1 and Task 2 were committed, same result both times |
| `pnpm lint` | ✅ 2 successful, 2 total, 0 errors/warnings |
| `pnpm build` (includes Next.js's own TypeScript check — `apps/web` has no standalone `check-types` script, matching the existing CI workflow's setup) | ✅ Compiled successfully, TypeScript passed ("Finished TypeScript in 3.8s"), 15 routes generated (14 app routes + `/_not-found`) — same route count as the Sprint 013 baseline, no new routes added |
| `alembic check` | ✅ "No new upgrade operations detected." — confirms no migration was needed |
| Manual smoke test against the real running app (uvicorn + local PostgreSQL, not the pytest `TestClient`) | ✅ Created a portal link via the real API — activity event logged exactly once with the correct title/description; link listed with status "active"; revoked via `DELETE` — status flipped to "revoked", re-checked the activity feed — still exactly 1 event (confirms revoke does not log). A literal browser-rendered visual check of the Badge/list UI was **not** performed in this smoke test — verified instead via a thorough diff-level review of the exact render logic and a clean `next build`. |

## Follow-up items raised, not part of Sprint 014 scope

- Documents (upload/storage/serving) and messaging remain unstarted — deferred since Sprint 013.
- `docs/ROADMAP.md`'s stale Sprint 008–016 table remains unreconciled — still a separate, larger documentation decision.
- The roadmap's original Sprint 014 scope (Contracts + digital signatures; Payment tracking via Stripe/GoCardless) remains entirely unaddressed and unscheduled under any sprint number.
- Sprint 015 is not started.
