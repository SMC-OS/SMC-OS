# SIMO OS — API Specification

**Status:** Reflects the actual FastAPI application as of Sprint 012 (`app/main.py` + `app/api/v1/` + `app/auth/` + `app/customers/` + `app/projects/` + `app/quotes/` + `app/tenants/` + `app/invitations/` + `app/activity/` + `app/notifications/`). Sprint 003 moved every route except `/` and `/health` under `/api/v1` (clean cutover) and added JWT login/`/me`. Sprint 004 added the first auth-enforced module (`customers`); Sprint 006 added the second (`projects`); Sprint 007 added the third (`quotes`) and, for the first time, actually persisted a calculated quote; Sprint 008 added `tenants` — schema/CRUD only, not yet tied to authentication; Sprint 009 made authentication itself tenant-aware — every user belongs to a tenant, the JWT carries `tenant_id`, and `POST /api/v1/auth/signup` creates a new company workspace (see ADR-026). Sprint 010 formalized `role` as a real enum (`UserRole`) and added a `require_role()` permission dependency (ADR-027) — machinery only, not attached to any route. Sprint 011 adds `invitations` (ADR-028): an Owner can invite a Staff teammate by email, and `require_role(UserRole.OWNER)` is attached to a route for the first time. **Sprint 012 (ADR-029) enforces tenant data isolation across every business-data module** — `customers`, `projects`, `quotes`, `activity`, `notifications`, and `dashboard` now filter every query by the caller's `tenant_id`; `activity` and `notifications` gained auth for the first time (previously fully public); `tenants` list/detail now return only the caller's own tenant (previously leaked every tenant in the system). `materials` stays a shared, unfiltered reference catalogue by design.
**Base URL (local dev):** `http://127.0.0.1:8000`
**Versioning:** `/api/v1` prefix on every route except `GET /` and `GET /health`, which stay unversioned as infra/health-check endpoints. Implemented Sprint 003 (ADR-012).
**Authentication:** JWT bearer tokens (`POST /api/v1/auth/login`, `POST /api/v1/auth/signup`, `GET /api/v1/auth/me`) since Sprint 003 (signup added Sprint 009). Every token carries a `tenant_id` claim since Sprint 009 (ADR-026) — a token issued before that sprint is rejected (`401`), not silently accepted. Sprint 003 itself required no route to present a token (ADR-020); `/api/v1/customers/*` (Sprint 004, ADR-021), `/api/v1/projects/*` (Sprint 006, ADR-022), `/api/v1/quotes/*` (Sprint 007, ADR-023), `/api/v1/tenants/*` (Sprint 008), and — since Sprint 012 (ADR-029) — `/api/v1/activity*`, `/api/v1/notifications*`, and `GET /api/v1/dashboard` all enforce it. `POST /api/v1/quote` and `POST /api/v1/estimate` deliberately stay public (ADR-023); since Sprint 012, a valid token optionally tags the created quote with the caller's tenant via `get_current_user_optional` — called with no token, the quote is still created, just tenant-less.
**CORS:** `allow_origins=["*"]`, all methods and headers allowed (`app/main.py`) — acceptable for local development only; must be restricted before any non-local deployment.

---

## Infra routes (unversioned, `app/main.py`)

### `GET /`

Welcome message. No parameters.

```json
{
  "message": "Welcome to Simo OS",
  "status": "running"
}
```

### `GET /health`

Static health check — does **not** check a database connection.

```json
{ "status": "healthy" }
```

---

## Auth routes (`app/auth/router.py`) — added Sprint 003, tenant-aware since Sprint 009

`role` on `UserOut` (below) is validated against `UserRole` since Sprint 010 (`"Owner"` or `"Staff"`) — same JSON shape as before, just constrained server-side now. `/api/v1/invitations*` is the only place `role` is checked (Sprint 011, ADR-028); see the Invitation routes section below.

### `POST /api/v1/auth/signup` — added Sprint 009

Creates a brand-new company workspace (`Tenant`) and its first user (`role="Owner"`), then signs them in — same response shape as `/login`. Email availability is checked before any row is written, so a duplicate email never leaves an orphaned tenant.

**Request body** (`SignupRequest`)
```json
{ "company_name": "Acme Stoneworks", "name": "Jane Doe", "email": "jane@acmestoneworks.com", "password": "..." }
```

**Response (201)** (`TokenResponse`) — same shape as `/login`, see below.
**Response (409):** `{ "detail": "Email already registered" }`

### `POST /api/v1/auth/login`

**Request body** (`LoginRequest`)
```json
{ "email": "owner@simo-os.local", "password": "..." }
```

**Response (200)** (`TokenResponse`)
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "...", "name": "Simo", "email": "owner@simo-os.local", "role": "Owner",
    "tenant_id": "...", "tenant_name": "Default Workspace"
  }
}
```

`access_token`'s JWT payload is `{"sub": "<user id>", "tenant_id": "<tenant id>", "exp": ...}` since Sprint 009 (ADR-026) — previously just `{"sub": ..., "exp": ...}`.

**Response (401):** `{ "detail": "Incorrect email or password" }`

### `GET /api/v1/auth/me`

`Authorization: Bearer <token>` header required.

**Response (200)** (`UserOut`): `{ "id": "...", "name": "...", "email": "...", "role": "...", "tenant_id": "...", "tenant_name": "..." }`
**Response (401):** `{ "detail": "Could not validate credentials" }` — missing, malformed, expired token, **or a token missing the `tenant_id` claim** (i.e. any token issued before Sprint 009 — a clean cutover, not a dual-mode shim).

One owner account is seeded on startup (`app/auth/seed.py`) if the `users` table is empty, from `.env`'s `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD` — never hardcoded credentials. Since Sprint 009 this goes through the same `AuthService.signup()` path as a real signup, giving the seeded owner a real "Default Workspace" tenant instead of special-cased logic.

---

## Customer routes (`app/customers/router.py`) — added Sprint 004

**All three routes require `Authorization: Bearer <token>`** — the first auth-enforced module (ADR-021). `401` (`{"detail": "Could not validate credentials"}`) without a valid token. **Tenant-scoped since Sprint 012 (ADR-029):** every query filters by the caller's own `tenant_id` — a customer created by one tenant is invisible to every other tenant's list, and a cross-tenant `{customer_id}` 404s identically to an unknown one.

### `GET /api/v1/customers`

| Query param | Type | Default |
|---|---|---|
| `limit` | integer | `20` |

**Response** — array of `Customer`, most recent first:
```json
[{ "id": "...", "name": "James Okafor", "email": "james@example.com", "phone": "07123456789", "created_at": "2026-08-11T10:00:00Z" }]
```

### `GET /api/v1/customers/{customer_id}`

**Response (200):** a single `Customer` (same shape as above).
**Response (404):** `{ "detail": "Customer not found" }` — also returned (not `403`) for a customer belonging to a different tenant (ADR-029).

### `POST /api/v1/customers`

**Request body** (`CustomerCreate`): `{ "name": "string", "email": "string | null", "phone": "string | null" }`

**Response (201):** the created `Customer`. Also logs a real `ActivityEvent` (`customer_added`) server-side — the frontend no longer logs this itself. (As of Sprint 007, `/quotes/new` follows the same pattern too — see the Quote routes section below.)

---

## Project routes (`app/projects/router.py`) — added Sprint 006

**All four routes require `Authorization: Bearer <token>`** — the second auth-enforced module (same reasoning as customers, ADR-021/ADR-022). **Tenant-scoped since Sprint 012 (ADR-029):** every query filters by the caller's own `tenant_id`, including the status-update write path — previously any authenticated user of any tenant could advance any other tenant's project by guessing/knowing its id.

### `GET /api/v1/projects`

| Query param | Type | Default |
|---|---|---|
| `limit` | integer | `20` |

**Response** — array of `Project`, most recent first:
```json
[{ "id": "...", "name": "Riverside Kitchen Renovation", "customer_id": "...", "notes": null, "status": "enquiry", "created_at": "2026-08-11T10:00:00Z" }]
```

### `GET /api/v1/projects/{project_id}`

**Response (200):** a single `Project`.
**Response (404):** `{ "detail": "Project not found" }` — also returned (not `403`) for a project belonging to a different tenant (ADR-029).

### `POST /api/v1/projects`

**Request body** (`ProjectCreate`): `{ "name": "string", "customer_id": "uuid | null", "notes": "string | null" }`

**Response (201):** the created `Project`, `status` defaulted to `"enquiry"`. Also logs a real `ActivityEvent` (`project_created`) server-side, same pattern as customer creation — the frontend no longer logs this itself.
**Response (404):** `{ "detail": "Customer not found" }` — since Sprint 012 (ADR-029), a non-null `customer_id` must belong to the caller's own tenant, or the project isn't created at all.

### `PATCH /api/v1/projects/{project_id}/status`

Advances (or otherwise sets) a project's stage in the job pipeline. This is the **only** update endpoint in the project — no general-purpose edit, matching the Customers precedent (list/detail/create) except for this one functionally-necessary exception: a "job pipeline" is meaningless without a way to move a project between stages.

**Request body** (`ProjectStatusUpdate`): `{ "status": "<ProjectStatus>" }`

`ProjectStatus` values, in pipeline order: `enquiry`, `quoted`, `booked`, `templated`, `fabricated`, `installed`, `complete`. Any value is accepted in any order — the API doesn't enforce moving forward-only; the frontend's detail page only ever offers the single next stage, but the endpoint itself doesn't restrict it.

**Response (200):** the updated `Project`.
**Response (404):** `{ "detail": "Project not found" }` — also returned (not `403`) for a project belonging to a different tenant (ADR-029) — the write is rejected before any mutation happens.
**Response (422):** pydantic enum validation — a `status` value outside the 7 listed above.

---

## Quote routes (`app/quotes/router.py`) — added Sprint 007

**All three routes require `Authorization: Bearer <token>`** — the third auth-enforced module (ADR-023). Quotes themselves are created via `POST /api/v1/quote` (below, still public) — these routes are for browsing/downloading what's already been calculated. **Tenant-scoped since Sprint 012 (ADR-029):** every query filters by the caller's own `tenant_id`; a quote created anonymously (no token presented to `POST /quote`) has no tenant and is invisible here to every caller.

### `GET /api/v1/quotes`

| Query param | Type | Default |
|---|---|---|
| `limit` | integer | `20` |

**Response** — array of the persisted `quotes` row shape, most recent first. Note this is **not** the same shape `POST /api/v1/quote` returns — there's no `customer` name or `slabs` count, since neither is a column on `quotes` (see `docs/DATABASE_SCHEMA.md` for why):
```json
[{ "id": "...", "customer_id": "...", "material": "Calacatta Gold", "thickness": "20mm", "kitchen_length": 3.5, "island": false, "waterfall": 0, "splashback": false, "upstands": false, "postcode": null, "price_per_slab": 2650, "price_before_vat": 5300, "vat": 1060.0, "total": 6360.0, "created_at": "2026-08-11T10:00:00Z" }]
```

### `GET /api/v1/quotes/{quote_id}`

**Response (200):** a single quote, same shape as above.
**Response (404):** `{ "detail": "Quote not found" }` — also returned (not `403`) for a quote belonging to a different tenant, or one with no tenant at all (ADR-029).

### `GET /api/v1/quotes/{quote_id}/invoice`

Generates and returns a real downloadable PDF invoice for an already-persisted quote — `app/quotes/pdf.py`, rewritten this sprint with a letterhead and a proper VAT breakdown table (material/thickness line, VAT, total), built in-memory (`io.BytesIO`), not written to local disk.

**Response (200):** `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="invoice-<id>.pdf"`, raw PDF bytes.
**Response (404):** `{ "detail": "Quote not found" }` — also returned (not `403`) for a quote belonging to a different tenant (ADR-029).

---

## Tenant routes (`app/tenants/router.py`) — added Sprint 008, list/detail scoped Sprint 012

**All three routes require `Authorization: Bearer <token>`.** GET (list) and GET/{id} were audited in Sprint 012 (ADR-029): before that sprint they returned **every** tenant in the system (name/slug/status) to any authenticated caller — a real cross-tenant leak. Both now return only the caller's own tenant.

### `GET /api/v1/tenants`

| Query param | Type | Default |
|---|---|---|
| `limit` | integer | `20` — accepted but unused since Sprint 012; the response is always the caller's own tenant, at most one row |

**Response** — an array containing exactly the caller's own `Tenant` (or empty if somehow absent):
```json
[{ "id": "...", "name": "Smoke Test Stoneworks", "slug": "smoke-test-stoneworks", "status": "active", "created_at": "2026-08-13T00:00:00Z" }]
```

### `GET /api/v1/tenants/{tenant_id}`

**Response (200):** the caller's own `Tenant` (same shape as above) — only if `tenant_id` matches the caller's own.
**Response (404):** `{ "detail": "Tenant not found" }` — also returned (not `403`) for any `tenant_id` that isn't the caller's own, including a real, existing tenant (ADR-029, ADR-028's cross-tenant-lookup-leak precedent).

### `POST /api/v1/tenants`

**Request body** (`TenantCreate`): `{ "name": "string", "slug": "string | null" }` — `slug` is auto-generated from `name` if omitted (lowercased, hyphenated), with a random-suffix retry on a collision.

**Response (201):** the created `Tenant`, `status` defaulted to `"active"`. Also logs a real `ActivityEvent` (`tenant_created`) server-side, tagged with the *new* tenant's own id, same pattern as customers/projects/quotes.

Creates a brand-new, **unlinked** tenant — the caller's own `tenant_id` doesn't change, and the caller has no special access to the tenant they just created (it's invisible via `GET /tenants*` to them too, same as any other tenant that isn't their own). Audited in Sprint 012 (ADR-029) and left unchanged: this doesn't read or expose any other tenant's data, so it isn't an isolation leak — whether this route should still be reachable at all now that `POST /api/v1/auth/signup` is the real workspace-creation path is a separate, explicitly deferred question.

---

## Invitation routes (`app/invitations/router.py`) — added Sprint 011 (ADR-028)

The first module that lets a tenant have more than one user, and the first place `require_role(UserRole.OWNER)` (Sprint 010, ADR-027) is actually attached to a route. `POST`/`GET`/`DELETE /api/v1/invitations*` require `Authorization: Bearer <token>` **and** an `Owner` role — `403` (`{"detail": "Insufficient permissions"}`) for a valid token belonging to a `Staff` user. The two `/token/{token}` routes are deliberately public — an invitee has no account yet.

### `POST /api/v1/invitations`

Creates a pending invitation for an email address. Always invites as `Staff` — `InvitationCreate` has no `role` field (see ADR-028 for why). Returns the one-time raw token; it is never retrievable again after this response (only its SHA-256 hash is persisted).

**Request body** (`InvitationCreate`): `{ "email": "newhire@example.com" }`

**Response (201)** (`InvitationCreateOut`):
```json
{
  "id": "...", "tenant_id": "...", "email": "newhire@example.com", "role": "Staff",
  "status": "pending", "invited_by_user_id": "...", "expires_at": "2026-08-21T00:37:36Z",
  "created_at": "2026-08-14T00:37:36Z", "token": "<one-time raw token, only ever returned here>"
}
```
**Response (409):** `{ "detail": "A user with that email already exists." }`, or `{ "detail": "An invitation is already pending for this email." }`.

### `GET /api/v1/invitations`

| Query param | Type | Default |
|---|---|---|
| `status_filter` | string \| null | none — no filter |

**Response** — array of `InvitationOut` (same shape as `POST`'s response, minus `token`), most recent first, scoped to the caller's tenant. `status` reflects `"expired"` for a still-`"pending"` row whose `expires_at` has passed, even though nothing was written back to the row (derived at read time — see ADR-028).

### `DELETE /api/v1/invitations/{invitation_id}`

Revokes a pending invitation.

**Response (200):** the updated `InvitationOut` (`status: "revoked"`).
**Response (404):** `{ "detail": "Invitation not found" }` — also returned (not `403`) for an invitation belonging to a different tenant, so a cross-tenant lookup can't confirm another tenant's invitation exists.

### `GET /api/v1/invitations/token/{token}` — public, no auth

What an unauthenticated invitee sees before deciding whether to accept.

**Response (200)** (`InvitationPublicOut`): `{ "email": "...", "role": "Staff", "tenant_name": "...", "status": "pending", "expires_at": "..." }` — no internal IDs.
**Response (404):** `{ "detail": "Invitation not found" }` — unknown token.

### `POST /api/v1/invitations/token/{token}/accept` — public, no auth

Creates the `Staff` user (via `app.auth.service.auth_service.create_user()`, the same primitive `signup()` uses) and signs them in immediately — same response shape as `/auth/login`.

**Request body** (`AcceptInvitationRequest`): `{ "name": "string", "password": "string" }`

**Response (200)** (`TokenResponse`) — same shape as `/auth/login`, `user.role` is `"Staff"`.
**Response (404):** `{ "detail": "Invitation not found" }` — unknown token.
**Response (409):** one of `{ "detail": "This invitation has been revoked." }`, `{ "detail": "This invitation has already been used." }`, `{ "detail": "This invitation link has expired." }`, or `{ "detail": "A user with that email already exists." }` (the email was registered through a separate path between invite and accept).

---

## Core routes (`app/api/v1/core.py`) — moved under `/api/v1` in Sprint 003, bodies unchanged

### `POST /api/v1/process`

Routes free text to an assistant via `BrainManager` → `BrainRouter`. The router is a hardcoded keyword-to-agent dictionary today, not an AI/LLM classifier (see `docs/DECISIONS.md`).

**Request**
```json
{ "text": "how much is calacatta gold" }
```

**Response** — shape depends on which agent handled it:
- Routed to `sales` (material/price keywords): `{ "material": "...", "price": "£...", "details": {...}, "includes": [...] }`, or `{ "message": "I couldn't find that material." }` if no match.
- Routed to `search` (show/find/compare keywords): a JSON array of scored material matches.
- Anything else: `{ "agent": "<agent-name-or-'executive'>", "request": "<original text>", "status": "received" }` — the 9 other named agents (construction, customer_service, executive, finance, marketing, projects, purchasing, scheduling, seo, social) are routed to by keyword but have no implemented logic yet, so they all fall through to this generic stub.

### `POST /api/v1/quote`

Calculates a full quote from structured input **and persists it** (Sprint 007 — `app/quotes/service.py`, wrapping the pricing engine in `app/quotes/calculator.py`). Deliberately stays public — matches the original engine's contract, and `/estimate`'s free-text path has no way to authenticate a caller either. **Since Sprint 012 (ADR-029):** if a valid `Authorization: Bearer <token>` is presented, the persisted quote is tagged with that caller's `tenant_id` and becomes visible via their `GET /api/v1/quotes`; called with no token (or an invalid/expired one), the quote is still created and this response is unchanged, but the row has no tenant and is invisible to every tenant's browsing routes.

**Request body** (`QuoteRequest`, `app/quotes/models.py`)

| Field | Type | Required | Default |
|---|---|---|---|
| `customer` | string | yes | — free-text name; **not** stored on the persisted row (no such column — see `docs/DATABASE_SCHEMA.md`), only echoed back in this response |
| `material` | string | yes | — must match a seeded material name (`app/materials/seed.py`), case-insensitive |
| `thickness` | string | yes | — actually affects `price_per_slab` (looked up as `(material, thickness)`) since Sprint 005 |
| `kitchen_length` | float | yes | — |
| `island` | boolean | no | `false` |
| `waterfall` | integer | no | `0` |
| `splashback` | boolean | no | `false` |
| `upstands` | boolean | no | `false` |
| `postcode` | string \| null | no | `null` |
| `customer_id` | uuid \| null | no | `null` — Sprint 007: optionally links a real `customers` row, persisted on the `quotes` row. Since Sprint 012, if the caller is authenticated, this id must belong to their own tenant or the request `404`s (`{ "detail": "Customer not found" }`) with nothing persisted; an anonymous call skips this check (no tenant to validate against). |

**Response** — the calculated result plus persistence metadata:
```json
{
  "customer": "Sarah Whitfield",
  "material": "Calacatta Gold",
  "slabs": 2,
  "price_per_slab": 2650,
  "price_before_vat": 5300,
  "vat": 1060.0,
  "total": 6360.0,
  "id": "59b2b3af-bd39-4439-8a39-204b68c7e615",
  "customer_id": null,
  "created_at": "2026-08-11T10:00:00Z"
}
```

Also logs a real `ActivityEvent` (`quote_created`) server-side — the frontend no longer logs this itself, same pattern Sprint 004/006 established for customers/projects.

**Fixed in Sprint 003, still true after Sprint 005's database-backed catalogue:** an unrecognised `material`/`thickness` combination returns a real `400` (`{ "detail": "Unrecognised value: '...'" }`) via a global exception handler (`app/core/errors.py`) — the lookup changed from a dict subscript to a DB query, but it still raises the same `KeyError` on a miss, so the handler needed no changes.

**Sprint 005 — slab count is a real formula**, not a placeholder: depth, wastage allowance, and island/waterfall/splashback/upstand extras all factor into `slabs`. See `docs/SPRINTS/sprint-005.md` for the exact constants and their documented assumptions.

### `POST /api/v1/estimate`

Free-text → quote. Parses a natural-language description with regex/keyword matching (`app/assistant/estimator.py` — not AI), builds a `QuoteRequest`, then persists via the same `quote_service` as `/api/v1/quote`. Same `400` behaviour on an unrecognised material, same response shape.

**Request**
```json
{ "text": "3.5m kitchen in calacatta oro with island" }
```

**Response** — same shape as `POST /api/v1/quote`.

### `GET /api/v1/dashboard`

**Sprint 007 — all four numbers are now real**, computed from the database (previously hardcoded). **`Authorization: Bearer <token>` required since Sprint 012 (ADR-029)** — this route had no auth at all before this sprint; the four numbers below are now the caller's own tenant's counts, not global ones. No query parameters.

```json
{
  "quotes_today": 3,
  "revenue": 18420.0,
  "customers": 12,
  "projects": 4
}
```

| Field | Source |
|---|---|
| `quotes_today` | `count(quotes)` where `created_at` is today |
| `revenue` | `sum(quotes.total)` — all-time, distinct from `quotes_today` by design |
| `customers` | `count(customers)` |
| `projects` | `count(projects)` |

---

## Activity routes (`app/activity/router.py`) — added Sprint 001, mounted under `/api/v1` in Sprint 003, auth + tenant-scoped Sprint 012

Backed by `PostgresActivityRepository` since Sprint 002 — data survives a server restart. **`Authorization: Bearer <token>` required since Sprint 012 (ADR-029)** — both routes had no auth at all before this sprint. Every event is now scoped to the caller's tenant: `GET` only returns events logged under the caller's own `tenant_id`, and `POST` tags the new event with it. A seed-data event or one logged from an anonymous `POST /api/v1/quote`/`/estimate` call has no tenant and is invisible here to every caller.

### `GET /api/v1/activity`

| Query param | Type | Default | Notes |
|---|---|---|---|
| `limit` | integer | `20` | Max events returned, most recent first |
| `type` | `ActivityType` \| omitted | none | Filter to one event type |

`ActivityType` values: `quote_created`, `customer_added`, `project_created`, `invoice_generated`, `ai_request`, `user_login`, `tenant_created` (Sprint 008).

**Response** — array of `ActivityEvent`:
```json
[
  {
    "id": "59b2b3af-bd39-4439-8a39-204b68c7e615",
    "type": "quote_created",
    "title": "New quote created",
    "description": "Sarah Whitfield — Calacatta Gold, £6,360",
    "timestamp": "2026-08-09T14:32:01.123456"
  }
]
```

### `POST /api/v1/activity`

**Request body** (`ActivityEventCreate`): `{ "type": "<ActivityType>", "title": "string", "description": "string | null" }`

**Response** — the created `ActivityEvent` (same shape as above, with generated `id`/`timestamp`).

---

## Notification routes (`app/notifications/router.py`) — added Sprint 001, mounted under `/api/v1` in Sprint 003, auth + tenant-scoped Sprint 012

Backed by `PostgresNotificationRepository` since Sprint 002 — data survives a server restart. **`Authorization: Bearer <token>` required since Sprint 012 (ADR-029)** — all four routes had no auth at all before this sprint. Every notification is now scoped to the caller's tenant, including the mark-as-read write path: marking a different tenant's notification as read `404`s rather than mutating it.

### `GET /api/v1/notifications`

| Query param | Type | Default |
|---|---|---|
| `limit` | integer | `50` |

**Response** — array of `Notification`:
```json
[
  {
    "id": "a1b2c3...",
    "title": "Quote approved",
    "message": "Sarah Whitfield approved her Calacatta Gold quote.",
    "type": "success",
    "timestamp": "2026-08-09T14:00:00.000000",
    "read": false
  }
]
```
`NotificationType` values: `success`, `warning`, `info`, `error`.

### `GET /api/v1/notifications/unread-count`

```json
{ "unread": 3 }
```

### `POST /api/v1/notifications`

**Request body** (`NotificationCreate`): `{ "title": "string", "message": "string", "type": "<NotificationType>" }` (`type` defaults to `"info"` if omitted).

**Response** — the created `Notification`.

### `PATCH /api/v1/notifications/{notification_id}/read`

Marks one notification as read.

- **Response (200):** the updated `Notification`.
- **Response (404):** `{ "detail": "Notification not found" }` — also returned (not `403`) for a notification belonging to a different tenant (ADR-029); nothing is mutated.

---

## Error responses (`app/core/errors.py`) — added Sprint 003

| Status | When | Body shape |
|---|---|---|
| `400` | A lookup against a known dict fails (e.g. unrecognised `/api/v1/quote` material) | `{ "detail": "Unrecognised value: '...'" }` |
| `401` | Bad login credentials, or a missing/invalid/expired token on `/api/v1/auth/me` | `{ "detail": "..." }` |
| `404` | Resource not found (e.g. unknown notification id) | `{ "detail": "..." }` |
| `422` | Request body fails pydantic validation | `{ "detail": "Invalid request", "errors": [...] }` |
| `500` | Any other unhandled exception | `{ "detail": "Internal server error" }` — logged server-side, never leaks a stack trace to the client |

---

## Route summary table

| Method | Path | Added | DB-backed? | Auth required? |
|---|---|---|---|---|
| GET | `/` | Initial | No | No |
| GET | `/health` | Initial | No | No |
| POST | `/api/v1/auth/signup` | Sprint 009 | Yes | No (issues the token) |
| POST | `/api/v1/auth/login` | Sprint 003 (tenant-aware since Sprint 009) | Yes | No (issues the token) |
| GET | `/api/v1/auth/me` | Sprint 003 | Yes | **Yes** |
| GET | `/api/v1/customers` | Sprint 004 | Yes | **Yes** |
| POST | `/api/v1/customers` | Sprint 004 | Yes | **Yes** |
| GET | `/api/v1/customers/{customer_id}` | Sprint 004 | Yes | **Yes** |
| GET | `/api/v1/projects` | Sprint 006 | Yes | **Yes** |
| POST | `/api/v1/projects` | Sprint 006 | Yes | **Yes** |
| GET | `/api/v1/projects/{project_id}` | Sprint 006 | Yes | **Yes** |
| PATCH | `/api/v1/projects/{project_id}/status` | Sprint 006 | Yes | **Yes** |
| GET | `/api/v1/quotes` | Sprint 007 | Yes | **Yes** |
| GET | `/api/v1/quotes/{quote_id}` | Sprint 007 | Yes | **Yes** |
| GET | `/api/v1/quotes/{quote_id}/invoice` | Sprint 007 | Yes | **Yes** |
| GET | `/api/v1/tenants` | Sprint 008 | Yes | **Yes** — own tenant only (Sprint 012) |
| POST | `/api/v1/tenants` | Sprint 008 | Yes | **Yes** (existing single-tenant gate) |
| GET | `/api/v1/tenants/{tenant_id}` | Sprint 008 | Yes | **Yes** — own tenant only (Sprint 012) |
| POST | `/api/v1/invitations` | Sprint 011 | Yes | **Yes** (`require_role(OWNER)`) |
| GET | `/api/v1/invitations` | Sprint 011 | Yes | **Yes** (`require_role(OWNER)`) |
| DELETE | `/api/v1/invitations/{invitation_id}` | Sprint 011 | Yes | **Yes** (`require_role(OWNER)`) |
| GET | `/api/v1/invitations/token/{token}` | Sprint 011 | Yes | No (invitee has no account yet) |
| POST | `/api/v1/invitations/token/{token}/accept` | Sprint 011 | Yes | No (issues the token) |
| POST | `/api/v1/process` | Initial | No | No |
| POST | `/api/v1/quote` | Initial | Yes — Postgres (Sprint 007) | No — optional since Sprint 012 (tags tenant if presented) |
| POST | `/api/v1/estimate` | Initial | Yes — Postgres (Sprint 007) | No — optional since Sprint 012 (tags tenant if presented) |
| GET | `/api/v1/dashboard` | Initial | Yes — Postgres (Sprint 007) | **Yes** (Sprint 012) |
| GET | `/api/v1/activity` | Sprint 001 | Yes — Postgres (Sprint 002) | **Yes** (Sprint 012) |
| POST | `/api/v1/activity` | Sprint 001 | Yes — Postgres (Sprint 002) | **Yes** (Sprint 012) |
| GET | `/api/v1/notifications` | Sprint 001 | Yes — Postgres (Sprint 002) | **Yes** (Sprint 012) |
| GET | `/api/v1/notifications/unread-count` | Sprint 001 | Yes — Postgres (Sprint 002) | **Yes** (Sprint 012) |
| POST | `/api/v1/notifications` | Sprint 001 | Yes — Postgres (Sprint 002) | **Yes** (Sprint 012) |
| PATCH | `/api/v1/notifications/{notification_id}/read` | Sprint 001 | Yes — Postgres (Sprint 002) | **Yes** (Sprint 012) |

The old unprefixed paths (`/quote`, `/activity`, `/notifications`, etc.) all return `404` as of Sprint 003 — confirmed via `tests/test_health.py`. `POST /api/v1/quote/pdf` (Sprint 001–006) was **removed** in Sprint 007, not kept alongside the new flow — replaced by `GET /api/v1/quotes/{id}/invoice`, which downloads a real PDF for an already-persisted quote instead of calculating-and-writing-to-disk in one call.
