# SIMO OS — API Specification

**Status:** Reflects the actual FastAPI application as of Sprint 004 (`app/main.py` + `app/api/v1/` + `app/auth/` + `app/customers/` + `app/activity/` + `app/notifications/`). Sprint 003 moved every route except `/` and `/health` under `/api/v1` (clean cutover) and added JWT login/`/me`. Sprint 004 adds the first real business-data module (`customers`) and is the first to actually **require** a token.
**Base URL (local dev):** `http://127.0.0.1:8000`
**Versioning:** `/api/v1` prefix on every route except `GET /` and `GET /health`, which stay unversioned as infra/health-check endpoints. Implemented Sprint 003 (ADR-012).
**Authentication:** JWT bearer tokens (`POST /api/v1/auth/login`, `GET /api/v1/auth/me`) since Sprint 003. Sprint 003 itself required no route to present one (ADR-020); Sprint 004's `/api/v1/customers/*` routes are the first to enforce it (ADR-021) — every other route below is still callable without a token.
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

**Response (201):** the created `Customer`. Also logs a real `ActivityEvent` (`customer_added`) server-side — the frontend no longer logs this itself (contrast with `/quotes/new`/`/projects/new`, which still do, pending their own sprints).

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

Calculates a full quote from structured input. This is the real pricing engine (`app/quotes/calculator.py`).

**Request body** (`QuoteRequest`, `app/quotes/models.py`)

| Field | Type | Required | Default |
|---|---|---|---|
| `customer` | string | yes | — |
| `material` | string | yes | — (must match a key in `app/data/pricing.py`, case-insensitive) |
| `thickness` | string | yes | — |
| `kitchen_length` | float | yes | — |
| `island` | boolean | no | `false` |
| `waterfall` | integer | no | `0` |
| `splashback` | boolean | no | `false` |
| `upstands` | boolean | no | `false` |
| `postcode` | string \| null | no | `null` |

**Response**
```json
{
  "customer": "Sarah Whitfield",
  "material": "Calacatta Gold",
  "slabs": 2,
  "price_per_slab": 2650,
  "price_before_vat": 5300,
  "vat": 1060.0,
  "total": 6360.0
}
```

**Fixed in Sprint 003:** an unrecognised `material` value now returns a real `400` (`{ "detail": "Unrecognised value: '...'" }`) via a global exception handler (`app/core/errors.py`), instead of an unhandled `KeyError` surfacing as a raw `500`.

### `POST /api/v1/estimate`

Free-text → quote. Parses a natural-language description with regex/keyword matching (`app/assistant/estimator.py` — not AI), builds a `QuoteRequest`, then calls the same calculation logic as `/api/v1/quote`. Same `400` behaviour on an unrecognised material.

**Request**
```json
{ "text": "3.5m kitchen in calacatta oro with island" }
```

**Response** — same shape as `POST /api/v1/quote`.

### `POST /api/v1/quote/pdf`

Generates a PDF quote document.

**Request body** — same `QuoteRequest` shape as `POST /api/v1/quote`.

**Response**
```json
{ "pdf": "quote.pdf", "quote": { /* calculated quote, same shape as POST /api/v1/quote */ } }
```

**Known limitation (unchanged):** the PDF is written to `quote.pdf` on the server's local disk (overwritten on every call) rather than returned as a downloadable file or stored per-quote. Not wired into the frontend yet.

### `GET /api/v1/dashboard`

**Returns hardcoded, static numbers — not database-backed.** No query parameters affect the response.

```json
{
  "quotes_today": 12,
  "revenue": 8420,
  "customers": 327,
  "projects": 18
}
```

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
| POST | `/api/v1/process` | Initial | No | No |
| POST | `/api/v1/quote` | Initial | No | No |
| POST | `/api/v1/estimate` | Initial | No | No |
| POST | `/api/v1/quote/pdf` | Initial | No | No |
| GET | `/api/v1/dashboard` | Initial | No (hardcoded) | No |
| GET | `/api/v1/activity` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| POST | `/api/v1/activity` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| GET | `/api/v1/notifications` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| GET | `/api/v1/notifications/unread-count` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| POST | `/api/v1/notifications` | Sprint 001 | Yes — Postgres (Sprint 002) | No |
| PATCH | `/api/v1/notifications/{notification_id}/read` | Sprint 001 | Yes — Postgres (Sprint 002) | No |

The old unprefixed paths (`/quote`, `/activity`, `/notifications`, etc.) all return `404` as of Sprint 003 — confirmed via `tests/test_health.py`.
