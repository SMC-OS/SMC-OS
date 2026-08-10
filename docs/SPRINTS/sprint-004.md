# Sprint 004 — Customers (CRM), Auth Enforcement, Minimal Login UI

**Status:** ✅ Done, pending commit approval. Implemented and verified against the live local PostgreSQL 16 instance and a real headless-browser walkthrough; not yet committed to git.

## Objective

Deliver the roadmap's Sprint 004 item — "CRM: customer list/detail/create, backed by the database" — and, because this is the first sprint to introduce real business data, decide what Sprint 003's deferred auth machinery (ADR-020) should actually protect. Two scope decisions were made explicitly before implementation:

- **Auth is now enforced** on all `/api/v1/customers/*` routes (`Depends(get_current_user)`) — this is exactly the trigger ADR-020 described. Consequence: the frontend needed a way to obtain and hold a token for the first time, so this sprint also includes the minimum login UI required for that — not a full account/settings UX.
- **CRUD scope is list/detail/create only**, matching the roadmap's literal wording. The customer detail page is read-only; update/delete are explicitly future work.

## Scope delivered

**Backend — `app/customers/` (new module)**
- `models.py` — `CustomerCreate`, `CustomerOut`.
- `service.py` — `CustomerService.list_all()/get()/create()`. `create()` also logs a real `ActivityEvent` server-side (`activity_service.log(...)`, reusing the Sprint 001 singleton) — the frontend no longer logs this itself, unlike `/quotes/new`/`/projects/new`, which still do pending their own sprints.
- `router.py` — `GET/POST /customers`, `GET /customers/{id}`, all three gated by `Depends(get_current_user)` — **the first auth-enforced routes in the project** (ADR-021).
- `app/database/crud.py` — `create_customer`, `get_customer_by_id`, `list_customers` added, matching the existing helper style.
- `app/api/v1/__init__.py` — mounts the new `customers_router`.
- No migration — the `customers` table has existed since Sprint 002 with no API surface until now; its existing columns (`id`, `tenant_id`, `name`, `email`, `phone`, `created_at`) already cover list/detail/create.

**Frontend — real login, for the first time**
- `lib/auth-storage.ts` — plain localStorage wrapper (`getToken`/`setToken`/`clearToken`), outside React so `lib/api.ts` can use it directly.
- `components/auth/AuthProvider.tsx` — context mirroring `ThemeProvider`'s shape (`{ isAuthenticated, isReady, login, logout }`). `isReady` exists specifically to avoid a real race: child page effects fire before a parent provider's own mount effect on first render, so a page checking `isAuthenticated` alone would incorrectly redirect an already-logged-in user to `/login` for one render before the provider caught up. Pages wait for `isReady` before deciding.
- `lib/api.ts` — `request()` now attaches `Authorization: Bearer <token>` from storage on every call (harmless on the still-public routes), and clears the token on a `401` response so the next page-level check sees "logged out."
- New `app/login/page.tsx` — minimal email/password form, redirects to `/customers` on success.
- `app/customers/page.tsx` — replaced the activity-feed (`ModuleIndexPage`) pattern with a real list from `GET /api/v1/customers`; redirects to `/login` if not authenticated.
- New `app/customers/[id]/page.tsx` — read-only detail view.
- `app/customers/new/page.tsx` — now calls `POST /api/v1/customers` and redirects to the new customer's detail page, instead of only logging an activity event.
- `components/shell/UserProfileMenu.tsx` — Sign out is now real (clears the token, redirects to `/login`). Profile/Settings remain disabled — nothing new to show/configure for either yet. Stale "Sprint 003" tooltip text updated.
- `app/settings/page.tsx` — stale "Sprint 003" reference corrected.
- New `types/auth.ts`, `types/customer.ts` — hand-mirrored from the backend pydantic models, per project convention.

## Explicitly out of scope for this sprint (by decision, not oversight)

- **No other route requires auth.** `/api/v1/quote`, `/api/v1/activity`, `/api/v1/notifications`, `/api/v1/process`, `/api/v1/dashboard` all remain fully public — enforcement was applied surgically to `customers`, the one module that triggered ADR-020's condition, not broadly.
- **No customer update/delete.** List/detail/create only, per the confirmed scope decision.
- **No full account/settings UX.** Login exists; Profile and Settings pages are unchanged placeholders.
- **No Next.js middleware/SSR-level route protection.** Guarding is a client-side check-on-mount redirect — proportionate to an internal tool with one seeded user today.

## Audit results

| Check | Result |
|---|---|
| `pytest` (23 tests: 16 existing + 7 new in `test_customers.py`) | ✅ All passing against the real local Postgres |
| `401` on all 3 customer routes without a token | ✅ Confirmed by `test_customers_routes_require_auth` |
| `404` on an unknown customer id | ✅ Confirmed by `test_get_unknown_customer_returns_404` |
| Customer creation logs a matching `ActivityEvent` | ✅ Confirmed by `test_create_customer_logs_activity` |
| Test fixtures clean up after themselves | ✅ `customers` table back to 0 rows, `users` back to 1 (seeded owner) after the suite runs |
| `tsc --noEmit` | ✅ 0 errors |
| `eslint .` | ✅ 0 errors, 0 warnings |
| `next build` | ✅ All 13 routes compile, including new `/login` and dynamic `/customers/[id]` |
| Real browser walkthrough (Playwright, used as transient dev tooling only — not added to `package.json`) | ✅ All 7 steps passed: logged-out `/customers` → `/login` redirect; login succeeds; empty list renders; creating a customer redirects to its detail page showing the entered data; the customer appears in the list; Sign out redirects to `/login`; `/customers` redirects to `/login` again post-logout. No console errors. Test data (2 QA customers + their activity rows) cleaned up from the database afterward; the dev server was stopped. |

## Follow-up items raised, not part of Sprint 004 scope

- Customer update/delete — natural follow-up once there's a concrete need.
- Full account/settings UX (Profile, real Settings) — still unbuilt.
- Whether Sprint 005 (Material Library) or Sprint 006 (Quotes/Projects persistence) should also enforce auth is a case-by-case call for those sprints, not an automatic rule set by this one.
