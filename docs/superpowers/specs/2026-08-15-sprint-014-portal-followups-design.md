# Sprint 014 Design — Portal Link Activity Logging + Management UI

**Status:** Approved for implementation (design phase only — not yet implemented/committed as of this writing)
**Date:** 2026-08-15
**Depends on:** Sprint 013 (commit `8e581de`, closed and accepted — not reopened by this sprint)

## 1. Objective

Close two related gaps in the Sprint 013 portal-link feature:

1. Portal link creation didn't log an `ActivityEvent` — every other creation flow (customers/projects/quotes/tenants) does. This was found during this sprint's planning (from the working tree's uncommitted diff); `docs/SPRINTS/sprint-013.md` does not name it anywhere.
2. The `GET`/`DELETE /api/v1/portal-links` routes shipped in Sprint 013 with no frontend consumer. This one `docs/SPRINTS/sprint-013.md`'s "Follow-up items raised, not part of Sprint 013 scope" section explicitly named.

## 2. Reconciliation against the roadmap

`docs/ROADMAP.md`'s original table lists Sprint 014 as "Contracts + digital signatures; Payment tracking (Stripe/GoCardless)." That table is explicitly flagged as stale in `sprint-013.md` and `sprint-008.md` — actual sprint numbering diverged from it long ago (e.g. the roadmap's Sprint 015 content, RBAC/staff invitations, actually shipped as Sprint 010-011). Nothing in the repo touches contracts, signatures, or payments.

What's actually in flight: `git status` at the start of this planning session showed 4 uncommitted files (`app/activity/models.py`, `app/portal/service.py`, `apps/web/app/customers/[id]/page.tsx`, `tests/test_portal.py`). The `app/portal/service.py` diff contains an inline code comment reading `# Sprint 014 — every other creation flow ... logs an ActivityEvent; portal links didn't.` — the in-progress code already self-identifies as Sprint 014, and implements exactly the two follow-up items above.

**Decision (user-confirmed):** Sprint 014 = finishing this in-flight portal follow-up work, not the roadmap's stale Contracts+Payments line. That line remains deferred, unnumbered, for a future sprint.

## 3. User/business outcome

Staff/Owner users get portal-link-sharing visibility in the existing Recent Activity feed, and can see and revoke previously-issued links from a customer's page without touching the database. Zero change to public portal (customer-facing) behavior.

## 4. Exact scope and deliverables

All four are already written, uncommitted in the working tree, and verified passing as of this planning session:

- `ActivityType.PORTAL_LINK_CREATED` enum value (`app/activity/models.py`, 1 line added).
- `PortalService.create_link()` calls `activity_service.log(...)` after row creation (`app/portal/service.py`), title "Portal link shared", description = customer name. Revoke deliberately does **not** log — matches `revoke_invitation()`'s create-only-logs precedent.
- Customer detail page: an "existing links" list under the portal-link card — created/expires dates, status `Badge` (`active`=success, `revoked`=neutral, `expired`=warning), Revoke button shown only on active links (`apps/web/app/customers/[id]/page.tsx`).
- 2 new backend tests (`tests/test_portal.py`): `test_create_portal_link_logs_activity`, `test_create_portal_link_activity_not_visible_to_other_tenant`.

Verified: full backend suite is **136 passed** (134 baseline + 2 new), run directly via `.venv/Scripts/python.exe -m pytest tests/ -q`.

## 5. Existing implementation reused

- `activity_service.log()` — identical call shape to customers/projects/quotes/tenants/invitations.
- `PortalService.derive_status()` — unchanged.
- `GET`/`DELETE /api/v1/portal-links` routes and `api.ts` client methods (`getPortalLinks`, `revokePortalLink`) — shipped Sprint 013, unused until now.
- `Badge` component (`apps/web/components/ui/Badge.tsx`) — no changes needed; `success`/`neutral`/`warning` tones already exist.

## 6. Backend/API work

None outstanding — already written. No new routes. One new `ActivityType` value + one new `activity_service.log()` call inside `PortalService.create_link()`.

## 7. Frontend work

None outstanding — already written. Customer detail page consumes existing endpoints; no new API client methods needed.

## 8. Database/migration work

**None.** `ActivityLog.type` is a plain `String` column (`app/database/models.py`), not a Postgres-native enum — confirmed directly. Adding `PORTAL_LINK_CREATED` to the Python-side enum requires zero schema change and no Alembic migration.

## 9. Auth/RBAC requirements

Unchanged. List/revoke already require `get_current_user` (any authenticated tenant user, not Owner-gated) — matches ADR-030's reasoning that sharing/managing a link is routine Staff work, not a tenant-control decision. No new permission checks needed.

## 10. Tenant-isolation requirements

Unchanged, already enforced per ADR-029: `list_portal_links`/`revoke_portal_link` filter by `current_user.tenant_id`. The new activity log call passes `tenant_id=tenant_id` explicitly. `test_create_portal_link_activity_not_visible_to_other_tenant` verifies a second tenant cannot see another tenant's portal-link activity event.

## 11. Security considerations

Low risk — additive visibility/management tooling over data the caller could already read (their own tenant's portal links) or infer (that a link was created, since they created it). No new attack surface: no new public route, no new PII exposure (activity description is just `customer.name`, already visible elsewhere in the tenant's own UI).

## 12. Tests and acceptance criteria

- Full backend suite passes: **136/136**, verified directly this session.
- `test_create_portal_link_logs_activity`: creating a link produces a `portal_link_created` activity event with the customer's name.
- `test_create_portal_link_activity_not_visible_to_other_tenant`: a second tenant's activity feed doesn't show it.
- Still needed before calling the sprint done (not yet run this session):
  - `tsc --noEmit`, `eslint`, `next build` clean on the frontend.
  - `alembic check` — expect no new operations (no model/column change).
  - Manual smoke test in the running app: generate a portal link on a customer page, confirm it appears in the list with correct status/badge, revoke it, confirm the list updates and the button disappears, confirm the event appears in Recent Activity.

## 13. Exact files/modules likely affected

- `app/activity/models.py` (modified, done)
- `app/portal/service.py` (modified, done)
- `tests/test_portal.py` (modified, done)
- `apps/web/app/customers/[id]/page.tsx` (modified, done)
- `docs/SPRINTS/sprint-014.md` (new — completion record, written after implementation, matching the format every prior sprint doc uses)
- `docs/CHANGELOG.md` (new entry)
- `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md` (minor updates only if their portal descriptions need updating to mention activity logging + the list/revoke UI now being consumed)
- `docs/ROADMAP.md` — **not touched**, same precedent as Sprint 012/013: reconciling the stale Sprint 008–016 table stays a separate, explicitly out-of-scope decision.

## 14. Dependencies and blockers

None. Depends only on Sprint 013 (done, committed, closed — not reopened by this sprint). No external services, no new packages.

## 15. Explicit OUT OF SCOPE

- Contracts, digital signatures, or payment tracking (Stripe/GoCardless) — the stale roadmap's original Sprint 014 line. Deferred to a future sprint under whatever number a roadmap reconciliation eventually assigns it.
- Document upload/storage and messaging — still deferred from Sprint 013, untouched.
- Reconciling `docs/ROADMAP.md`'s stale Sprint 008–016 table itself.
- Any change to portal token design, auth, or tenant-isolation semantics (ADR-029/ADR-030 stand unchanged).
- Revoke-action activity logging (deliberately excluded, matches `revoke_invitation()` precedent).
- Sprint 013 itself — closed and accepted (commit `8e581de`), not reopened or modified by this sprint.
- Starting Sprint 015 or any work beyond this sprint's scope.

## 16. Architectural decisions requiring approval

**One judgment call, resolved (user-confirmed):** this does not warrant a new ADR. Nothing here is a new architectural decision — it applies two already-decided conventions (activity-logs-on-creation, and consuming an already-built API) to close a known gap. It will be recorded in `sprint-014.md` and the changelog only; no ADR-031.

## 17. Verification strategy

1. Re-run the full backend suite immediately before commit (already confirmed once: 136/136; re-confirm in case anything shifts).
2. Run frontend checks: `tsc --noEmit`, `eslint .`, `next build` (not yet run this session).
3. Manual smoke test in the running app: create → list → revoke a portal link on a real customer; confirm the Activity feed shows the event; confirm cross-tenant isolation holds.
4. `alembic check` to confirm zero migration drift.
5. Write `docs/SPRINTS/sprint-014.md` + a `docs/CHANGELOG.md` entry documenting the above results, matching the Sprint 013 record format.

## Notes on process

This design was produced via the Superpowers brainstorming workflow (architectural path). A research fork was dispatched to inventory the repo (roadmap, ADRs/`DECISIONS.md`, `USER_ROLES.md`, `SYSTEM_ARCHITECTURE.md`, sprint history, uncommitted diffs); every factual claim in this document (diff contents, test count, schema shape, follow-up items, roadmap staleness) was independently re-verified by direct `git diff`, `git status`, `grep`, and a live `pytest` run rather than taken solely on the fork's report. Two decisions were confirmed explicitly with the user: (a) Sprint 014 = finishing the in-flight portal follow-ups, not the roadmap's stale Contracts+Payments line; (b) no new ADR is needed.

Per explicit instruction, no files were modified, no code implemented, and nothing committed or pushed as part of producing this design. Sprint 015 was not started. `docs/ROADMAP.md` was not modified.
