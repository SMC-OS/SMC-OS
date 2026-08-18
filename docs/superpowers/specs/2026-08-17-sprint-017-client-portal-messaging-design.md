# Sprint 017 Design — Client Portal Messaging

**Status:** Approved for implementation (design phase only — not yet implemented/committed as of this writing)
**Date:** 2026-08-17
**Depends on:** Sprint 016 (commit `37ddc25`, closed and pushed — not reopened by this sprint)

## 1. Objective

Close the last remaining piece of the client-portal gap originally scoped at Sprint 013 (tracking + documents + messaging), deliberately deferred there (ADR-030) and named again in Sprint 014's, Sprint 015's, and Sprint 016's own "Follow-up items" sections — four sprints running, the same repeated-flagging pattern that justified choosing documents for Sprint 016. Sprint 017 closes messaging: staff and a customer exchange text messages tied to that customer, through the same no-account/no-login portal-link mechanism already used for tracking, invoice download, and document download.

## 2. Reconciliation against the roadmap

`docs/ROADMAP.md` has no Sprint 017 line at all — it stops at Sprint 016, and Sprints 012–016 have already diverged substantially from that table's content, confirmed by `docs/SYSTEM_ARCHITECTURE.md`'s own §9 footnote ("reflects the pre-SaaS-replan draft and has not yet been reconciled"). The roadmap's original Sprint 013 "Client Portal" line bundled tracking + documents + messaging; Sprint 013 scoped down to tracking only, Sprint 016 closed documents. This sprint closes the third and final piece deferred since then. Reconciling the roadmap table itself remains a separate, out-of-scope documentation decision (same precedent as Sprints 012–016). `docs/ROADMAP.md` is **not modified** by this sprint.

## 3. User/business outcome

A customer can send a message to staff and read staff replies through their existing portal link — no account, no login. Staff can do the same from the customer's detail page. Both sides see new messages appear without a manual page reload while the thread is open (5-second polling, matching the rest of this app's live-feeling panels).

## 4. Exact scope and deliverables

**Backend**
- New `messages` table: `id`, `tenant_id` (NOT NULL FK), `customer_id` (NOT NULL FK — customer-level, not project-level, matching `PortalLink`/`Document` precedent; see §18 point 3), `sender_type` (`"staff"` | `"customer"`, NOT NULL), `sender_user_id` (FK → users, **nullable** — populated only for staff-authored messages; always `NULL` for customer-authored messages, since a customer has no `users` row per ADR-030), `body` (text, NOT NULL, server-enforced 5,000-character cap), `created_at`.
- New module `app/messages/` (`models.py`, `service.py`, `router.py`), following the one-module-per-concern convention every prior module uses.
  - `service.py`: `MessageService` — `create_staff_message(db, *, tenant_id, customer_id, sender_user_id, body) -> Message`, validating `customer_id` resolves under the caller's tenant (ADR-029's relationship-bypass pattern, reused from `PortalService.create_link()`/`DocumentService.upload_document()`) and the body policy (§5). `list_messages(db, tenant_id, customer_id) -> list[Message]`, ascending by `created_at` (oldest first — a conversation, not a file list; contrast with Documents' "most recent first").
  - `router.py`: `POST /api/v1/messages?customer_id=` (`201`, any authenticated tenant user, not Owner-gated — matches customer/project/portal-link/document creation precedent) and `GET /api/v1/messages?customer_id=` (`200`; `customer_id` is a **required** query parameter — unlike Documents' optional filter, a message thread is meaningless without a customer scope; omitting it is a `422`, FastAPI's own required-query-param validation).
- `app/portal/service.py`: `PortalService` gains `list_customer_messages(db, token) -> list[Message]` and `post_customer_message(db, token, body) -> Message`, mirroring `get_customer_quote()`'s/`list_customer_documents()`'s exact shape: active-token requirement, `tenant_id`/`customer_id` resolved from the token row only (never from caller input — there is no caller-supplied `customer_id` on either public route, removing the "different customer in the same tenant" bypass class that exists for the documents-by-id download route), one shared `PortalLinkNotFoundError` for every failure. `post_customer_message()` additionally logs an `ActivityEvent` and creates a `Notification` on success (§7).
- `app/portal/router.py`: two new public routes — `GET /token/{token}/messages` (`200`) and `POST /token/{token}/messages` (`201`) — mirroring the existing invoice-download and Sprint 016 document routes' exact shape. Both status codes match their staff-side counterparts exactly, so the frontend's `postMessage`/`postPortalMessage` methods can share identical response-handling logic.
- `app/activity/models.py`: new `ActivityType.CUSTOMER_MESSAGE_RECEIVED` value.
- `app/api/v1/__init__.py`: mount the new `messages` router.

**Frontend**
- Customer detail page (`apps/web/app/customers/[id]/page.tsx`) gains a "Messages" card: a scrollable thread (sender-side styling driven by `sender_type`, not a resolved name — see §5) and a text input + Send button. Polls every 5s while mounted, via the existing `usePolling` primitive (`hooks/usePolling.ts`), matching the dashboard/activity/notifications panels' established pattern (Design Principle #6: polling now, swappable for real-time later).
- `apps/web/app/portal/[token]/page.tsx` gains a Messages section inside the existing `portal.status === "active"` content block, same thread + input pattern, same 5s polling, fetched independently of the existing `getPortalByToken`/`getPortalDocuments` calls so one failing fetch never blocks another.
- New `apps/web/types/message.ts`; `apps/web/lib/api.ts` gains `getMessages`, `postMessage` (authenticated) and `getPortalMessages`, `postPortalMessage` (public).
- Message body is rendered as **plain text only** — no `dangerouslySetInnerHTML`, no markdown parsing, line breaks preserved via CSS (`whitespace-pre-wrap`), not by interpreting the string as HTML. This is a binding constraint (§5), not implementer discretion.

**Docs**
- `docs/DECISIONS.md` — new ADR-033: the messaging data model and why `sender_user_id` is nullable, the customer-level (not project-level) attachment decision, the notification/activity trigger on inbound customer messages, the plain-text-only rendering constraint and why, and the accepted no-rate-limiting gap.
- `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md` — updated: new module/routes, the client-portal gap (tracking + documents + messaging, all three now closed).
- `docs/ROADMAP.md` — **not touched**, same precedent as Sprints 012–016.

## 5. Message content policy (explicit, per your clarification)

This is the binding policy for this sprint — not a placeholder, not left to implementer judgment:

- **Maximum body length: 5,000 characters.** Enforced server-side (Pydantic field validation on `MessageCreate.body`); a request exceeding this is rejected with `422`, nothing persisted.
- **Empty or whitespace-only bodies are rejected with `422`**, nothing persisted — the body is stripped before the length/emptiness check, but the stored value is the original (unstripped) body, not the stripped one, matching how no other module in this codebase silently mutates user-supplied text before storing it.
- **Plain text only.** No markdown rendering, no rich text, no HTML interpretation on either the backend or the frontend. The frontend renders `message.body` as a plain React text node (JSX's default escaping), never via `dangerouslySetInnerHTML` — this is the sole XSS mitigation for this feature and is treated as load-bearing, not incidental.
- **No file attachments this sprint.** Documents already have their own dedicated upload flow (Sprint 016, ADR-032); attaching a file to a message would either duplicate that upload/security surface or require a document-picker UI referencing an existing `Document` row — real additional scope this sprint doesn't take on.
- **No per-message read/unread state.** The Notification created on each inbound customer message (§7) already gives staff an unread/read signal at the notification level; a second read-tracking mechanism on the message row itself would be redundant for this sprint's scope.
- **No editing or deleting a sent message** — post-and-read only, matching the upload-and-download-only precedent Documents established (ADR-032) and the create-and-revoke-only precedent Invitations/PortalLinks established.
- **No resolution of a staff sender's display name.** `MessageOut` exposes `sender_type` (`"staff"` | `"customer"`) and `sender_user_id` (the raw id, nullable), not a joined/resolved name — no other `*Out` model in this codebase resolves a `*_user_id` column to a display name either (`DocumentOut` exposes only `uploaded_by_user_id`). The frontend distinguishes "you" / "staff" / "the customer" using `sender_type` plus (on the authenticated side) comparing `sender_user_id` to the signed-in user's own id where relevant, not a resolved name.
- **No rate limiting on the public `POST /token/{token}/messages` route this sprint.** No rate limiting exists anywhere in this application today, so this isn't a new hole relative to the rest of the API surface — but it is worth naming explicitly rather than leaving it a silent gap, since this is the first public route in this codebase that lets an anonymous caller (anyone holding a valid portal link) write new rows on every request rather than only read them.
- **No WebSockets/SSE this sprint.** Both new UI surfaces poll every 5 seconds via the existing `usePolling` primitive, per Design Principle #6 (polling now, swappable for a real-time layer later without touching consuming components).

## 6. Storage

No new storage concern — this table holds text rows only, in the existing PostgreSQL database, same as every other business-data table. No local-disk or object-storage question exists for this sprint (contrast with Sprint 016's documents, which needed one).

## 7. Notification and Activity behavior on inbound customer messages

When a customer posts a message via `POST /token/{token}/messages` (and only then — a staff-authored message via `POST /api/v1/messages` does **not** trigger either of these, matching how no other module notifies staff of their own actions):

- `PortalService.post_customer_message()` logs one `ActivityEvent` (`ActivityType.CUSTOMER_MESSAGE_RECEIVED`), tagged with the token's own `tenant_id`, title "New message from a customer", description including the customer's name (resolved via the token row's `customer_id`, the same lookup `get_customer_quote()`/`list_customer_documents()` already perform) — matching the log-on-consequential-action convention every other module follows (`customer_added`, `quote_created`, `team_member_deactivated`).
- It also creates exactly one `Notification` (`type: "info"`), tagged with the same `tenant_id`, so the new message shows up in the bell dropdown for every user in that tenant — `notification_service.create()` already takes `tenant_id` (not a per-user target; no module in this codebase creates a notification scoped to one specific user), but every existing call to it comes from `app/notifications/router.py`'s own `POST` handler or `seed.py`'s startup seeding. **This sprint is the first to call `notification_service.create()` as a side effect of another module's business logic**, not from the notifications HTTP layer itself — worth calling out plainly rather than implying an existing precedent that isn't there.
- The `ActivityEvent` call, by contrast, does match an established pattern: `app/customers/service.py`, `app/quotes/service.py`, `app/projects/service.py`, and `app/users/service.py` (Sprint 015) already call `activity_service.log()` directly, in-process, from within another module's service layer, not via an HTTP call. `PortalService.post_customer_message()` follows that same, already-precedented shape for the `ActivityEvent` half only.
- If the message body fails validation (§5), no `Message` row, no `ActivityEvent`, and no `Notification` are created — the validation happens before any of the three writes.

## 8. Backend/API work

Four new routes (2 staff-facing: post, list; 2 public: post, list), one new module, one new `ActivityType` enum value, no changes to any existing route.

## 9. Frontend work

Two pages extended (`/customers/[id]` gains a Messages card; `/portal/[token]` gains a Messages section). No other page changes. Four new API client methods, one new type file. Both new UI surfaces poll every 5s while mounted (§5).

## 10. Database/migration work

One additive table (`messages`). No changes to any existing table, column, or constraint.

## 11. Auth/RBAC requirements

No `require_role` usage — staff post/list are any authenticated tenant user, matching the precedent every other creation-style route in this codebase already sets (customers, projects, quotes, portal links, documents). No new permission checks beyond the existing `get_current_user` gate.

## 12. Tenant-isolation requirements

`messages` filtered by `tenant_id` everywhere (ADR-029 convention). `customer_id` validated against the caller's own tenant at staff-post time (ADR-029's relationship-bypass check, reused pattern). Staff `GET /api/v1/messages` requires `customer_id` and is tenant-scoped — a cross-tenant `customer_id` reads as `404` (ADR-028 precedent). Public routes resolve `tenant_id`/`customer_id` from the token row itself, **never from caller input** — neither public route accepts a `customer_id` parameter at all, which removes the "different customer in the same tenant, requested via a token scoped to a different customer" bypass class that exists for Documents' by-id download route (there is no id for an attacker to substitute; the entire thread is implicitly scoped to the token's own customer). A revoked or expired token reads as `404` on both the list and post routes, matching the existing portal-status derivation (`PortalService.derive_status()`) every other portal content type already uses.

## 13. Security considerations

Covered in full in §5 and §12. Summary: tenant/customer isolation enforced identically to every prior portal-adjacent module; no path-traversal or file-storage surface (text-only, no attachments); XSS closed by rendering the message body as a plain React text node only, never interpreted as HTML/markdown; a 5,000-character server-enforced cap bounds storage growth from the public, anonymous-write endpoint; empty/whitespace-only bodies rejected before any write; revoked/expired tokens produce no access, no leak, and no write. No rate limiting is implemented this sprint — an accepted, explicitly named gap (§5), not a silent one.

## 14. Tests and acceptance criteria

- Staff posts a message for their own tenant's customer → `201`, persisted, `sender_type: "staff"`, `sender_user_id` = the caller's own id.
- Staff posts with a `customer_id` belonging to a different tenant → `404`, nothing persisted.
- Staff posts an empty or whitespace-only body → `422`, nothing persisted.
- Staff posts a body over 5,000 characters → `422`, nothing persisted.
- Staff lists messages for a customer → tenant-scoped, ascending order (oldest first), correct set.
- Staff lists messages without a `customer_id` query param → `422` (required parameter).
- Portal token lists messages → only that token's own customer's messages, ascending order.
- Portal token posts a message → `201`, `sender_type: "customer"`, `sender_user_id: null`; exactly one new `ActivityEvent` (`customer_message_received`) and exactly one new `Notification` are created, both tagged with the token's own tenant.
- Portal token posts an empty or over-length body → `422`, nothing persisted, and no `ActivityEvent`/`Notification` created.
- A revoked or expired portal token → both the list and post routes `404`, no leak, no write.
- A staff-authored message does **not** create an `ActivityEvent` or `Notification` (only inbound customer messages do — §7).
- Frontend: `pnpm lint`/`pnpm build` clean; both new polling effects start on mount and are torn down on unmount (no leaked interval — verified via diff-level review at minimum, live smoke test if practical, matching Sprints 014–016's verification depth).
- Migration: `alembic check` clean, `upgrade head`/`downgrade -1`/`upgrade head` round-trip clean, autogenerate detects only the one new table.

## 15. Exact files/modules likely affected

- `alembic/versions/<new>_add_messages_table.py` (new)
- `app/database/models.py` (modify: new `Message` model)
- `app/database/crud.py` (modify: message CRUD helpers)
- `app/messages/__init__.py`, `app/messages/models.py`, `app/messages/service.py`, `app/messages/router.py` (new)
- `app/portal/service.py` (modify: `list_customer_messages`, `post_customer_message`)
- `app/portal/router.py` (modify: two new public routes)
- `app/activity/models.py` (modify: new `ActivityType.CUSTOMER_MESSAGE_RECEIVED`)
- `app/core/config.py` — **not modified** (no new setting needed; contrast with Sprint 016's `upload_dir`)
- `app/api/v1/__init__.py` (modify: mount)
- `apps/web/app/customers/[id]/page.tsx` (modify: Messages card)
- `apps/web/app/portal/[token]/page.tsx` (modify: Messages section)
- `apps/web/types/message.ts` (new)
- `apps/web/lib/api.ts` (modify: four new methods)
- `tests/test_messages.py` (new)
- `docs/DECISIONS.md`, `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md` (modify)
- `docs/SPRINTS/sprint-017.md`, `docs/CHANGELOG.md` (new/modify, written after implementation)
- `docs/ROADMAP.md` — **not touched**

## 16. Dependencies and blockers

Depends only on Sprint 016 (done, pushed) and Sprint 013's portal token mechanism. No new third-party dependency expected — this sprint needs no file-upload/multipart handling (contrast with Sprint 016's `python-multipart`); if the implementation plan discovers otherwise, it must be called out explicitly rather than silently added, same standard Sprint 016 held itself to.

## 17. Explicit OUT OF SCOPE

- File attachments on messages (per your instruction) — documents already have their own upload flow.
- Per-message read/unread state (per your instruction) — the Notification created per inbound message already signals this at the notification level.
- WebSockets/SSE or any other real-time push (per your instruction) — 5-second polling only, via the existing `usePolling` primitive.
- Rate limiting on the public post route (per your instruction) — an accepted, explicitly flagged gap.
- Editing or deleting a sent message — post-and-read only.
- Resolving a staff sender's display name on `MessageOut` — `sender_type`/`sender_user_id` only.
- Any change to portal token design, auth, or tenant-isolation semantics established in ADR-029/ADR-030.
- Markdown or rich-text rendering — plain text only (per your instruction).
- The smaller flagged backlog items not chosen for this sprint: the `EmailAlreadyRegisteredError`/`is_active` interaction (Sprint 015, re-flagged Sprint 016), a reactivation endpoint for a deactivated teammate (Sprint 015), content-sniffing/magic-byte validation on document uploads (Sprint 016, ADR-032's accepted gap), and the supplier database + purchasing workflow (flagged unaddressed in Sprint 015's follow-ups).
- `docs/ROADMAP.md` changes.
- Sprint 018 or any work beyond this scope.

## 18. Architectural decisions requiring approval

Resolved during brainstorming and this clarification round — recorded here for the ADR, not open questions:
1. Messaging (closing the last piece of the original client-portal scope) is this sprint's focus — confirmed with the user, chosen over a hardening/bug-fix bundle and over the supplier/purchasing workflow.
2. Bidirectional messaging (not staff-to-customer-only announcements) — confirmed with the user.
3. Customer-level (not project-level) threads — matches `PortalLink`/`Document` precedent, confirmed with the user.
4. 5-second polling while a thread is open, reusing `usePolling` — confirmed with the user, over a load-once-and-refresh-after-send alternative.
5. Inbound customer messages create both a `Notification` and an `ActivityEvent` — confirmed with the user, over activity-only or neither.
6. Text-only messages, no attachments this sprint — confirmed with the user.
7. New `app/messages/` module for staff-side routes, with the two public routes on `app/portal/router.py` — confirmed with the user, over folding staff-side routes into `app/portal/` itself.
8. The full message content policy in §5 (5,000-char cap, plain-text rendering, no read state, no editing/deleting, no name resolution, no rate limiting) — presented as defaults matching established precedent, not objected to.

**New ADR required:** yes, ADR-033 — the first bidirectional, publicly-writable data flow in this codebase (every prior public route was either read-only or, for documents, a bounded binary upload with its own distinct security model); not a mechanical application of an already-decided convention.

## 19. Verification strategy

1. `pytest` — full suite, confirm new `tests/test_messages.py` cases pass alongside all pre-existing tests.
2. `alembic check` and an explicit `upgrade head` / `downgrade -1` / `upgrade head` round-trip.
3. `pnpm lint`, `pnpm build` (frontend TypeScript check happens inside build, per this repo's established pattern).
4. Manual/API-level smoke test against the real running app: post a message as staff, confirm it appears on the portal page within one poll interval; post a message as the customer (via the portal link), confirm it appears on the staff customer page within one poll interval, confirm exactly one new Notification and one new ActivityEvent were created; confirm a revoked/expired token can't list or post; confirm an empty and an over-length body are both rejected with nothing persisted.
5. Manual render check: confirm a message body containing `<script>`-like text renders as literal visible text on both pages, not executed — the concrete verification of §5's plain-text-rendering constraint.
6. `git diff --check` across the full range.
7. Scope-creep check: diff stat against the file list in §15 — no unlisted file should appear, and confirm no file-upload/attachment code, no rate-limiting code, and no WebSocket/SSE code was added.

## Notes on process

This design was produced via the Superpowers brainstorming workflow (architectural path), continuing directly from the already-completed and pushed Sprint 016 work (commit `37ddc25`) — a new, independent planning cycle, not a reopening of Sprint 016. Research was performed directly against the repository (`docs/SPRINTS/sprint-016.md`, the Sprint 016 design spec and implementation plan, `docs/ROADMAP.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/USER_ROLES.md`, `docs/API_SPEC.md`, `docs/DECISIONS.md`'s ADR-028 through ADR-032, and `docs/SPRINTS/sprint-015.md`'s follow-up list), not delegated to a subagent. Eight scope decisions were confirmed explicitly with the user, one question at a time, before this spec was written (see §18). Per explicit instruction, no application files were modified, no code implemented, no implementation plan written, and nothing committed or pushed as part of producing this design. Sprint 018 was not started. `docs/ROADMAP.md` was not modified. Sprint 016 was not reopened or re-audited.
