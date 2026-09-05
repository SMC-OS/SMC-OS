# GeoCore — API Specification

**Status:** Reflects the actual FastAPI application through Sprint 018. Sprint 018 adds the production runtime contract without changing product-route auth or tenant semantics: configurable CORS, request IDs, dependency-free liveness, database-aware readiness, and safe structured error/request logging (ADR-034).
**Base URL (local dev):** `http://127.0.0.1:8000`
**Versioning:** `/api/v1` prefix on every product route. `GET /`, `GET /health`, and `GET /ready` are unversioned infrastructure routes. `/health` was preserved from Sprint 003's versioning decision (ADR-012); `/ready` was added in Sprint 018 (ADR-034).
**Authentication:** JWT bearer tokens (`POST /api/v1/auth/login`, `POST /api/v1/auth/signup`, `GET /api/v1/auth/me`) since Sprint 003 (signup added Sprint 009). Every token carries a `tenant_id` claim since Sprint 009 (ADR-026) — a token issued before that sprint is rejected (`401`), not silently accepted. Sprint 003 itself required no route to present a token (ADR-020); `/api/v1/customers/*` (Sprint 004, ADR-021), `/api/v1/projects/*` (Sprint 006, ADR-022), `/api/v1/quotes/*` (Sprint 007, ADR-023), `/api/v1/tenants/*` (Sprint 008), and — since Sprint 012 (ADR-029) — `/api/v1/activity*`, `/api/v1/notifications*`, and `GET /api/v1/dashboard` all enforce it. `POST /api/v1/quote` and `POST /api/v1/estimate` deliberately stay public (ADR-023); since Sprint 012, a valid token optionally tags the created quote with the caller's tenant via `get_current_user_optional` — called with no token, the quote is still created, just tenant-less.
**CORS:** Origins come from `CORS_ALLOWED_ORIGINS`. Development/test default to `http://localhost:3000` and `http://127.0.0.1:3000`; production requires an explicit comma-separated list of absolute HTTPS origins and rejects wildcard, loopback, credentials, path, query, and fragment values. Methods and headers remain broad and credentials remain enabled, but a denied origin receives no CORS permission. CORS is a browser policy, not authentication; JWT/portal-token and tenant checks remain authoritative.
**Request correlation:** Every HTTP response includes `X-Request-ID`. A caller-supplied value is retained only when it is 1–128 ASCII letters, digits, `.`, `_`, or `-`; otherwise the backend generates a UUID. This value is for correlation only and grants no identity or permission.

---

## Infra routes (unversioned, `app/main.py`)

### `GET /`

Welcome message. No parameters.

```json
{
  "message": "Welcome to GeoCore",
  "status": "running"
}
```

### `GET /health`

Dependency-free liveness check. It does **not** access the database, filesystem, network, or migration state.

```json
{ "status": "healthy" }
```

### `GET /ready`

Unauthenticated database-readiness check. It runs a bounded `SELECT 1` through the configured SQLAlchemy engine. The entire connection-and-query probe is capped at `READINESS_TIMEOUT_SECONDS`, which cannot exceed two seconds.

**Response (200):**

```json
{ "status": "ready", "database": "reachable" }
```

**Response (503):**

```json
{ "status": "not_ready", "database": "unreachable" }
```

The 503 response never includes the connection string, database host, credentials, driver error, raw exception, or stack trace. `/ready` proves connectivity only; it does not inspect or certify the current Alembic revision.

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
{ "email": "owner@geocore.local", "password": "..." }
```

**Response (200)** (`TokenResponse`)
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "...", "name": "Jordan Owner", "email": "owner@geocore.local", "role": "Owner",
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

In development/test, one owner account is seeded during lifespan only when `SEED_DATA_ENABLED=true` and the `users` table is empty, using `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD`. Since Sprint 009 this goes through the same `AuthService.signup()` path as a real signup, giving the seeded owner a real "Default Workspace" tenant instead of special-cased logic. Production requires `SEED_DATA_ENABLED=false` and never runs this seeder.

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

## Portal routes (`app/portal/router.py`) — added Sprint 013 (ADR-030)

Read-only client portal: a customer views their own projects/quotes with no account, no login, no `users` row. Token design mirrors `app/invitations/router.py` exactly (opaque `secrets.token_urlsafe(32)`, SHA-256-hashed at rest) with one behavioral difference: **a portal link is reusable, not single-use** — there is no `"accepted"` status and no accept step; every `GET` against an `"active"`, unexpired token just re-reads the current data. `POST`/`GET`/`DELETE /api/v1/portal-links*` require `Authorization: Bearer <token>` but, unlike invitations, are **not** `require_role(OWNER)`-gated — sharing a project link with a customer is routine Staff work, not a tenant-control decision. The one `/token/{token}` route is deliberately public.

### `POST /api/v1/portal-links`

Creates a reusable portal link for one customer. Returns the one-time raw token; it is never retrievable again after this response (only its SHA-256 hash is persisted).

**Request body** (`PortalLinkCreate`): `{ "customer_id": "uuid" }`

**Response (201)** (`PortalLinkCreateOut`):
```json
{
  "id": "...", "tenant_id": "...", "customer_id": "...", "created_by_user_id": "...",
  "status": "active", "expires_at": "2026-11-13T07:02:30Z", "created_at": "2026-08-15T07:02:30Z",
  "token": "<one-time raw token, only ever returned here>"
}
```
**Response (404):** `{ "detail": "Customer not found" }` — `customer_id` must belong to the caller's own tenant (ADR-029's relationship-linkage-bypass check, same pattern as `POST /api/v1/projects`).

### `GET /api/v1/portal-links`

| Query param | Type | Default |
|---|---|---|
| `customer_id` | uuid \| null | none — no filter, lists every link for the caller's tenant |

**Response** — array of `PortalLinkOut` (same shape as `POST`'s response, minus `token`), most recent first, scoped to the caller's tenant. `status` reflects `"expired"` for a still-`"active"` row whose `expires_at` has passed, derived at read time (never written back — see ADR-030).

### `DELETE /api/v1/portal-links/{portal_link_id}`

Revokes a portal link — the customer's link stops working immediately (subsequent `GET /token/{token}` calls read as `"revoked"`, no data).

**Response (200):** the updated `PortalLinkOut` (`status: "revoked"`).
**Response (404):** `{ "detail": "Portal link not found" }` — also returned (not `403`) for a link belonging to a different tenant, so a cross-tenant lookup can't confirm another tenant's link exists.

### `GET /api/v1/portal-links/token/{token}` — public, no auth

What the customer sees. **Always `200`, even for a revoked or expired link** — `status` tells the story, `projects`/`quotes` are simply empty then (same "shape, not an error, carries the state" convention `InvitationPublicOut` uses). No internal ids, no customer email/phone — identity is confirmed by possession of the link, not by echoing PII back. `notes` on a project is deliberately excluded (may hold internal staff remarks).

**Response (200)** (`PortalPublicOut`):
```json
{
  "status": "active",
  "tenant_name": "Acme Stoneworks",
  "customer_name": "Sarah Whitfield",
  "expires_at": "2026-11-13T07:02:30Z",
  "projects": [{ "id": "...", "name": "Riverside Kitchen Renovation", "status": "quoted", "created_at": "..." }],
  "quotes": [{ "id": "...", "material": "Calacatta Gold", "thickness": "20mm", "kitchen_length": 3.5, "price_before_vat": 5300, "vat": 1060.0, "total": 6360.0, "created_at": "..." }]
}
```
**Response (404):** `{ "detail": "Portal link not found" }` — unknown token only; a revoked/expired *known* token still returns `200` (see above).

### `GET /api/v1/portal-links/token/{token}/invoice/{quote_id}` — public, no auth

Downloads the same PDF invoice `GET /api/v1/quotes/{quote_id}/invoice` produces, reusing `app/quotes/pdf.py` — only reachable via a valid, **active** (not expired/revoked) link, and only for a quote belonging to that link's own `customer_id`, not merely its tenant (a portal link scoped to one customer must not surface a different customer's invoice, even within the same tenant).

**Response (200):** `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="invoice-<id>.pdf"`, raw PDF bytes.
**Response (404):** `{ "detail": "Invoice not found" }` — unknown token, an inactive (expired/revoked) token, an unknown `quote_id`, or a quote belonging to a different customer/tenant. All four cases return the identical response, so a caller can't distinguish "bad token" from "not your quote."

### `GET /api/v1/portal-links/token/{token}/documents` — public, no auth — added Sprint 016 (ADR-032)

Lists documents uploaded against the token's own customer. Same active-token requirement as the invoice route above — a revoked/expired link lists none.

**Response (200):** array of `DocumentOut` (see Document routes below).
**Response (404):** `{ "detail": "Portal link not found" }` — unknown or inactive token.

### `GET /api/v1/portal-links/token/{token}/documents/{document_id}/download` — public, no auth — added Sprint 016 (ADR-032)

Downloads one document, reusing `app/documents/service.py`'s `file_path()`. Only reachable via a valid, active link, and only for a document belonging to that link's own `customer_id` — mirrors the invoice route's "match both tenant_id AND customer_id" pattern exactly.

**Response (200):** `Content-Type: <the stored content_type>`, `Content-Disposition: attachment; filename="<original_filename>"`, raw file bytes.
**Response (404):** `{ "detail": "Document not found" }` — unknown/inactive token, unknown `document_id`, or a document belonging to a different customer. All cases return the identical response.

---

## Message routes (`app/messages/router.py` + `app/portal/router.py`) — added Sprint 017 (ADR-033)

Customer-level, chronological plain-text messaging. Bodies must contain at least one non-whitespace character and are limited to 5,000 characters. Message bodies are stored unchanged and must be rendered as text, never HTML or markdown. No attachments, editing/deleting, read state, real-time push, or rate limiting are provided.

### `POST /api/v1/messages?customer_id={customer_id}`

Authenticated staff route; any tenant user may post. `customer_id` is a required query parameter. The customer must belong to the caller's tenant or the response is 404. Request body: `{ "body": "text" }`. Response `201` is `MessageOut`; `sender_type` is `"staff"` and `sender_user_id` is the caller's user id. Staff messages do not create activity or notifications.

### `GET /api/v1/messages?customer_id={customer_id}`

Authenticated staff route. Returns the customer's `MessageOut[]` oldest-first. Missing `customer_id` returns 422; unknown or cross-tenant customer returns 404.

### `GET /api/v1/portal-links/token/{token}/messages` — public, no auth

Lists only the resolved active token's own customer thread, oldest-first. Unknown, revoked, or expired tokens return 404. No caller-supplied customer id is accepted.

### `POST /api/v1/portal-links/token/{token}/messages` — public, no auth

Posts to only the resolved active token's own customer thread. Request body: `{ "body": "text" }`; response `201` is `MessageOut` with `sender_type: "customer"` and `sender_user_id: null`. A successful post creates exactly one `customer_message_received` activity event and one tenant-scoped `info` notification. Unknown/inactive token returns 404; invalid body returns 422 with no write or side effect.

`MessageOut`: `id`, `tenant_id`, `customer_id`, `sender_type`, nullable `sender_user_id`, `body`, `created_at`.

## Document routes (`app/documents/router.py`) — added Sprint 016 (ADR-032)

Client portal document upload/download — staff upload a file against a customer, downloadable by staff and (via the two public routes above) by that customer through their portal link. `Authorization: Bearer <token>` required on all three routes below, **not** `require_role`-gated — any authenticated tenant user, matching the customer/project/portal-link creation precedent. Upload security policy: 20MB max, enforced against actual bytes written; an explicit extension allowlist (`.pdf .doc .docx .xls .xlsx .txt .jpg .jpeg .png .heic .webp`); the stored filename is always a generated `uuid4()`, never the client-supplied name (path traversal prevented by construction); the original filename is retained only as display/`Content-Disposition` metadata. See ADR-032 for the full rationale.

### `POST /api/v1/documents`

Uploads a file against a customer. `multipart/form-data`; `customer_id` is a query parameter, the file itself is the `file` form field.

**Response (201)** (`DocumentOut`):
```json
{
  "id": "...", "tenant_id": "...", "customer_id": "...", "uploaded_by_user_id": "...",
  "original_filename": "Contract Draft.pdf", "content_type": "application/pdf",
  "size_bytes": 48213, "created_at": "2026-08-16T14:20:06Z"
}
```
`storage_filename` (the on-disk name) is never included in this or any other response.

**Response (404):** `{ "detail": "Customer not found" }` — `customer_id` must belong to the caller's own tenant (ADR-029's relationship-linkage-bypass check).
**Response (413):** `{ "detail": "File exceeds the 20MB limit" }` — checked against actual bytes written, not a trusted `Content-Length` header.
**Response (422):** `{ "detail": "File type '.exe' is not allowed" }` — extension not on the allowlist.

### `GET /api/v1/documents`

| Query param | Type | Default |
|---|---|---|
| `customer_id` | uuid \| null | none — no filter, lists every document for the caller's tenant |

**Response** — array of `DocumentOut`, most recent first, scoped to the caller's tenant.

### `GET /api/v1/documents/{document_id}/download`

**Response (200):** `Content-Type: <the stored content_type>`, `Content-Disposition: attachment; filename="<original_filename>"`, raw file bytes.
**Response (404):** `{ "detail": "Document not found" }` — unknown id, or a document belonging to a different tenant (not `403` — a cross-tenant lookup can't confirm another tenant's document exists).

---

## User management routes (`app/users/router.py`) — added Sprint 015 (ADR-031)

Team management: an Owner can list their tenant's team and deactivate a Staff member's access. Both routes require `Authorization: Bearer <token>` **and** an `Owner` role (`require_role(UserRole.OWNER)`) — `403` (`{"detail": "Insufficient permissions"}`) for a valid token belonging to a `Staff` user, same as `/api/v1/invitations*`. Deactivation is soft — `users.is_active` flips to `false`, the row is never deleted (ADR-031) — and it does **not** cascade to that user's portal links, which keep working.

### `GET /api/v1/users`

Lists every user in the caller's own tenant.

**Response (200)** — array of `TeamMemberOut`:
```json
[{ "id": "...", "name": "Sarah Whitfield", "email": "sarah@acme.test", "role": "Owner", "is_active": true, "created_at": "2026-08-15T07:02:30Z" }]
```

### `POST /api/v1/users/{user_id}/deactivate`

Deactivates a teammate's access. Logs an `ActivityEvent` (`team_member_deactivated`) on success.

**Response (200)** (`TeamMemberOut`): the updated row, `is_active: false`.
**Response (409):** `{ "detail": "You cannot deactivate your own account." }` — self-deactivation, checked before any lookup.
**Response (404):** `{ "detail": "User not found" }` — unknown `user_id`, or one belonging to a different tenant (same response for both, so a cross-tenant lookup can't confirm another tenant's user exists — ADR-028 precedent).

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

Sprint 018 preserves every JSON error body below. Correlation is carried in the `X-Request-ID` response header rather than by changing response schemas. Unexpected exceptions emit a structured `unhandled_exception` record containing the request ID, method, safe route template, and exception type; the response and routine logs never expose a stack trace, raw exception message, authorization header, request body, query string, or concrete token-bearing URL.

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
| GET | `/ready` | Sprint 018 | Yes — connectivity probe only | No |
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
| POST | `/api/v1/portal-links` | Sprint 013 | Yes | **Yes** (any tenant user, not Owner-only) |
| GET | `/api/v1/portal-links` | Sprint 013 | Yes | **Yes** |
| DELETE | `/api/v1/portal-links/{portal_link_id}` | Sprint 013 | Yes | **Yes** |
| GET | `/api/v1/portal-links/token/{token}` | Sprint 013 | Yes | No (customer has no account) |
| GET | `/api/v1/portal-links/token/{token}/invoice/{quote_id}` | Sprint 013 | Yes | No (customer has no account) |
| POST | `/api/v1/documents` | Sprint 016 | Yes | **Yes** (any tenant user, not Owner-only) |
| GET | `/api/v1/documents` | Sprint 016 | Yes | **Yes** |
| GET | `/api/v1/documents/{document_id}/download` | Sprint 016 | Yes | **Yes** |
| GET | `/api/v1/portal-links/token/{token}/documents` | Sprint 016 | Yes | No (customer has no account) |
| GET | `/api/v1/portal-links/token/{token}/documents/{document_id}/download` | Sprint 016 | Yes | No (customer has no account) |
| POST | `/api/v1/messages?customer_id={customer_id}` | Sprint 017 | Yes | **Yes** (any tenant user, not Owner-only) |
| GET | `/api/v1/messages?customer_id={customer_id}` | Sprint 017 | Yes | **Yes** |
| GET | `/api/v1/portal-links/token/{token}/messages` | Sprint 017 | Yes | No (customer has no account) |
| POST | `/api/v1/portal-links/token/{token}/messages` | Sprint 017 | Yes | No (customer has no account) |
| GET | `/api/v1/users` | Sprint 015 | Yes | **Yes** (`require_role(OWNER)`) |
| POST | `/api/v1/users/{user_id}/deactivate` | Sprint 015 | Yes | **Yes** (`require_role(OWNER)`) |
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
