# Sprint 016 Design — Client Portal Documents (Upload/Download)

**Status:** Approved for implementation (design phase only — not yet implemented/committed as of this writing)
**Date:** 2026-08-15
**Depends on:** Sprint 015 (commit `3117457`, closed and pushed — not reopened by this sprint)

## 1. Objective

Close the documents half of the client-portal gap deliberately deferred at Sprint 013's original scoping decision, and named again in both Sprint 014's and Sprint 015's "Follow-up items" sections — the most repeatedly-flagged concrete gap anywhere in this repo's sprint history. Messaging (the other deferred half) remains out of scope; it was considered and not chosen (see design options presented during brainstorming).

## 2. Reconciliation against the roadmap

`docs/ROADMAP.md`'s literal Sprint 016 line ("AI Renovation Planner / Design Assistant / Stone Visualiser; full observability; security hardening; subscription billing") is stale and untouched by this sprint — confirmed via `docs/SYSTEM_ARCHITECTURE.md`'s own note that its §9 roadmap table "reflects the pre-SaaS-replan draft and has not yet been reconciled" with actual delivery. `docs/ROADMAP.md`'s original Sprint 013 "Client Portal" line bundled tracking + documents + messaging; Sprint 013 deliberately scoped down to tracking only. This sprint closes one of the two pieces deferred then — documents, not messaging. Reconciling the roadmap table itself remains a separate, out-of-scope documentation decision (same precedent as Sprints 012–015).

## 3. User/business outcome

Staff can upload a file (a contract, a spec sheet, a job-site photo) against a customer; that customer sees and downloads it through their existing portal link, with no account and no login — extending the same no-account access model Sprint 013 built for project/quote status and invoice download.

## 4. Exact scope and deliverables

**Backend**
- New `documents` table: `id`, `tenant_id` (NOT NULL FK), `customer_id` (NOT NULL FK — customer-level, not project-level; see §16), `uploaded_by_user_id` (NOT NULL FK → users), `original_filename` (display/metadata only, never used as a filesystem path), `storage_filename` (the generated UUID-based name actually used on disk), `content_type`, `size_bytes`, `created_at`.
- New module `app/documents/` (`models.py`, `service.py`, `router.py`), following the one-module-per-concern convention every prior module uses.
  - `service.py`: `upload_document(db, *, tenant_id, uploaded_by_user_id, customer_id, file) -> Document`, validating `customer_id` resolves under the caller's tenant (ADR-029's relationship-bypass pattern, reused from `PortalService.create_link()`/`ProjectService.create()`), validating the upload policy (§5), writing the file to disk under a generated filename, and persisting the row. `list_documents(db, tenant_id, customer_id) -> list[Document]`. `get_document(db, tenant_id, document_id) -> Document | None` (tenant-scoped, for staff download). `get_document_for_portal(db, portal_link, document_id) -> Document | None` (scoped to the link's own `customer_id`, mirroring `PortalService`'s existing invoice-download check).
  - `router.py`: `POST /api/v1/documents` (upload, multipart form) and `GET /api/v1/documents?customer_id=` (list) — any authenticated tenant user, not Owner-gated (matches customer/project-creation and portal-link-creation precedent: routine work, not a tenant-control decision). `GET /api/v1/documents/{id}/download` (staff download, tenant-scoped). Public: `GET /api/v1/portal-links/token/{token}/documents` (list) and `GET /api/v1/portal-links/token/{token}/documents/{id}/download`, gated to the token's own `customer_id`, mirroring the existing `GET /api/v1/portal-links/token/{token}/invoice/{quote_id}` pattern exactly (same "resolve tenant/customer from the token row, never from caller input" convention).
- `app/core/config.py`: new `upload_dir: str` setting (a local directory path; created on startup if missing).
- `app/api/v1/__init__.py`: mount the new router.

**Frontend**
- Customer detail page (`apps/web/app/customers/[id]/page.tsx`) gains a "Documents" card: an upload form (file input + submit) and a list of previously uploaded documents (filename, size, uploaded date, download link) — same `Badge`/list pattern established in Sprint 014/015.
- `apps/web/app/portal/[token]/page.tsx` gains a Documents section: a list of available documents with download links, alongside the existing project/quote/invoice content.
- New `apps/web/types/document.ts`; `apps/web/lib/api.ts` gains `uploadDocument`, `getDocuments`, `downloadDocument` (authenticated) and `getPortalDocuments`, `downloadPortalDocument` (public).

**Docs**
- `docs/DECISIONS.md` — new ADR-032: local-disk storage choice and its acknowledged limitation (doesn't survive a redeploy to a new host, doesn't scale past single-instance — explicitly deferred, not a defect), the generated-filename-not-original-filename rationale, the customer-level (not project-level) attachment decision, and the explicit upload security policy (§5).
- `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md` — updated: new module/routes, `upload_dir` config, the "documents" half of the portal gap now closed (messaging still open).
- `docs/ROADMAP.md` — **not touched**, same precedent as Sprints 012–015.

## 5. Upload security policy (explicit, per your clarification)

This is the binding policy for this sprint — not a placeholder, not "reject dangerous files" left to implementer judgment:

- **Maximum file size: 20 MB.** Enforced server-side before the file is written to disk (checked against `Content-Length` and re-checked against actual bytes written, so a client lying about `Content-Length` can't bypass the cap). A request exceeding this is rejected with `413`.
- **Storage filename: a generated UUID (`uuid4()`), with the original extension preserved for the on-disk name only if that extension is itself on the allowlist below** (e.g. `a1b2c3d4-....pdf`) — the user-supplied filename is never used to construct a filesystem path, closing path traversal by construction (no `..`, no path separators, no user input in the path at all beyond the validated extension).
- **The original filename is preserved only as `Document.original_filename`** — database metadata, used solely for the list UI's display text and the `Content-Disposition` header's `filename=` parameter on download. It is never interpreted as a path.
- **Downloads always set `Content-Disposition: attachment; filename="<original_filename>"`.** No route ever serves an uploaded file inline, and the upload directory is never exposed as static/directly-servable content — the only way to retrieve a file's bytes is through the authenticated staff route or the token-gated public route, both of which set this header.
- **File type: an explicit allowlist, checked against the file's extension (case-insensitive) at upload time.** A file whose extension is not on this list is rejected with `422` before any bytes are written to disk. This is an allowlist, not a denylist — an allowlist can't be defeated by a dangerous extension nobody thought to list, which is the standard reason to prefer it here:
  - Documents: `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.txt`
  - Images: `.jpg`, `.jpeg`, `.png`, `.heic`, `.webp`
  - Explicitly excluded even though they're sometimes seen as "documents": `.svg` (has a real history of embedded-script XSS even when downloaded rather than rendered) and `.html`/`.htm` (never appropriate as a client-facing "document" in this context).
- **No content-sniffing/magic-byte validation this sprint** — the allowlist check is extension-based only. A user could rename a script to `.pdf` and it would pass the extension check; this is an accepted, explicit gap for this sprint (not a silent one) because: (a) the file is never executed or served inline by anything in this codebase regardless of its real content, (b) it is never placed anywhere web-servable outside the two authenticated/token-gated download routes, and (c) deeper content validation is real additional scope this sprint doesn't take on. Flagged explicitly in ADR-032 and in §16's out-of-scope list, not left implicit.
- **No virus scanning this sprint** (per your instruction) — flagged in ADR-032 as an accepted gap, not a silent one.
- **No S3/object storage this sprint** (per your instruction) — local disk only, per §6.
- **No storage quotas this sprint** (per your instruction) — no per-tenant or per-customer cap on total storage consumed.

## 6. Storage

Local disk (your decision), a new `upload_dir` setting in `app/core/config.py` (default e.g. `./uploads`, created on startup if missing, `.gitignore`d). Acknowledged limitation, stated plainly rather than glossed over: this does not survive a redeploy to a different host, and does not scale past a single running instance. Accepted for this sprint per your decision; revisiting it is real future work once real hosting is decided, not a defect to silently work around.

## 7. Backend/API work

Four new routes (2 staff-facing: upload, list; 1 staff download; 2 public: list, download — 5 total), one new module, one new config setting, no changes to any existing route.

## 8. Frontend work

Two pages extended (`/customers/[id]` gains a Documents card; `/portal/[token]` gains a Documents section). No other page changes. Five new API client methods, one new type file.

## 9. Database/migration work

One additive table (`documents`). No changes to any existing table, column, or constraint.

## 10. Auth/RBAC requirements

No `require_role` usage — upload/list/staff-download are any authenticated tenant user, matching the precedent every other creation-style route in this codebase already sets (customers, projects, quotes, portal links). No new permission checks beyond the existing `get_current_user` gate.

## 11. Tenant-isolation requirements

`documents` filtered by `tenant_id` everywhere (ADR-029 convention). `customer_id` validated against the caller's own tenant at upload time (ADR-029's relationship-bypass check, reused pattern). Staff `GET /documents/{id}/download` is tenant-scoped — a cross-tenant id reads as 404 (ADR-028 precedent). Public routes resolve `tenant_id`/`customer_id` from the token row itself, never from caller input (ADR-030's existing convention) — a document belonging to a different customer in the same tenant, requested via a token scoped to a different customer, reads as 404.

## 12. Security considerations

Covered in full in §5. Summary: path traversal closed by construction (generated filenames, no user input in the path), forced-download headers on every serving route (no inline rendering, no XSS-via-served-file), extension allowlist (not denylist) enforced before any bytes are written, size cap enforced server-side against actual bytes (not just a trusted header), and revoked/expired portal tokens produce no document access — matching the existing portal-status derivation (`PortalService.derive_status()`) other content types already use.

## 13. Tests and acceptance criteria

- Staff uploads a valid `.pdf` for their own tenant's customer → 201, row persisted, file exists on disk under a generated (non-original) filename.
- Staff uploads with a `customer_id` belonging to a different tenant → 404, nothing persisted, nothing written to disk.
- Staff uploads a file over 20MB → 413, nothing persisted, nothing written to disk.
- Staff uploads a file with a disallowed extension (e.g. `.exe`, `.svg`, `.html`) → 422, nothing persisted, nothing written to disk.
- Staff lists documents for a customer → tenant-scoped, correct set.
- Staff downloads a document → 200, `Content-Disposition: attachment` with the *original* filename, correct bytes.
- Staff downloads a document belonging to another tenant (cross-tenant id) → 404.
- Portal token lists documents → only that token's own customer's documents, none from another customer in the same tenant.
- Portal token downloads a document → 200, forced-download header, correct bytes.
- Portal token downloads a document belonging to a *different* customer in the same tenant → 404 (relationship-bypass check on the public path).
- A revoked or expired portal token → document routes produce no leak (matching existing derived-status behavior for other portal content).
- Frontend: `pnpm lint`/`pnpm build` clean; upload form and document lists render correctly (verified via diff-level review at minimum, live smoke test if practical, matching Sprints 014/015's verification depth).
- Migration: `alembic check` clean, `upgrade head`/`downgrade -1`/`upgrade head` round-trip clean, autogenerate detects only the one new table.

## 14. Exact files/modules likely affected

- `alembic/versions/<new>_add_documents_table.py` (new)
- `app/database/models.py` (modify: new `Document` model)
- `app/database/crud.py` (modify: document CRUD helpers)
- `app/documents/models.py`, `app/documents/service.py`, `app/documents/router.py` (new)
- `app/portal/router.py` (modify: two new public routes, or mounted from `app/documents/router.py` under the same `/portal-links` prefix — exact placement is an implementation-plan decision, not a design one)
- `app/core/config.py` (modify: `upload_dir` setting)
- `app/api/v1/__init__.py` (modify: mount)
- `apps/web/app/customers/[id]/page.tsx` (modify: Documents card)
- `apps/web/app/portal/[token]/page.tsx` (modify: Documents section)
- `apps/web/types/document.ts` (new)
- `apps/web/lib/api.ts` (modify: five new methods)
- `tests/test_documents.py` (new)
- `docs/DECISIONS.md`, `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md` (modify)
- `docs/SPRINTS/sprint-016.md`, `docs/CHANGELOG.md` (new/modify, written after implementation)
- `docs/ROADMAP.md` — **not touched**
- `.gitignore` (modify: exclude the local `uploads/` directory)

## 15. Dependencies and blockers

Depends only on Sprint 015 (done, pushed) and Sprint 013's portal token mechanism. Likely needs `python-multipart` for FastAPI's `UploadFile` form handling — the implementation plan must confirm whether it's already a dependency (`requirements.txt`) before assuming; if not already present, adding it is the one new package this sprint may require, and must be called out explicitly in the plan rather than silently added.

## 16. Explicit OUT OF SCOPE

- Messaging/chat for the client portal — still deferred (the other half of the gap this sprint doesn't close).
- File versioning or editing — upload-and-download only, no replace/update of an existing document.
- Virus scanning (per your instruction).
- S3/object storage (per your instruction).
- Storage quotas, per-tenant or per-customer (per your instruction).
- Content-sniffing/magic-byte validation beyond the extension allowlist (§5) — an accepted, explicitly-flagged gap, not a silent one.
- Project-level document attachment — customer-level only, matching `PortalLink`'s existing design (ADR-030's stated reasoning: avoids a project-picker UI, one customer's document list serves all their concurrent jobs).
- Any change to portal token design, auth, or tenant-isolation semantics established in ADR-029/ADR-030.
- `docs/ROADMAP.md` changes.
- Sprint 017 or any work beyond this scope.

## 17. Architectural decisions requiring approval

Resolved during brainstorming and this clarification round — recorded here for the ADR, not open questions:
1. Documents (not messaging) is this sprint's scope — confirmed with the user.
2. Local disk storage, not S3 — confirmed with the user, limitation stated plainly.
3. Customer-level (not project-level) attachment — matches `PortalLink` precedent, presented as a default and not objected to.
4. The full upload security policy in §5 — confirmed with the user, verbatim.

**New ADR required:** yes, ADR-032 — this is the first binary-upload feature in the codebase (new storage concern, new security surface), not an application of an already-decided convention.

## 18. Verification strategy

1. `pytest` — full suite, confirm new `tests/test_documents.py` cases pass alongside the existing 145.
2. `alembic check` and an explicit `upgrade head` / `downgrade -1` / `upgrade head` round-trip.
3. `pnpm lint`, `pnpm build` (frontend TypeScript check happens inside build, per this repo's established pattern).
4. Manual/API-level smoke test against the real running app: upload a document as staff, download it as staff, view/download it via a portal token, confirm a revoked/expired token can't access it, confirm an oversized/disallowed-extension upload is rejected.
5. Manual on-disk check: confirm the stored filename is a generated UUID, not the original filename, and that the original filename only appears in the DB row and the `Content-Disposition` header.
6. `git diff --check` across the full range.
7. Scope-creep check: diff stat against the file list in §14 — no unlisted file should appear, and confirm no messaging-related code was added.

## Notes on process

This design was produced via the Superpowers brainstorming workflow (architectural path), continuing directly from the already-completed and pushed Sprint 015 work (commit `3117457`) — a new, independent planning cycle, not a reopening of Sprint 015. Research was performed directly against the repository (`docs/ROADMAP.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/USER_ROLES.md`, `docs/API_SPEC.md`, `docs/SPRINTS/sprint-015.md`, `docs/DECISIONS.md`), not delegated to a subagent. Three scope decisions were confirmed explicitly with the user before this spec was written: (a) Sprint 016 = client portal documents, chosen over messaging and over the roadmap's larger stale items (billing, AI features); (b) local-disk storage, not S3; (c) the complete, explicit upload security policy in §5, provided verbatim by the user rather than left to implementer discretion.

Per explicit instruction, no application files were modified, no code implemented, no implementation plan written, and nothing committed or pushed as part of producing this design. Sprint 017 was not started. `docs/ROADMAP.md` was not modified. Sprint 015 was not reopened or re-audited.
