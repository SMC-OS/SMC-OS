# GeoCore

The AI operating system for stone and construction businesses — quoting, projects, scheduling and client communication in one multi-tenant workspace.

GeoCore is the **platform**. Each business that uses it is a **tenant**, with its own data, team and company identity on every customer-facing document. Simo Marble & Construction Ltd is one such tenant, not the platform itself (see `docs/DECISIONS.md` ADR-036).

## Repository layout

| Path | What it is | Deployed as |
|---|---|---|
| `app/` | FastAPI backend — quotes, projects, CRM, portal, billing, auth | `api.geocore.one` |
| `apps/web/` | Next.js application — the authenticated product | `app.geocore.one` |
| `apps/marketing/` | Next.js public site | `geocore.one` |
| `packages/` | Shared ESLint / TypeScript config and UI stubs | — |
| `alembic/` | Database migrations | — |
| `docs/` | Architecture, decisions, runbooks, sprint records | — |

The public site is a separate application on purpose: the apex must be a fast, fully indexable marketing surface, and `apps/web`'s root route is the authenticated dashboard (ADR-038).

## Getting started

Requires Python 3.12, Node 22, pnpm 9, and PostgreSQL 16.

```sh
# Backend
cp .env.example .env
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (from the repository root)
pnpm install
pnpm dev
```

`docker-compose.yml` provides a local PostgreSQL matching `.env.example`.

## Tests

```sh
pytest                              # backend
pnpm --filter web test              # application component tests
pnpm --filter web test:robots       # application stays out of the search index
pnpm --filter marketing test:indexability   # public site ships indexable
pnpm lint && pnpm check-types && pnpm build
pnpm --filter web test:e2e          # Playwright, needs a running API
```

CI runs all of the above on every push and pull request (`.github/workflows/ci.yml`).

## Documentation

| Document | Purpose |
|---|---|
| `docs/SYSTEM_ARCHITECTURE.md` | How the halves fit together |
| `docs/DECISIONS.md` | Architecture decision records — **read before changing anything structural** |
| `docs/API_SPEC.md` | Route contracts |
| `docs/DATABASE_SCHEMA.md` | Schema and tenancy model |
| `docs/ROADMAP.md` | Canonical future sprint sequence |
| `docs/SPRINTS/` | Authoritative historical execution record |
| `docs/PRODUCTION_RUNBOOK.md` | Release, rollback and operations |
| `docs/STAGING_RUNBOOK.md` | Railway staging |
| `docs/DNS_GEOCORE_ONE.md` | Production domain change sheet |

## A note on `simo-os` identifiers

Three internal identifiers deliberately keep their pre-rebrand names: the production upload mount `/var/lib/simo-os/uploads`, the logger name `simo_os`, and the database name. Renaming them would orphan uploaded documents, break log-based alerting, and require a downtime migration respectively — all for zero customer-visible benefit. This is a recorded decision (ADR-037), not an oversight.
