# Sprint 001 — Professional Application Shell

**Status:** ✅ Done
**Commit:** `3cf51c8` — "Sprint #001 - Professional Application Shell" (plus follow-up docs/gitignore commits)

## Objective

Build a premium, production-ready application shell for SIMO OS without breaking any existing functionality, and lay it out so future modules plug into the shell instead of requiring it to be rewritten.

## Scope delivered

**Backend — additive only, every existing route left untouched**
- `app/activity/` — new module: `models.py`, `repository.py` (interface + in-memory implementation), `service.py`, `router.py`, `seed.py`. Routes: `GET/POST /activity` (with `limit`/`type` query params).
- `app/notifications/` — same pattern. Routes: `GET/POST /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{notification_id}/read`.
- `app/main.py` — two `include_router` calls and two seed calls added; no existing route body modified.

**Frontend — application shell**
- Collapsible sidebar (desktop) + mobile drawer (`components/layout/Sidebar.tsx`, `SidebarContext.tsx`)
- Topbar with global search trigger, dark mode toggle, notifications bell, user profile menu (`components/layout/Topbar.tsx`)
- Global search / command palette, Cmd/Ctrl+K (`components/shell/CommandPalette.tsx`)
- Notifications dropdown, polls `/notifications` (`components/shell/NotificationsPanel.tsx`)
- User profile menu — auth-gated items disabled with an explanatory tooltip, since auth doesn't exist yet (`components/shell/UserProfileMenu.tsx`)
- Dark mode — class-based via Tailwind v4 `@custom-variant`, persisted to `localStorage`, no flash on load (`components/theme/ThemeProvider.tsx`)
- Responsive layout throughout

**Frontend — dashboard rebuild**
- `StatGrid`/`StatCard` — animated value transitions, polls `/dashboard` every 5s
- `RecentActivityPanel` — polls `/activity`
- `QuickActions` — real navigation to `/quotes/new`, `/customers/new`, `/projects/new`
- `DashboardStatusBar` — loading/error/offline states, offline detected via `navigator.onLine`

**Frontend — new functional pages**
- `/quotes/new` — fully functional, calls the real `POST /quote` pricing engine and displays the calculated breakdown
- `/customers/new`, `/projects/new` — functional forms that log a real `ActivityEvent` (visible on the dashboard within one poll cycle), explicitly badged "not saved as a permanent record yet" since CRM/Projects persistence doesn't exist until Sprint 004/006
- `/quotes`, `/customers`, `/projects` — index pages showing recently logged activity of the matching type, plus a "Coming in Sprint N" state and a CTA to the "new" page
- `/ai-assistant` — calls the existing `POST /process` endpoint, shows the resolved agent and raw response
- `/settings` — honest "coming soon" state (no auth to configure yet)

## Cleanup

Per explicit instruction, nothing was permanently deleted. 14 files archived to `apps/web/_legacy/` (documented in `_legacy/README.md`):
- 3 duplicate empty `Card.tsx` files
- The dead, broken `components/dashboard/Dashboard.tsx` (imported an empty file, was never actually wired into any route)
- 3 empty stub components (`RecentProjects.tsx`, `RecentQuotes.tsx`, `RevenueChart.tsx`)
- 7 files that were accidentally 0-byte files instead of real directories (`ai`, `charts`, `forms`, `navigation`, `notifications`, `shared`, `tables`), which would have blocked creating real folders of the same name

## Audit results

| Check | Result |
|---|---|
| Python imports (`from app.main import app`) | ✅ Clean |
| All 7 original endpoints | ✅ All return 200, unchanged behaviour |
| New endpoints (activity, notifications) | ✅ All return 200 |
| `tsc --noEmit` | ✅ 0 errors |
| ESLint | ✅ 0 errors, 0 warnings (6 real issues found and fixed — see below) |
| `next build` | ✅ Compiles and statically generates all 10 routes with 0 errors (confirmed via a temporary local-font workaround for a sandbox that lacked internet access to Google Fonts — not a code defect) |

### Real issues found and fixed during the audit

`eslint-plugin-react-hooks` (bundled with `eslint-config-next` 16.2.12) caught 6 genuine issues, all fixed:
- A ref mutated during render in `usePolling` — moved into its own effect.
- Two effects in the command palette that reset state reactively — restructured to reset at the point of closing/typing instead.
- Three one-time reads of browser-only APIs (`localStorage`, `matchMedia`, `navigator.onLine`) on mount — legitimate (SSR can't read them), kept with scoped, justified `eslint-disable` comments.

## Not verified

Visual appearance of responsive layout and dark mode was reviewed in code but not screenshotted (no running browser in the build sandbox). Flagged for a manual check when run locally.

## Follow-up items raised, not part of Sprint 001 scope

- 55 generated files (`.pyc`, `.vscode/settings.json`) had been committed to git history before this sprint's `.gitignore` fix — addressed in a separate commit (`d58af5c`), see `docs/CHANGELOG.md`.
- `apps/web/app/smc-home-backup.tsx` and `SMC-OS/smc-home-backup.tsx` are leftover backup files (not routes) — not addressed, still present.
- `packages/ui/` (Turborepo starter boilerplate) remains unused by `apps/web` — flagged as a duplicate "shared UI" system in the original architecture report, not resolved.
