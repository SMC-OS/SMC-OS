# SIMO OS — Roadmap

Estimates are in developer-days (relative sizing, assuming AI-assisted development at the pace demonstrated in Sprint 001), not a fixed-price quote. **P0** = blocking/sequenced · **P1** = important, order flexible · **P2** = valuable, can slip a sprint. Full architecture context behind these decisions lives in `docs/DECISIONS.md`.

---

## v0.1 — Foundation & Stabilise

| Sprint | Feature | Priority | Status |
|---|---|---|---|
| **001** | Application shell (sidebar, topbar, search, notifications, dark mode), dashboard rebuild, Recent Activity + Notifications backend (in-memory) | P0 | ✅ **Done** — see `docs/SPRINTS/sprint-001.md` |
| **002** | Database foundation: PostgreSQL + SQLAlchemy 2.0 + Alembic; core models (`Customer`, `Quote`, `Project`, `Material`, `User`, `ActivityLog`, `Notification`); swap the in-memory activity/notification repositories for Postgres-backed ones | P0 | ✅ **Done** (pending commit approval) — see `docs/SPRINTS/sprint-002.md` |
| **003** | API restructuring (`/api/v1`, `core/config.py` via pydantic-settings, `.env`); error handling middleware; basic JWT auth; `pytest` + CI | P0 | ✅ **Done** — see `docs/SPRINTS/sprint-003.md` |

## v0.2 — Core Business Operations

| Sprint | Feature | Priority | Status |
|---|---|---|---|
| **004** | CRM: customer list/detail/create, backed by the database | P0 | ⬜ Not started |
| **005** | Full Material Library + accurate slab-yield calculator (replaces the placeholder in `quotes/slab_calculator.py`) | P0 | ⬜ Not started |
| **006** | AI Quotation Generator v1 (LLM-assisted text→quote); Projects module job pipeline | P1 | ⬜ Not started |
| **007** | Invoice generator (proper PDF, VAT breakdown, downloadable); dashboard polish (Recent Activity reflects real DB events) | P1 | ⬜ Not started |

## v0.3 — AI Workforce & Automation

| Sprint | Feature | Priority | Status |
|---|---|---|---|
| **008** | Real AI Router — replaces `brain/router.py`'s keyword dict with LLM/embeddings-based intent classification | P0 | ⬜ Not started |
| **009** | Implement the 9 stub assistants (customer service, marketing, SEO, scheduling, finance, purchasing, construction, social, executive) | P1 | ⬜ Not started |
| **010** | AI Sales Assistant + AI Customer Support (chat-based, grounded in CRM/material data) | P1 | ⬜ Not started |
| **011** | Appointment booking + calendar integration; marketing dashboard + social scheduler; automation; Analytics v1 | P2 | ⬜ Not started |

## v1.0 — Production SaaS Platform

| Sprint | Feature | Priority | Status |
|---|---|---|---|
| **012** | Multi-tenant architecture refactor | P0 | ⬜ Not started |
| **013** | Client Portal (project tracking, documents, messaging) | P1 | ⬜ Not started |
| **014** | Contracts + digital signatures; Payment tracking (Stripe/GoCardless) | P1 | ⬜ Not started |
| **015** | Staff management + RBAC; Supplier database + purchasing workflow | P2 | ⬜ Not started |
| **016** | AI Renovation Planner / Design Assistant / Stone Visualiser; full observability; security hardening; subscription billing | P2 | ⬜ Not started — highest R&D risk in the roadmap |

---

**Total remaining estimate (Sprint 002–016):** roughly 60 developer-days from the original planning pass. Treat as a baseline, not a deadline — re-baseline this document at the end of any sprint that runs meaningfully over or under.

This roadmap should be updated whenever a sprint completes: move its row's Status to ✅ Done and link its `docs/SPRINTS/sprint-NNN.md` record, the same way Sprint 001 is linked above.
