# SIMO OS — Roadmap

**P0** = blocking/sequenced · **P1** = important, order flexible · **P2** = valuable, can slip a sprint. Full architecture context behind these decisions lives in `docs/DECISIONS.md`.

**Reconciliation note (Sprint 022 planning):** this document stopped being updated after Sprint 007, even though development continued through Sprint 021 — its original v0.3/v1.0 tables described an AI-Workforce-first sequence that was never followed; what actually shipped from Sprint 008 onward was a SaaS-transformation-first sequence (tenants → auth → RBAC → invitations → isolation → client portal → hardening → staging → quote approval/handoff → enquiry conversion). Every one of those sprints' own completion records flagged this exact drift and explicitly deferred fixing it. This revision reconciles the document with `docs/SPRINTS/008.md`–`021.md` (the historical source of truth) and locks the sequence from Sprint 022 onward. See the maintenance rule at the bottom so this doesn't happen again.

---

## v0.1 — Foundation & Stabilise

| Sprint | Feature | Priority | Status |
|---|---|---|---|
| **001** | Application shell (sidebar, topbar, search, notifications, dark mode), dashboard rebuild, Recent Activity + Notifications backend (in-memory) | P0 | ✅ **Done** — see `docs/SPRINTS/sprint-001.md` |
| **002** | Database foundation: PostgreSQL + SQLAlchemy 2.0 + Alembic; core models (`Customer`, `Quote`, `Project`, `Material`, `User`, `ActivityLog`, `Notification`); swap the in-memory activity/notification repositories for Postgres-backed ones | P0 | ✅ **Done** — see `docs/SPRINTS/sprint-002.md` |
| **003** | API restructuring (`/api/v1`, `core/config.py` via pydantic-settings, `.env`); error handling middleware; basic JWT auth; `pytest` + CI | P0 | ✅ **Done** — see `docs/SPRINTS/sprint-003.md` |

## v0.2 — Core Business Operations

| Sprint | Feature | Priority | Status |
|---|---|---|---|
| **004** | CRM: customer list/detail/create, backed by the database | P0 | ✅ **Done** — see `docs/SPRINTS/sprint-004.md` |
| **005** | Full Material Library + accurate slab-yield calculator (replaces the placeholder in `quotes/slab_calculator.py`) | P0 | ✅ **Done** — see `docs/SPRINTS/sprint-005.md` |
| **006** | Projects module: job pipeline (enquiry → quoted → booked → templated → fabricated → installed → complete), backed by the database, second auth-enforced module | P1 | ✅ **Done** — see `docs/SPRINTS/sprint-006.md` |
| **TBD** | AI Quotation Generator v1 (LLM-assisted text→quote via the already-installed OpenAI SDK) — **split out of Sprint 006**, still not scheduled: no `OPENAI_API_KEY` configured anywhere in this project, and real usage costs money per request, so it needs a deliberate go-ahead rather than bundling it in silently | P1 | ⬜ Not started |
| **007** | Invoice generator (proper PDF, VAT breakdown, downloadable); dashboard polish (Recent Activity reflects real DB events) | P1 | ✅ **Done** — see `docs/SPRINTS/sprint-007.md` |

## v0.3 — SaaS Transformation (delivered, Sprints 008–021)

This phase replaced the original v0.3/v1.0 tables' AI-Workforce-first plan with a SaaS-foundation-first one. Every row below is fully shipped, tested, and — from Sprint 020 onward — verified with a true browser E2E and a real staging deployment before merge.

| Sprint | Feature | Status |
|---|---|---|
| **008** | Tenants & workspace model — `Tenant` table, FK plumbing on all 7 tenant-owned tables (schema only, zero enforcement) | ✅ **Done** — see `docs/SPRINTS/sprint-008.md` |
| **009** | Tenant-aware authentication — `POST /auth/signup`, tenant-scoped JWT, `users.tenant_id` becomes `NOT NULL` | ✅ **Done** — see `docs/SPRINTS/sprint-009.md` |
| **010** | Roles & permissions machinery — `UserRole` enum, `require_role()` (shipped inert, zero routes attached) | ✅ **Done** — see `docs/SPRINTS/sprint-010.md` |
| **011** | Staff invitations — first real `Staff` user, first route anywhere gated by `require_role()` | ✅ **Done** — see `docs/SPRINTS/sprint-011.md` |
| **012** | Tenant data isolation enforcement — every business-data query filtered by `tenant_id`; closed two pre-existing cross-tenant leaks found during the sprint | ✅ **Done** — see `docs/SPRINTS/sprint-012.md` |
| **013** | Read-only client portal — customer views their own project/quote status + downloads an invoice via a token link, no login | ✅ **Done** — see `docs/SPRINTS/sprint-013.md` |
| **014** | Portal link activity logging + a management UI (list/revoke) for existing links | ✅ **Done** — see `docs/SPRINTS/sprint-014.md` |
| **015** | Team management — Owner views the team and deactivates a Staff member's access | ✅ **Done** — see `docs/SPRINTS/sprint-015.md` |
| **016** | Client portal documents — staff upload, customer downloads via their existing portal link | ✅ **Done** — see `docs/SPRINTS/sprint-016.md` |
| **017** | Client portal messaging — staff ⇄ customer plain-text threads over the portal link | ✅ **Done** — see `docs/SPRINTS/sprint-017.md` |
| **018** | Production runtime hardening — explicit runtime modes, non-root container, structured/redacted logging, `/health` + `/ready` | ✅ **Done** — see `docs/SPRINTS/sprint-018.md` |
| **019** | Railway unified staging — separate web/API services, private Postgres, persistent uploads, recovery design | ✅ **Done** — see `docs/SPRINTS/sprint-019.md` |
| **020** | Quote approval + Quote→Project handoff — first true browser E2E, first real staging deployment/verification | ✅ **Done** — see `docs/SPRINTS/sprint-020.md` |
| **021** | Enquiry → Customer conversion — atomic transaction, true E2E, staging-verified, merged to `main` (`3b5e864`) | ✅ **CLOSED** — see `docs/SPRINTS/sprint-021.md` |

## Deferred — AI Workforce & Commerce (not scheduled)

These were the original v0.3/v1.0 line items. None have shipped and none are scheduled under a sprint number yet — kept here explicitly so they aren't mistaken for abandoned, only deferred:

- Real AI Router (replacing `brain/router.py`'s keyword dict with LLM/embeddings-based intent classification)
- The 9 stub AI assistants (customer service, marketing, SEO, scheduling, finance, purchasing, construction, social, executive)
- AI Sales Assistant + AI Customer Support (chat-based, grounded in CRM/material data)
- Marketing dashboard + social scheduler, Analytics v1
- Contracts + digital signatures; payment tracking (Stripe/GoCardless)
- Supplier database + purchasing workflow
- AI Renovation Planner / Design Assistant / Stone Visualiser (vision + rendering)
- Subscription billing

## v1.0 — Product Vertical Completion & Launch (Sprint 022–030, locked)

The vertical the product was always meant to complete: **Enquiry → Customer → Appointment/Site Visit → Quote → Approval → Project → Project Operations → Client Portal → Notifications/Follow-up → Business Command Centre → Hardening → UAT → Release Candidate → Production Launch.** Enquiry, Customer, Quote, Approval, Project, and Client Portal are already done (above); the sequence below closes the rest, in order, ending at production launch.

| Sprint | Feature | Status |
|---|---|---|
| **022** | Appointment / Site Visit Scheduling | ⬜ Not started — next up |
| **023** | Project Operations | ⬜ Not started |
| **024** | Notifications / Follow-up Automation | ⬜ Not started |
| **025** | Business Command Centre | ⬜ Not started |
| **026** | Security & Production Hardening II | ⬜ Not started |
| **027** | Full-System E2E / UAT Preparation | ⬜ Not started |
| **028** | UAT + Bug-Fix Cycle | ⬜ Not started |
| **029** | Release Candidate + Rollback/Recovery Drill | ⬜ Not started |
| **030** | **Production Launch** 🚀 | ⬜ Not started — **the planned core production-launch milestone** |

**Sprint 030 is the planned production-launch milestone.** No Sprint 031+ scope is defined — re-baseline this document once Sprint 030 is reached, not before.

---

## Roadmap maintenance rule

- `docs/ROADMAP.md` is the **canonical source for the future sprint sequence** — what's coming next and in what order.
- `docs/SPRINTS/sprint-NNN.md` files are the **authoritative historical execution record** — what was actually built, tested, and shipped, sprint by sprint.
- When a sprint closes, this file must be updated in that same closeout, or in an immediately-following docs-only change — never left to drift. This document going eight sprint-numbers stale (Sprint 007 → 021) before anyone caught it is exactly the failure mode this rule exists to prevent.
