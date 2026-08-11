# SIMO OS — API Specification

**Status:** Reflects the actual FastAPI application as of Sprint 007 (`app/main.py` + `app/api/v1/` + `app/auth/` + `app/customers/` + `app/projects/` + `app/quotes/` + `app/activity/` + `app/notifications/`). Sprint 003 moved every route except `/` and `/health` under `/api/v1` (clean cutover) and added JWT login/`/me`. Sprint 004 added the first auth-enforced module (`customers`); Sprint 006 added the second (`projects`); Sprint 007 adds the third (`quotes`) and, for the first time, actually persists a calculated quote.
**Base URL (local dev):** `http://127.0.0.1:8000`
**Versioning:** `/api/v1` prefix on every route except `GET /` and `GET /health`, which stay unversioned as infra/health-check endpoints. Implemented Sprint 003 (ADR-012).
**Authentication:** JWT bearer tokens (`POST /api/v1/auth/login`, `GET /api/v1/auth/me`) since Sprint 003. Sprint 003 itself required no route to present one (ADR-020); `/api/v1/customers/*` (Sprint 004, ADR-021), `/api/v1/projects/*` (Sprint 006, ADR-022), and `/api/v1/quotes/*` (Sprint 007, ADR-023) enforce it. `POST /api/v1/quote` and `POST /api/v1/estimate` deliberately stay public — every other route below is still callable without a token.
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

## Auth routes (`app/auth/router.py`) — added Sprint 003

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
  "user": { "id": "...", "name": "Simo", "email": "owner@simo-os.local", "role": "Owner" }
}
```

**Response (401):** `{ "detail": "Incorrect email or password" }`

### `GET /api/v1/auth/me`

`Authorization: Bearer <token>` header required.

**Response (200)** (`UserOut`): `{ "id": "...", "name": "...", "email": "...", "role": "..." }`
**Response (401):** `{ "detail": "Could not validate credentials" }` — missing, malformed, or expired token.

One owner account is seeded on startup (`app/auth/seed.py`) if the `users` table is empty, from `.env`'s `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD` — never hardcoded credentials.

---

## Customer routes (`app/customers/router.py`) — added Sprint 004

**All three routes require `Authorization: Bearer <token>`** — the first auth-enforced module (ADR-021). `401` (`{"detail": "Could not validate credentials"}`) without a valid token.

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
**Response (404):** `{ "detail": "Customer not found" }`.

### `POST /api/v1/customers`

**Request body** (`CustomerCreate`): `{ "name": "string", "email": "string | null", "phone": "string | null" }`

**Response (201):** the created `Customer`. Also logs a real `ActivityEvent` (`customer_added`) server-side — the frontend no longer logs this itself. (As of Sprint 007, `/quotes/new` follows the same pattern too — see the Quote routes section below.)

---

## Project routes (`app/projects/router.py`) — added Sprint 006

**All four routes require `Authorization: Bearer <token>`** — the second auth-enforced module (same reasoning as customers, ADR-021/ADR-022).

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
**Response (404):** `{ "detail": "Project not found" }`.

### `POST /api/v1/projects`

**Request body** (`ProjectCreate`): `{ "name": "string", "customer_id": "uuid | null", "notes": "string | null" }`

**Response (201):** the created `Project`, `status` defaulted to `"enquiry"`. Also logs a real `ActivityEvent` (`project_created`) server-side, same pattern as customer creation — the frontend no longer logs this itself.

### `PATCH /api/v1/projects/{project_id}/status`

Advances (or otherwise sets) a project's stage in the job pipeline. This is the **only** update endpoint in the project — no general-purpose edit, matching the Customers precedent (list/detail/create) except for this one functionally-necessary exception: a "job pipeline" is meaningless without a way to move a project between stages.

**Request body** (`ProjectStatusUpdate`): `{ "status": "<ProjectStatus>" }`

`ProjectStatus` values, in pipeline order: `enquiry`, `quoted`, `booked`, `templated`, `fabricated`, `installed`, `complete`. Any value is accepted in any order — the API doesn't enforce moving forward-only; the frontend's detail page only ever offers the single next stage, but the endpoint itself doesn't restrict it.

**Response (200):** the updated `Project`.
**Response (404):** `{ "detail": "Project not found" }`.
**Response (422):** pydantic enum validation — a `status` value outside the 7 listed above.

---

## Quote routes (`app/quotes/router.py`) — added Sprint 007

**All three routes require `Authorization: Bearer <token>`** — the third auth-enforced module (ADR-023). Quotes themselves are created via `POST /api/v1/quote` (below, still public) — these routes are for browsing/downloading what's already been calculated.

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
**Response (404):** `{ "detail": "Quote not found" }`.

### `GET /api/v1/quotes/{quote_id}/invoice`

Generates and returns a real downloadable PDF invoice for an already-persisted quote — `app/quotes/pdf.py`, rewritten this sprint with a letterhead and a proper VAT breakdown table (material/thickness line, VAT, total), built in-memory (`io.BytesIO`), not written to local disk.

**Response (200):** `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="invoice-<id>.pdf"`, raw PDF bytes.
**Response (404):** `{ "detail": "Quote not found" }`.

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

Calculates a full quote from structured input **and persists it** (Sprint 007 — `app/quotes/service.py`, wrapping the pricing engine in `app/quotes/calculator.py`). Deliberately stays public — matches the original engine's contract, and `/estimate`'s free-text path has no way to authenticate a caller either.

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
| `customer_id` | uuid \| null | no | `null` — Sprint 007: optionally links a real `customers` row, persisted on the `quotes` row |

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

**Sprint 007 — all four numbers are now real**, computed from the database (previously hardcoded). No auth required (consistent with `/activity`), no query parameters.

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

## Activity routes (`app/activity/router.py`) — added Sprint 001, mounted under `/api/v1` in Sprint 003

Backed by `PostgresActivityRepository` since Sprint 002 — data survives a server restart. Router body unchanged since Sprint 001 (ADR-002); only its mount prefix changed.

### `GET /api/v1/activity`

| Query param | Type | Default | Notes |
|---|---|---|---|
| `limit` | integer | `20` | Max events returned, most recent first |
| `type` | `ActivityType` \| omitted | none | Filter to one event type |

`ActivityType` values: `quote_created`, `customer_added`, `project_created`, `invoice_generated`, `ai_request`, `user_login`.

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

## Notification routes (`app/notifications/router.py`) — added Sprint 001, mounted under `/api/v1` in Sprint 003

Backed by `PostgresNotificationRepository` since Sprint 002 — data survives a server restart. Router body unchanged since Sprint 001; only its mount prefix changed.

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
- **Response (404):** `{ "detail": "Notification not found" }`.

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
| POST | `/api/v1/auth/login` | Sprint 003 | Yes | No (issues the token) |
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
| POST | `/api/v1/process` | Initial | No | No |
| POST | `/api/v1/quote` | Initial | Yes — Postgres (Sprint 007) | No |
| POST | `/api/v1/estimate` | Initial | Yes — Postgres (Sprint 007) | No |
| GET | `/api/v1/dashboard` | Initial | Yes — Postgres (Sprint 007) | No |
| GET | `/api/v1/activity` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| POST | `/api/v1/activity` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| GET | `/api/v1/notifications` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| GET | `/api/v1/notifications/unread-count` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| POST | `/api/v1/notifications` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| PATCH | `/api/v1/notifications/{notification_id}/read` | Sprint 001 | Yes — Postgres (Sprint 002) | No |

The old unprefixed paths (`/quote`, `/activity`, `/notifications`, etc.) all return `404` as of Sprint 003 — confirmed via `tests/test_health.py`. `POST /api/v1/quote/pdf` (Sprint 001–006) was **removed** in Sprint 007, not kept alongside the new flow — replaced by `GET /api/v1/quotes/{id}/invoice`, which downloads a real PDF for an already-persisted quote instead of calculating-and-writing-to-disk in one call.
