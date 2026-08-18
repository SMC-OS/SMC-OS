# Sprint 017 — Client Portal Messaging

**Status:** Implementation reconciled to the approved design and verified locally. Not committed or pushed; held for user approval.

## Objective

Close the final capability deferred from Sprint 013's client-portal scope. Staff and a customer can now exchange customer-level plain-text messages through the existing portal-link mechanism, with no customer account or login. `docs/ROADMAP.md` remains untouched.

## Scope delivered

**Backend**

- Additive migration `f81683afc3f4` creates `messages`: tenant/customer ownership, sender type, nullable staff `sender_user_id`, body, and creation timestamp.
- New `app/messages/` module exposes authenticated staff POST/GET routes. `customer_id` is required as a query parameter; unknown and cross-tenant customers return 404.
- Existing portal service/router gains public list/post routes. Tenant and customer are derived only from an active token row; unknown, expired, and revoked tokens return 404.
- Threads are customer-level and oldest-first.
- Body policy: plain text, 5,000 characters maximum, empty/whitespace-only input rejected with 422, accepted input stored unchanged.
- Staff-authored messages create no activity or notification. Each inbound customer message creates one `CUSTOMER_MESSAGE_RECEIVED` activity event and one tenant-scoped informational notification.
- No attachments, read state, editing/deleting, rate limiting, WebSockets, or SSE.

**Frontend**

- Customer detail and public portal pages gain message threads and send forms.
- Both surfaces use the existing `usePolling` hook on a five-second interval.
- Message bodies render only through JSX text interpolation with `whitespace-pre-wrap`; no HTML or markdown rendering.
- Shared `MessageOut` TypeScript type includes nullable `sender_user_id`.

**Documentation**

- Approved design and implementation plan copied unchanged into the main working tree.
- ADR-033, changelog, roles, architecture, and API documentation updated.
- `docs/ROADMAP.md` unchanged.

## Test coverage

`tests/test_messages.py` contains 21 Sprint 017 tests covering required query parameters, authenticated sender attribution, 5,000/5,001 boundaries, blank input, tenant isolation and cross-tenant 404 behavior, chronological order, staff no-side-effects, portal customer scoping, customer activity/notification counts, invalid-input no-side-effects, revoked/expired tokens, absence of rate limiting, and plain-text round trips.

## Verification results

| Check | Result |
|---|---|
| Targeted Sprint 017 suite | ✅ 21 passed, 68 warnings |
| Full backend suite | ✅ 178 passed, 277 deprecation warnings, 0 failed |
| Alembic heads/current | ✅ sole head `f81683afc3f4`; database at head |
| Alembic check | ✅ `No new upgrade operations detected.` |
| Alembic downgrade/upgrade | ✅ `f81683afc3f4 → b0bddd0fb66b → f81683afc3f4` |
| Frontend lint | ✅ 2/2 tasks successful, 0 warnings/errors |
| TypeScript | ✅ workspace `check-types` passed; web TypeScript passed inside production build |
| Production build | ✅ Next.js 16.2.12; 14/14 static pages generated, 17 routes, 0 warnings/errors |
| `git diff --check` | ✅ exit 0 (Git emitted line-ending conversion notices only) |
| Security/scope review | ✅ tenant/customer isolation, active-token enforcement, plain-text rendering, and declared non-goals verified; no prohibited feature scope found |

## Remaining warnings

- Existing deprecation warnings remain: `datetime.utcnow()`, Starlette HTTP status aliases, and FastAPI TestClient/httpx compatibility.
- Activity and notification repositories retain their established independent-session commit architecture. The normal success path creates exactly one of each and is covered by tests, but the three writes are not one atomic database transaction if a later repository write fails.
- `sender_type` and its nullable-id relationship are enforced by the application service/API contract rather than a database CHECK constraint, matching the existing repository style.
- No interactive browser smoke test was run during this fast-track verification; lint, TypeScript, production build, API integration tests, migration round-trip, and static UI security inspection all passed.
