# Sprint 014 — Portal Link Activity Logging + Management UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two Sprint 013 follow-up items — portal link creation not logging an `ActivityEvent`, and no frontend UI to list/revoke existing portal links — verify, document, and commit the already-written code that does both.

**Architecture:** No new architecture. Reuses the existing `activity_service.log()` convention (same call shape as every other creation flow) inside `PortalService.create_link()`, and consumes the already-shipped `GET`/`DELETE /api/v1/portal-links` routes from a new section of the existing customer detail page. All four source-file changes already exist, uncommitted, in the working tree; this plan verifies, tests, documents, and commits them — it does not design new code.

**Tech Stack:** FastAPI/SQLAlchemy 2.0 backend (Python 3.12, `.venv`), Next.js 16/React 19 frontend (TypeScript, Tailwind v4, pnpm/Turborepo), pytest, Alembic.

**Spec:** `docs/superpowers/specs/2026-08-15-sprint-014-portal-followups-design.md`

## Global Constraints

- No database migration — `ActivityLog.type` is a plain `String` column, not a Postgres-native enum (spec §8).
- No new routes, no new API client methods, no auth/RBAC change, no tenant-isolation change (spec §6/§7/§9/§10).
- `docs/ROADMAP.md` must NOT be modified (spec §4, out-of-scope precedent from Sprint 012/013).
- No new ADR — record only in `docs/SPRINTS/sprint-014.md` and `docs/CHANGELOG.md` (spec §16).
- Sprint 013 (commit `8e581de`) must not be reopened or modified.
- Do not push to any remote at any point in this plan — commits are local only unless the user separately asks for a push.

---

## Task 1: Verify and commit the backend activity-logging change

**Files:**
- Modify (already done, uncommitted): `app/activity/models.py`
- Modify (already done, uncommitted): `app/portal/service.py`
- Modify (already done, uncommitted): `tests/test_portal.py`

**Interfaces:**
- Consumes: `activity_service.log(ActivityEventCreate, tenant_id: uuid.UUID)` — existing signature in `app/activity/service.py`, unchanged.
- Produces: `ActivityType.PORTAL_LINK_CREATED` (importable from `app.activity.models`) for Task 2/3 verification and for any future consumer of the activity feed.

- [ ] **Step 1: Confirm the enum addition**

Run: `git diff app/activity/models.py`

Expected: exactly one line added, `PORTAL_LINK_CREATED = "portal_link_created"`, inside the `ActivityType(str, Enum)` class alongside the existing `AI_REQUEST`, `USER_LOGIN`, `TENANT_CREATED` members. If the diff shows anything else (a different value spelling, a removed member, changes outside this enum), stop and flag it — do not proceed until the diff matches exactly this one addition.

- [ ] **Step 2: Confirm the service change**

Run: `git diff app/portal/service.py`

Expected: two new imports (`from app.activity.models import ActivityEventCreate, ActivityType` and `from app.activity.service import activity_service`), and inside `PortalService.create_link()`, after the `PortalLink` row is created and before `return row, raw_token`, a call:

```python
activity_service.log(
    ActivityEventCreate(
        type=ActivityType.PORTAL_LINK_CREATED,
        title="Portal link shared",
        description=customer.name,
    ),
    tenant_id=tenant_id,
)
```

where `customer` is the `Customer` row already fetched earlier in the method (via `crud.get_customer_by_id`) to validate `customer_id`. Confirm `revoke_link()` (or equivalent revoke method) in the same file has **no** matching `activity_service.log()` call — revoke must not log, per spec §6.

- [ ] **Step 3: Confirm the test additions**

Run: `git diff tests/test_portal.py`

Expected: two new test functions appended, `test_create_portal_link_logs_activity` and `test_create_portal_link_activity_not_visible_to_other_tenant`, both under a `# --- Sprint 014` comment marker. Confirm the first asserts a `GET /api/v1/activity?limit=50&type=portal_link_created` response contains an event with `description == <customer name>` and `title == "Portal link shared"`; confirm the second asserts the same query under `other_tenant_auth_headers` does not contain that event.

- [ ] **Step 4: Run the full backend suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: `136 passed` (134 pre-existing + the 2 new tests from Step 3). If any test fails, stop — do not proceed to commit. Investigate via `superpowers:systematic-debugging` rather than patching around a failure.

- [ ] **Step 5: Commit**

```bash
git add app/activity/models.py app/portal/service.py tests/test_portal.py
git commit -m "feat: Sprint 014 - log activity event on portal link creation

Every other creation flow (customers/projects/quotes/tenants) logs an
ActivityEvent; portal links didn't. Revoke deliberately does not log,
matching revoke_invitation()'s create-only-logs precedent."
```

---

## Task 2: Verify and commit the frontend portal-link management UI

**Files:**
- Modify (already done, uncommitted): `apps/web/app/customers/[id]/page.tsx`

**Interfaces:**
- Consumes: `api.getPortalLinks(customerId: string): Promise<PortalLinkOut[]>` and `api.revokePortalLink(id: string): Promise<void>` — both already exist in `apps/web/lib/api.ts` since Sprint 013 (unused until this change). `PortalLinkOut` type from `apps/web/types/portal.ts` (already exists). `Badge` component from `apps/web/components/ui/Badge.tsx` with `tone: "success" | "neutral" | "warning"` prop (already exists, unchanged).
- Produces: nothing consumed by a later task — this is a leaf UI change.

- [ ] **Step 1: Confirm the diff**

Run: `git diff "apps/web/app/customers/[id]/page.tsx"`

Expected, in order:
1. New imports: `Badge` from `@/components/ui/Badge`, and `PortalLinkOut` added to the existing `PortalLinkCreateOut` type import from `@/types/portal`.
2. A new `PORTAL_LINK_STATUS_TONE` lookup mapping `"active"→"success"`, `"revoked"→"neutral"`, `"expired"→"warning"`.
3. New component state: `portalLinks` (`PortalLinkOut[] | null`), `linksError` (`string | null`), `revokingId` (`string | null`).
4. A `loadPortalLinks(customerId: string)` function calling `api.getPortalLinks` and setting `portalLinks`/`linksError`.
5. `loadPortalLinks` called once after the customer loads, and again after a new link is created.
6. A `handleRevokePortalLink(id: string)` async function calling `api.revokePortalLink(id)`, then `loadPortalLinks`, with `revokingId` tracking in-flight state.
7. New JSX: an error banner for `linksError`, and — when `portalLinks` is non-empty — a divided list showing created/expires dates, a `Badge` for status, and a "Revoke" `Button` (variant `outline`, size `sm`) shown only when `link.status === "active"`, disabled and reading "Revoking…" while that link's revoke call is in flight.

If the diff is missing any of these seven elements, or introduces something not described in the spec (e.g. a new API call, a new route, a change to an unrelated part of the page), stop and flag it before proceeding.

- [ ] **Step 2: Manually trace the empty/error states**

Read the new JSX block and confirm: the links list only renders `!linksError && portalLinks && portalLinks.length > 0` — i.e. a customer with zero portal links renders neither an error nor an empty list (no "No links yet" placeholder is required by the spec; confirm none was silently added, since that would be undocumented scope creep).

- [ ] **Step 3: Commit**

```bash
git add "apps/web/app/customers/[id]/page.tsx"
git commit -m "feat: Sprint 014 - list and revoke existing portal links from customer page

GET/DELETE /api/v1/portal-links shipped in Sprint 013 with no frontend
consumer. Adds a list under the existing portal-link card: created/expires
dates, a status badge, and a revoke action on active links."
```

---

## Task 3: Full verification pass (frontend checks + migration drift check)

**Files:** none modified — verification only.

**Interfaces:**
- Consumes: Task 1 and Task 2 commits must exist before running this task (verification is meaningless against uncommitted state for a reviewer diffing between tasks).
- Produces: a pass/fail verdict gating Task 4/5. Do not proceed to Task 5 (docs) if any check in this task fails.

- [ ] **Step 1: Frontend lint**

Run (from repo root): `pnpm lint`

Expected: 0 errors, 0 warnings (matches Sprint 013's recorded baseline in `docs/SPRINTS/sprint-013.md`).

- [ ] **Step 2: Frontend type-check**

Run (from repo root): `pnpm check-types`

Expected: clean, no type errors. Pay particular attention to `apps/web/app/customers/[id]/page.tsx` — this is the file this sprint touched.

- [ ] **Step 3: Frontend build**

Run (from repo root): `pnpm build`

Expected: all routes compile, including `/customers/[id]`. No new routes are added this sprint, so the route count should match Sprint 013's baseline.

- [ ] **Step 4: Alembic drift check**

Run: `.venv/Scripts/python.exe -m alembic check`

Expected: no new operations detected — `ActivityLog.type` is a plain `String` column (confirmed in `app/database/models.py` during planning), so the new `ActivityType.PORTAL_LINK_CREATED` Python enum member requires no schema change. If `alembic check` reports drift, stop: that means the column type assumption in the spec was wrong, and the plan needs to be revisited (do not autogenerate a migration without understanding why one appeared).

- [ ] **Step 5: Re-run the backend suite once more**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: `136 passed` (re-confirms Task 1's result now that both commits exist, per spec §12/§17's "re-confirm right before the sprint is called done").

- [ ] **Step 6: Record results (no commit — this feeds Task 5's docs)**

No git action this step. Keep the exact output/pass counts from Steps 1-5 at hand — Task 5 copies them verbatim into `docs/SPRINTS/sprint-014.md`'s audit table, matching `sprint-013.md`'s format.

---

## Task 4: Manual smoke test

**Files:** none modified — manual verification only, run against the live local app.

**Interfaces:**
- Consumes: a running backend (`uvicorn`) and frontend (`pnpm dev`) against the local PostgreSQL instance, per `docs/DATABASE_SCHEMA.md` §"local setup" (`docker compose up -d` then `alembic upgrade head` if not already running).
- Produces: a pass/fail verdict gating Task 5.

- [ ] **Step 1: Start the app**

Use the repo's `run` skill/project launch pattern (or manually: backend `.venv/Scripts/python.exe -m uvicorn app.main:app --reload` from repo root; frontend `pnpm dev` from `apps/web`, or `pnpm dev` from repo root via Turborepo). Confirm both are reachable (backend `http://localhost:8000/docs`, frontend `http://localhost:3000`).

- [ ] **Step 2: Create a portal link and confirm the activity event**

Log in as the seeded owner, open any existing customer's detail page (`/customers/[id]`), click to generate a portal link. Confirm:
- The link is created and displayed (existing Sprint 013 behavior, unchanged).
- The new "existing links" list (Task 2) now shows one entry: today's date as "Created", a date 90 days out as "Expires", and a green/`success`-toned "active" badge.
- Navigate to the dashboard's Recent Activity feed (or `GET /api/v1/activity` via `/docs`). Confirm a new event appears with title "Portal link shared" and description equal to the customer's name.

- [ ] **Step 3: Revoke the link and confirm the list updates**

Click "Revoke" on the link created in Step 2. Confirm:
- The button shows "Revoking…" briefly, then the list re-renders with the badge now showing "revoked" (neutral tone), and the Revoke button no longer present on that row.
- No new activity event was logged for the revoke action (spec §6 — revoke deliberately does not log). Re-check the activity feed and confirm the entry count for `portal_link_created` events for this customer is still exactly 1.

- [ ] **Step 4: Confirm cross-tenant isolation holds visually**

If a second tenant/owner account is available (or create one via signup), log in as that second tenant and confirm: the first tenant's portal link does not appear anywhere in the second tenant's UI (no customer to view it on, since customers are tenant-scoped — this step mainly confirms nothing crashes/leaks if you inspect network responses directly via browser devtools on an unrelated activity fetch).

- [ ] **Step 5: Record the result**

No git action. Note pass/fail for Task 5's docs — this manual pass is what lets `sprint-014.md` claim "verified against the live local app," matching the phrasing every prior sprint doc uses.

---

## Task 5: Write the sprint completion record, changelog entry, and doc touch-ups; commit

**Files:**
- Create: `docs/SPRINTS/sprint-014.md`
- Modify: `docs/CHANGELOG.md`
- Modify (only if content is stale after this sprint): `docs/USER_ROLES.md`
- Modify (only if content is stale after this sprint): `docs/SYSTEM_ARCHITECTURE.md`

**Interfaces:**
- Consumes: the pass/fail results and exact figures recorded in Task 3 (lint/typecheck/build/alembic/pytest) and Task 4 (manual smoke test) — this task's audit table must use those real results, not placeholder checkmarks.
- Produces: nothing consumed by a later task — this is the final task in the plan.

- [ ] **Step 1: Write `docs/SPRINTS/sprint-014.md`**

Follow `docs/SPRINTS/sprint-013.md`'s exact section structure: `# Sprint 014 — <title>`, `**Status:**` line, `## Objective` (use spec §1/§2's reconciliation language — state plainly that the roadmap's "Contracts + Payments" line is stale and this sprint instead closes Sprint 013's two named follow-ups), `## Scope delivered` (Backend / Frontend / Docs subsections, listing the exact changes from Task 1/2), `## Test-suite coverage` (name the 2 new tests and what each asserts), `## Audit results` (a table using Task 3's and Task 4's real recorded results — mirror `sprint-013.md`'s table: `pytest`, `alembic check`, `eslint`, `tsc --noEmit`, `next build`, plus a manual-smoke-test row), and `## Follow-up items raised, not part of Sprint 014 scope` (carry forward: documents/messaging still unstarted; `ROADMAP.md`'s stale table still unreconciled; note that the roadmap's original "Contracts + digital signatures; Payment tracking" line remains entirely unaddressed and unscheduled).

- [ ] **Step 2: Add the `docs/CHANGELOG.md` entry**

Insert a new entry at the top of the file (above the existing `## 2026-08-15 — (uncommitted) — Sprint #013` entry), following that entry's exact format: date, `Sprint #014` title, a `Full detail in` pointer to `sprint-014.md`, then `**Backend**`/`**Frontend**`/`**Tests**` bullet subsections (short — 1-3 lines each, mirroring the density of the Sprint 012/013 entries above), and a `**Verified:**` closing line listing the real Task 3/4 results.

- [ ] **Step 3: Update `docs/USER_ROLES.md` and `docs/SYSTEM_ARCHITECTURE.md` only if needed**

Grep both files for "portal" (`grep -n -i portal docs/USER_ROLES.md docs/SYSTEM_ARCHITECTURE.md`). Their current text describes the portal as read-only tracking with a link-generation UI but does not mention activity logging or a list/revoke UI. Add a short clause to the relevant existing sentence(s) noting that portal link creation now logs an activity event and that the customer page now lists/revokes existing links — do not restructure these files beyond that, and do not touch any unrelated section. If, on inspection, the existing wording is generic enough to already cover this (e.g. it never claimed "no list/revoke UI" as a permanent fact), skip the edit and note in the commit message that no change was needed.

- [ ] **Step 4: Confirm `docs/ROADMAP.md` is untouched**

Run: `git diff docs/ROADMAP.md`

Expected: no output. This file must not be modified (Global Constraints, spec §4/§15).

- [ ] **Step 5: Commit**

```bash
git add docs/SPRINTS/sprint-014.md docs/CHANGELOG.md docs/USER_ROLES.md docs/SYSTEM_ARCHITECTURE.md
git commit -m "docs: Sprint 014 - record portal link activity logging + management UI

Closes the two follow-up items sprint-013.md raised. Roadmap's stale
'Contracts + Payments' Sprint 014 line remains unaddressed and
unscheduled; docs/ROADMAP.md intentionally not touched."
```

(If Step 3 made no changes to `USER_ROLES.md`/`SYSTEM_ARCHITECTURE.md`, drop those two paths from the `git add` — only add files that actually changed.)

---

## Explicit non-goals (carried from spec)

- No Alembic migration is expected or should be generated (Task 3, Step 4 verifies this rather than assuming it).
- No push to any remote — every commit in this plan is local. Pushing requires a separate, explicit user request.
- No work on Sprint 015 or on the roadmap's original Sprint 014 (Contracts/Payments) scope.
- No new ADR.
