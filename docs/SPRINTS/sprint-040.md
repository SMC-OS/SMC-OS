# Sprint 040 — GeoCore Premium OS Plan 01: Adaptive Workflows + Project 360 Foundation

**Branch:** `sprint-040-adaptive-workflows-project-360`
**Base:** `origin/main` @ `074eb4c5e5d9d4adc4d71c76e9d4e2d7e2f0691c` (Sprint 039 final auth/trial gate, PR #41)
**Alembic head at branch point (verified, not assumed):** `b5c6d7e8f9a0`
**Status:** CODE-COMPLETE — not deployed, not merged

---

## 1. Mission

Replace the single hard-coded, stone-shaped `ProjectStatus` pipeline (ADR-022) with a
versioned, trade-adaptive workflow engine every one of GeoCore's 28 trades gets its
own real stage sequence from, while every project that already exists keeps working
unchanged throughout — and give the project experience a real home, Project 360,
instead of the flat single-column page it has had since Sprint 006.

Authoritative sources, in priority order: the Master Spec
(`2026-09-17-geocore-premium-os-design-v3.md`), Plan 01
(`2026-09-17-geocore-plan-01-adaptive-workflows-project-360.md`), the Implementation
Roadmap (sequencing/context only). Plan 02 and every later roadmap phase are
explicitly out of scope for this sprint.

---

## 2. What was built, task by task

Every task below followed strict TDD (failing test → confirmed RED → minimum
implementation → confirmed GREEN → regression run → commit) and landed as its own
commit on `sprint-040-adaptive-workflows-project-360`.

### Task 1 — Expand the canonical trade catalogue
`app/trades/catalogue.py` gained 15 new `Trade` entries (the existing 13, `"other"`,
and every existing entry's order, all unchanged). Commit `017397f`.

### Task 2 — System workflow template library
New `app/workflows/catalogue.py`: a hand-authored, immutable stage sequence per trade
— stable machine `key`s (never derived from the freely-rewordable `label`), each
stage mapped to one of 13 stable semantic `WorkflowRole` values
(`lead`/`survey`/`quoted`/`approved`/`procurement`/`scheduled`/`in_progress`/
`inspection`/`snagging`/`handover`/`completed`/`on_hold`/`cancelled`). Every sequence
starts at Enquiry (`lead`) and ends at Complete (`completed`); an unknown/absent
trade resolves to a safe `general_v1` fallback, never stone. Commit `8db26bc`.

### Task 3 — Versioned workflow persistence + legacy migration safety
New tables `workflow_templates`/`workflow_stages`/`workflow_transitions`/
`project_workflow_history`, plus `projects.workflow_template_id`/
`workflow_stage_id` (NOT NULL) and `workflow_previous_active_stage_id` (nullable).
One migration, `0f93d11b04a4` (parent `b5c6d7e8f9a0`) — the single new linear
revision the plan's own contract asked for, self-contained (the seed spec is copied
in as plain literals, never imported from `app.workflows.catalogue`, so the
migration stays reproducible after that module changes later).

**The critical part:** an immutable `legacy_v1` template whose 7 real stage keys are,
by construction, exactly the historical `ProjectStatus` values. Every pre-existing
project is bound to it at the stage matching its own `status` string — never
guessed, never reinterpreted — before the two new columns become `NOT NULL`.
`projects.status` itself is untouched by the migration and stays fully live. See
ADR-042 for the full reasoning. Commit `912bf63`.

### Task 4 — Bind new projects and quote handoff to the workflow engine
`app/workflows/service.py`'s `resolve_initial_binding()` — every new project
(including a quote handoff) binds to its own trade's real system template at that
template's first ("Enquiry") stage; an unknown/absent trade falls back to
`general_v1`, never stone. `ProjectOut` gains a nested `workflow`
(`ProjectWorkflowSummary`) field alongside the unchanged legacy `status` field.
Found and fixed along the way: `crud.create_quote` (the stone-only quote creator)
never set `quote.trade`, so a stone quote's handoff was silently producing a
tradeless project even before this plan. Commit `ee9f07e`.

### Task 5 — Transition engine, Hold/Resume/Cancel and workflow history
Three new endpoints (`app/workflows/router.py`): `GET .../workflow`,
`GET .../workflow/history`, `POST .../workflow/transition`. Forward moves, Hold and
Cancel are all the same graph-edge-lookup operation against the project's own bound
template; Resume is the one non-graph-edge move, recognised by comparing the
requested target against `workflow_previous_active_stage_id`. The stage write and
its `ProjectWorkflowHistory` row commit atomically; automation dispatch fires
strictly after that commit. `PATCH /projects/{id}/status` (the legacy endpoint)
keeps working for every project exactly as before — repository discovery found the
entire pre-existing regression suite, the frontend and every E2E journey drive
`status` through it regardless of trade — with one addition: a `legacy_v1`-bound
project also has `workflow_stage_id` moved to the matching stage in the same
transaction, so `status` and `workflow` never drift apart for that one binding
where a 1:1 mapping actually exists. Commit `09c9abe`, with a follow-up fix
(`370aea2`) closing the same symmetry gap in the other direction — the *new*
`POST .../workflow/transition` endpoint also writes `status` for a `legacy_v1`
project moving to a real (non-side) stage, discovered while designing Task 8's
Workflow tab, which needs one endpoint to drive every project regardless of binding.

### Task 6 — Workflow gates
New `app/workflows/gates.py`: five initial stage entry requirements
(`customer_linked`, `assigned_user`, `site_address_present`, `completed_site_visit`,
`approved_source_quote`) as a Pydantic discriminated union validated out of
`WorkflowStage.gate_definitions` (the JSONB column Task 3 already added but left
unused). An unrecognised gate type fails loudly rather than silently admitting an
unenforced one. `GET .../workflow` annotates each allowed move with its own unmet
`GateBlocker`s; a blocked `POST .../workflow/transition` returns one structured 409
(`{"message", "blocked_requirements": [...]}`), never a generic unexplained
conflict. Commit `dcc8987`, with a follow-up (`0783d1d`) upgrading
`blocked_requirements` from bare codes to full `{code, message}` objects, found
while building Task 8's own Workflow tab — the frontend needed the same message
text `gates.py` already owns, not a second, driftable copy of it.

### Task 7 — Platform consumers use semantic roles
`app/database/crud.py`'s `count_projects_by_role` (one grouped aggregate query, same
O(1)-queries contract as its `count_projects_by_status` sibling) backs
`CommandCentreResponse.pipeline_by_role` (`PipelineRoleCounts`, all 13 roles, never
sparse) — additive alongside the unchanged `pipeline`. `project_subject`
(automations) gains `workflow_stage_key`/`workflow_stage_label`/`workflow_role`/
`previous_workflow_role` alongside the unchanged `status`/`previous_status`.
`app/ai/context.py` gains `projects.by_role` and a `recent_projects` list (name +
workflow name + stage label) alongside the unchanged `by_status`/
`recent_project_names` — still names and machine-defined labels only, no new PII.
Commit `d633989`.

### Task 8 — Project 360 frontend
The flat, single-column project page (unchanged since Sprint 006/023/036) is now
Project 360: a persistent header (name, trade, current workflow role + stage — real
data only) plus six tabs — Overview, Workflow, Schedule, Team, Tasks, Timeline. No
placeholder tabs for Financials/Materials/Documents/Variations/Photos — those are
future plans, not stubs shipped early. New components
(`apps/web/components/projects/`): `Project360Shell`, `WorkflowProgress`
(deliberately does not draw a full linear progress bar — no endpoint exposes a
template's complete ordered stage list, and inventing one would be exactly the kind
of fabricated state this plan forbids), `WorkflowBlockers`, `WorkflowHistory`,
`ProjectOverview`. The old "Advance to next status" button is gone, replaced by the
Workflow tab's transition-engine-driven actions for every project, legacy-bound or
not. Commit `7351265`.

### Task 9 — Command Center semantic pipeline
The Business Command Centre's Pipeline card now aggregates by the 13 shared
`WorkflowRole` categories instead of the old 7-value stone-shaped `ProjectStatus`
pipeline — a stone project on "Fabrication" and an electrical one on "First Fix" now
count together under one company-wide "In Progress" row. Commit `aca2083`.

### Task 10 — E2E journeys, full verification, closeout
See §3 and §4 below. Commit `c2f4a6d`, plus this doc and the `docs/DATABASE_SCHEMA.md`
§Sprint 040 / `docs/DECISIONS.md` ADR-042 updates.

---

## 3. E2E coverage

New `apps/web/e2e/trade-workflows.spec.ts` — three journeys nothing else covers:
an Electrical journey (create, move through Electrical's own real sequence, Hold,
Resume, full audit trail verified via the live API); a cross-trade Command Centre
journey (an Electrical project and a Stone project both land on `SURVEY` despite
completely different stage labels, and the Pipeline card counts them together); a
legacy-safety journey (a `legacy_v1`-bound project, seeded directly since there is no
API/UI path that produces one today, renders correctly in Project 360, and the old
`PATCH /status` endpoint keeps its `workflow` view in lockstep on reload).

Task 8's UI changes broke five pre-existing specs purely on selector/flow grounds
(functionality unchanged, UI location changed) — all fixed to open the right tab
first, and, where a spec exercised the removed Advance button, to drive the real
Workflow tab / transition endpoint instead: `project-operations.spec.ts`,
`full-system-journey.spec.ts` (the Stone journey — the handed-off project's full
real `stone_v1` sequence, 11 real moves, now drives through the Workflow tab),
`quote-handoff.spec.ts`, `role-boundary-owner-vs-staff.spec.ts`,
`site-visit-scheduling.spec.ts`.

---

## 4. Full verification (exact counts, this branch, this sandbox)

| Check | Result |
|---|---|
| Backend suite (`pytest tests/ -q`) | **1148 passed, 3 skipped, 0 failed** — run against a real local Postgres (docker unavailable in this sandbox; the existing `pg_ctlcluster`-managed cluster was found stopped after an environment reset mid-sprint and restarted — not a code issue) |
| Frontend unit/component suite (`npx vitest run`) | **193 passed**, 0 failed, 32 test files |
| Frontend typecheck (`tsc --noEmit`) | Clean |
| Frontend lint (`eslint`) | Clean |
| Frontend production build (`next build`) | Succeeds |
| Playwright E2E (`npx playwright test`) | **38 passed**, 0 failed (run with a temporary, never-committed `launchOptions.executablePath` override to work around a Playwright-browser-revision mismatch specific to this sandbox — `playwright.config.ts` itself is unchanged) |
| Alembic | Single clean head `0f93d11b04a4`, no branches, `alembic upgrade head` is a no-op from a fresh checkout at this head |

A stray `NotificationRecord` and three stray `Project`/`Quote`/`Customer` rows were
found in the shared seeded dev tenant during this verification pass — leftovers from
earlier manual/iterative testing during this same sprint (a `far-future`-dated
follow-up notification, and duplicate "Task4 Handoff Customer" rows from an
interrupted test run) — and were deleted directly from the local dev database. Not a
code defect; recorded here for transparency since it briefly broke
`tests/test_messages.py`'s ordering assumption on a shared-tenant row.

---

## 5. Known limitations / explicit scope boundaries

- **No gate-authoring UI.** `WorkflowStage.gate_definitions` is fully enforced
  (Task 6) but nothing seeds a real gate on a system template yet, and there is no
  admin surface to add one. Task 6's own tests set a stage's `gate_definitions`
  directly via the ORM to prove enforcement, restoring it to `NULL` afterwards.
- **No full-template-stage-list endpoint.** The Workflow tab shows a project's
  current stage and its own legal next moves, never a fabricated "all N stages"
  progress bar — a deliberate Task 8 design boundary, not an oversight (see ADR-042).
- **`lifecycle_state` (Master Spec §5.1's separate 6-value coarser field) was not
  built.** Plan 01's own Task 3/7 deliverables never call for it, and
  `PipelineRoleCounts` uses the 13-value `WorkflowRole` vocabulary directly — out of
  this phase's scope, not forgotten.
- **No tenant-owned workflow clones.** `workflow_templates.tenant_id` supports a
  future tenant-customised template; nothing in this plan writes one.
- **This sprint is not deployed.** No Railway deployment, no production database
  change, no merge to `main`.

---

## 6. Security/commercial invariants preserved

Stripe subscription architecture, the card-required 14-day SaaS trial, email
verification, password policy, the billing access gate, tenant isolation and the
current authentication model are all untouched by this sprint — confirmed by the
unmodified backend regression suite for `test_billing.py`, `test_email_verification.py`,
`test_password_reset.py`, `test_rbac_matrix.py` and `test_cross_tenant_boundary.py`-
equivalent coverage passing throughout every task's own verification pass.
