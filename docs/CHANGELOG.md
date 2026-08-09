# SIMO OS — Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/). Derived from `git log` on the `SMC-OS` repository. Dates are commit dates, not necessarily when work started.

---

## 2026-08-09 — `d01f07e` — docs: add example environment configuration

Added `apps/web/.env.local.example` (template for `NEXT_PUBLIC_API_URL`) after fixing the `.gitignore` pattern that had been silently excluding it.

## 2026-08-09 — `d58af5c` — chore: improve .gitignore and remove generated files from version control

- Rewrote the root `.gitignore` to add Python coverage (`__pycache__/`, `*.py[cod]`, `.venv/`, the stray `SIMO-OS.VENVA` folder, `quote.pdf`), editor/OS coverage (`.vscode/`, `.idea/`, `.DS_Store`, etc.), and expanded log/build-artifact patterns.
- Fixed `apps/web/.gitignore`'s `.env*` pattern with `!.env.*.example` negation so template env files can be tracked.
- Untracked (not deleted from disk) 54 already-committed `.pyc`/`__pycache__` files and `.vscode/settings.json`, which had been swept into the Sprint 001 commit before the backend had any Python-specific `.gitignore` rules.

## 2026-08-09 — `2e2f284` — docs: add SYSTEM_ARCHITECTURE

Added the canonical `SYSTEM_ARCHITECTURE.md` reference: folder structure, backend/frontend module map, full route table, API flow diagrams, design principles, coding standards, and the Sprint 002–016 roadmap.

## 2026-08-09 — `3cf51c8` — Sprint #001 - Professional Application Shell

The largest commit to date. Summary (full detail in `docs/SPRINTS/sprint-001.md`):

**Backend (additive only — no existing route changed)**
- New `app/activity/` module: repository-backed Recent Activity feed (`GET/POST /activity`, in-memory, seeded with sample events).
- New `app/notifications/` module: notification centre (`GET/POST /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{notification_id}/read`, in-memory, seeded).
- `app/main.py`: two `include_router` calls added plus seed calls — no existing route body touched.

**Frontend**
- Full application shell: collapsible sidebar with mobile drawer, topbar, global search (Cmd/Ctrl+K command palette), notifications dropdown, user profile menu, dark mode (class-based, persisted, no flash on load).
- Dashboard rebuilt from reusable components (`StatGrid`/`StatCard` with animated transitions, `RecentActivityPanel`, `QuickActions`, `DashboardStatusBar` for loading/error/offline), all polling every 5 seconds.
- New functional pages: `/quotes/new` (calls the real `POST /quote` engine), `/customers/new` and `/projects/new` (log real activity events, honestly badged as not yet persisted), `/ai-assistant` (calls `POST /process`), plus index pages for Quotes/Customers/Projects and a "coming soon" `/settings`.
- 14 obsolete files (3 duplicate empty `Card.tsx` components, the dead/broken `Dashboard.tsx`, empty stub components, and 7 files that were accidentally blocking real folder names) archived to `apps/web/_legacy/`, not deleted.

**Verification:** `tsc --noEmit` clean, `eslint` clean (6 real issues found and fixed), `next build` succeeds, all original and new backend routes smoke-tested.

## 2026-07-28 — `f812e56` — Initial commit from create-turbo

The starting point: a stock `create-turbo` scaffold (`apps/web`, `apps/docs`, `packages/ui`, `packages/eslint-config`, `packages/typescript-config`). The Python backend (`app/`) was not part of this commit — it was added to the working tree later, outside version control, and only entered git history via the Sprint 001 commit above.

---

*Add a new entry above this line at the top of the next section whenever a sprint or notable change lands. Keep the git commit hash so this stays traceable back to `git log`.*
