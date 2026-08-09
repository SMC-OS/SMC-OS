# Legacy / Archived Files — Sprint 001

These files were retired during Sprint 001 (application shell rebuild) but **not deleted**, per instruction. They are fully recoverable — just move them back to their original path under `apps/web/` if needed.

**Do not permanently delete anything in this folder without explicit approval.** The plan is to remove it once Sprint 001 has been tested and approved.

## Retired files and why

| File | Original path | Why it's obsolete |
|---|---|---|
| `components/Card.tsx` | `apps/web/components/Card.tsx` | 0 bytes, empty. Never imported anywhere. Superseded by the new `components/ui/Card.tsx`. |
| `components/ui/Card.tsx` | `apps/web/components/ui/Card.tsx` | 0 bytes, empty. Replaced by a real, implemented `Card` component in Sprint 001. |
| `components/dashboard/Card.tsx` | `apps/web/components/dashboard/Card.tsx` | 0 bytes, empty. Third duplicate of the same component name. |
| `components/dashboard/Dashboard.tsx` | `apps/web/components/dashboard/Dashboard.tsx` | Dead code — not imported by any route (`app/page.tsx` had its own hand-rolled dashboard instead). Also broken: it imported `ui/Card.tsx`, which was empty, so rendering it would have thrown. Replaced by the new dashboard built from the Sprint 001 component set. |
| `components/dashboard/RecentProjects.tsx` | `apps/web/components/dashboard/RecentProjects.tsx` | 0 bytes, empty stub. Not part of Sprint 001 (Recent Activity panel covers this need for now; a dedicated Projects list comes with the Projects module in a later sprint). |
| `components/dashboard/RecentQuotes.tsx` | `apps/web/components/dashboard/RecentQuotes.tsx` | 0 bytes, empty stub. Same reasoning as above. |
| `components/dashboard/RevenueChart.tsx` | `apps/web/components/dashboard/RevenueChart.tsx` | 0 bytes, empty stub. Charting is out of scope for Sprint 001 (application shell); revisit in a later sprint once real revenue data exists. |
| `components/phantom-folders/{ai,charts,forms,navigation,notifications,shared,tables}` | `apps/web/components/{ai,charts,forms,navigation,notifications,shared,tables}` | These were **not folders** — each was accidentally created as a single 0-byte file (likely `touch` used instead of `mkdir`). Left in place, they would have blocked creating real directories of the same name. Sprint 001 needs real `components/navigation/` and `components/notifications/` directories, so these had to move. No content was lost — each file was empty. |

## What replaced them

- `components/ui/` now holds real, reusable components (Card, Button, etc. as built out).
- `components/navigation/` and `components/notifications/` are now real directories holding the new Sidebar/Topbar-adjacent and NotificationsPanel pieces.
- The dashboard is rebuilt from `components/dashboard/*` (StatCard, StatGrid, RecentActivityPanel, QuickActions) plus the new shell in `components/layout/` and `components/shell/`.
