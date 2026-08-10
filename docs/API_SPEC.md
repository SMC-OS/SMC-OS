# SIMO OS — API Specification

**Status:** Reflects the actual FastAPI application as of Sprint 002 (`app/main.py` + `app/activity/` + `app/notifications/`). No route paths, request shapes, or response shapes changed in Sprint 002 — the only change is that `/activity` and `/notifications` are now PostgreSQL-backed instead of in-memory (see `docs/DATABASE_SCHEMA.md`), so their data now survives a server restart.
**Base URL (local dev):** `http://127.0.0.1:8000`
**Versioning:** None yet. All routes are unprefixed. `/api/v1` is planned for Sprint 003.
**Authentication:** None. Every route below is public. JWT auth is planned for Sprint 003.
**CORS:** `allow_origins=["*"]`, all methods and headers allowed (`app/main.py`) — acceptable for local development only; must be restricted before any non-local deployment.

---

## Core routes (`app/main.py`)

### `GET /`

Welcome message. No parameters.

```json
{
  "message": "Welcome to Simo OS",
  "status": "running"
}
```

### `GET /health`

Static health check — does **not** check a database connection (there isn't one yet).

```json
{ "status": "healthy" }
```

### `POST /process`

Routes free text to an assistant via `BrainManager` → `BrainRouter`. The router is a hardcoded keyword-to-agent dictionary today, not an AI/LLM classifier (see `docs/DECISIONS.md`).

**Request**
```json
{ "text": "how much is calacatta gold" }
```

**Response** — shape depends on which agent handled it:
- Routed to `sales` (material/price keywords): `{ "material": "...", "price": "£...", "details": {...}, "includes": [...] }`, or `{ "message": "I couldn't find that material." }` if no match.
- Routed to `search` (show/find/compare keywords): a JSON array of scored material matches.
- Anything else: `{ "agent": "<agent-name-or-'executive'>", "request": "<original text>", "status": "received" }` — the 9 other named agents (construction, customer_service, executive, finance, marketing, projects, purchasing, scheduling, seo, social) are routed to by keyword but have no implemented logic yet, so they all fall through to this generic stub.

### `POST /quote`

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

**Known limitation:** an unrecognised `material` value raises an unhandled `KeyError`, which FastAPI surfaces as a raw `500 Internal Server Error` — there is no input validation or friendly error response yet (`app/quotes/validator.py` is an empty placeholder).

### `POST /estimate`

Free-text → quote. Parses a natural-language description with regex/keyword matching (`app/assistant/estimator.py` — not AI), builds a `QuoteRequest`, then calls the same calculation logic as `/quote`.

**Request**
```json
{ "text": "3.5m kitchen in calacatta oro with island" }
```

**Response** — same shape as `POST /quote`.

### `POST /quote/pdf`

Generates a PDF quote document.

**Request body** — same `QuoteRequest` shape as `POST /quote`.

**Response**
```json
{ "pdf": "quote.pdf", "quote": { /* calculated quote, same shape as POST /quote */ } }
```

**Known limitation:** the PDF is written to `quote.pdf` on the server's local disk (overwritten on every call) rather than returned as a downloadable file or stored per-quote. Not wired into the frontend yet.

### `GET /dashboard`

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

## Activity routes (`app/activity/router.py`) — added Sprint 001

Backed by `PostgresActivityRepository` since Sprint 002 — data survives a server restart. `InMemoryActivityRepository` still exists in the same file but is no longer constructed by default. See `docs/DATABASE_SCHEMA.md`.

### `GET /activity`

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

### `POST /activity`

**Request body** (`ActivityEventCreate`): `{ "type": "<ActivityType>", "title": "string", "description": "string | null" }`

**Response** — the created `ActivityEvent` (same shape as above, with generated `id`/`timestamp`).

---

## Notification routes (`app/notifications/router.py`) — added Sprint 001

Backed by `PostgresNotificationRepository` since Sprint 002 — data survives a server restart. `InMemoryNotificationRepository` still exists in the same file but is no longer constructed by default.

### `GET /notifications`

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

### `GET /notifications/unread-count`

```json
{ "unread": 3 }
```

### `POST /notifications`

**Request body** (`NotificationCreate`): `{ "title": "string", "message": "string", "type": "<NotificationType>" }` (`type` defaults to `"info"` if omitted).

**Response** — the created `Notification`.

### `PATCH /notifications/{notification_id}/read`

Marks one notification as read.

- **Response (200):** the updated `Notification`.
- **Response (404):** `{ "detail": "Notification not found" }` — the only endpoint in the whole API with an explicit error response today.

---

## Route summary table

| Method | Path | Added | DB-backed? |
|---|---|---|---|
| GET | `/` | Initial | No |
| GET | `/health` | Initial | No |
| POST | `/process` | Initial | No |
| POST | `/quote` | Initial | No |
| POST | `/estimate` | Initial | No |
| POST | `/quote/pdf` | Initial | No |
| GET | `/dashboard` | Initial | No (hardcoded) |
| GET | `/activity` | Sprint 001 | **Yes** — Postgres (Sprint 002) |
| POST | `/activity` | Sprint 001 | **Yes** — Postgres (Sprint 002) |
| GET | `/notifications` | Sprint 001 | **Yes** — Postgres (Sprint 002) |
| GET | `/notifications/unread-count` | Sprint 001 | **Yes** — Postgres (Sprint 002) |
| POST | `/notifications` | Sprint 001 | **Yes** — Postgres (Sprint 002) |
| PATCH | `/notifications/{notification_id}/read` | Sprint 001 | **Yes** — Postgres (Sprint 002) |

The other 7 original routes remain not-DB-backed — that's unchanged Sprint 002 scope (see `docs/DATABASE_SCHEMA.md` §3 for what Sprint 002 deliberately didn't build).
