# Sprint 016 — Client Portal Documents (Upload/Download)

**Status:** ✅ Done. Implemented and verified against the real backend test suite, the frontend build/lint/typecheck, `alembic check` (including an explicit `upgrade`/`downgrade`/`upgrade` round-trip), and a manual smoke test against the real running app (uvicorn + local PostgreSQL 16). Not yet committed as of this writing — held per explicit user instruction until the full implementation and final verification were green.

## Objective

`docs/USER_ROLES.md`/`docs/SYSTEM_ARCHITECTURE.md`'s portal notes and `docs/SPRINTS/sprint-013.md`'s original scoping decision (ADR-030) all flag the same deferral: a read-only client portal shipped in Sprint 013 covering project/quote tracking only, with documents and messaging deliberately deferred. That deferral was named again in Sprint 014's follow-up list and again in Sprint 015's — three sprints running, the strongest "what's actually next" signal anywhere in this repo's history. Sprint 016 closes the documents half: staff can upload a file against a customer, and that customer can see and download it through their existing portal link, no account, no login.

`docs/ROADMAP.md`'s literal Sprint 016 line ("AI Renovation Planner / Design Assistant / Stone Visualiser; full observability; security hardening; subscription billing") is stale and untouched — `docs/SYSTEM_ARCHITECTURE.md` itself notes its roadmap table predates the SaaS replan and has not been reconciled with actual delivery. `docs/ROADMAP.md` is not modified by this sprint.

## Scope delivered

**Backend**
- Migration `b0bddd0fb66b`: new `documents` table (`id`, `tenant_id`, `customer_id`, `uploaded_by_user_id`, `original_filename`, `storage_filename`, `content_type`, `size_bytes`, `created_at`), additive-only.
- `app/core/config.py`: new `upload_dir` setting (`./uploads`, local disk, created on startup if missing).
- `requirements.txt`: new dependency `python-multipart==0.0.20`, required for FastAPI's `UploadFile` — not previously installed, flagged explicitly rather than silently added.
- New module `app/documents/` (`models.py`, `service.py`, `router.py`):
  - `service.py`: `upload_document()` validates `customer_id` under the caller's tenant (ADR-029 relationship-bypass check, reused from `PortalService.create_link()`), validates the extension against an explicit allowlist (`.pdf .doc .docx .xls .xlsx .txt .jpg .jpeg .png .heic .webp`), streams the file to disk in bounded chunks enforcing a 20MB cap against actual bytes written (not a trusted `Content-Length`), and stores it under a generated `uuid4()` filename — the user-supplied filename is never used as a path. `list_documents()`, `get_document()` (tenant-scoped), `file_path()`.
  - `router.py`: `POST /api/v1/documents` (upload), `GET /api/v1/documents` (list), `GET /api/v1/documents/{id}/download` (staff download) — none `require_role`-gated, matching customer/project/portal-link creation precedent.
- `app/database/crud.py`: `create_document`, `get_document_by_id`, `list_documents`.
- Two new public routes added to the **existing** `app/portal/router.py` (not a new router) — `GET /token/{token}/documents` and `GET /token/{token}/documents/{document_id}/download` — mirroring the existing invoice-download route's exact shape. `PortalService` gained `list_customer_documents()`/`get_customer_document()`, matching `get_customer_quote()`'s pattern: active-token requirement, match on both `tenant_id` AND `customer_id`, one shared `PortalLinkNotFoundError` for every failure.
- `app/api/v1/__init__.py`: mounted the new `documents` router.
- Every download route (staff and public) forces `Content-Disposition: attachment` — no route serves a file inline.
- `DocumentOut` deliberately excludes `storage_filename` — the on-disk name is never exposed to any client.

**Frontend**
- `apps/web/app/customers/[id]/page.tsx` gains a "Documents" card: a file-input upload control and a list of previously uploaded documents (filename, size, upload date, download button).
- `apps/web/app/portal/[token]/page.tsx` gains a Documents section: a read-only list with download buttons, fetched independently of the existing `getPortalByToken` call so a failed documents fetch can't block the projects/quotes view.
- New `apps/web/types/document.ts`; `apps/web/lib/api.ts` gains `uploadDocument`, `getDocuments`, `downloadDocument` (authenticated) and `getPortalDocuments`, `downloadPortalDocument` (public) — downloads use the existing blob-fetch-and-save pattern (`downloadInvoice`/`downloadPortalInvoice`), not a bare URL.
- Both new list-render conditions deliberately do not gate on the error state (`{documents && documents.length > 0 && (...)}`, no `!documentsError` in the guard) — carrying forward the lesson from Sprint 014's final review, which caught the opposite bug there.

**Docs**
- `docs/DECISIONS.md` — new ADR-032: local-disk storage and its stated limitation, generated-filename rationale, the complete upload security policy, customer-level attachment, and the route-placement decision.
- `docs/USER_ROLES.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md` — updated: new module/routes, `upload_dir` setting, the "documents" half of the portal gap now closed (messaging still open).
- `docs/ROADMAP.md` — **not touched**, same precedent as Sprints 012–015.

## Test-suite coverage

12 new tests in `tests/test_documents.py`:
- `test_upload_document_success` — valid upload succeeds, returns the correct metadata, never exposes `storage_filename`.
- `test_upload_document_cross_tenant_customer_returns_404` — a `customer_id` belonging to a different tenant is rejected.
- `test_upload_document_too_large_returns_413` — a file over 20MB is rejected, nothing persisted.
- `test_upload_document_disallowed_extension_returns_422` — a `.exe` upload is rejected, nothing persisted.
- `test_list_documents_is_tenant_scoped` — staff list is scoped to the caller's tenant.
- `test_download_document_success` — staff download returns the correct bytes with a forced-download header.
- `test_download_document_cross_tenant_returns_404` — a cross-tenant staff download attempt is rejected.
- `test_download_unknown_document_returns_404` — an unknown id is rejected.
- `test_portal_lists_only_that_customers_documents` — a portal token lists only its own customer's documents.
- `test_portal_downloads_document_successfully` — a portal token can download its own customer's document.
- `test_portal_cannot_download_another_customers_document` — a document belonging to a different customer in the *same* tenant, requested via a token scoped to a different customer, is rejected (the relationship-bypass check, distinct from cross-tenant isolation).
- `test_portal_revoked_link_cannot_access_documents` — a revoked portal link cannot list or download documents.

## Audit results

| Check | Result |
|---|---|
| `pytest` (157 tests: 145 pre-existing + 12 new) | ✅ 157 passed, 210 warnings (pre-existing deprecation warnings, unrelated to this sprint) |
| `alembic check` | ✅ "No new upgrade operations detected." |
| `alembic downgrade -1` / `upgrade head` round-trip | ✅ Clean — `b0bddd0fb66b` ↔ `dae9516f388b` |
| `pnpm lint` | ✅ 2 successful, 0 errors/warnings |
| `pnpm build` (includes Next.js's own TypeScript check — `apps/web` has no standalone `check-types` script) | ✅ Compiled clean, 15 routes, same count as Sprint 015's baseline — no new routes |
| `git diff --check` | ✅ exit 0, no whitespace/conflict-marker issues |
| Manual smoke test against the real running app (uvicorn + local Postgres, not the pytest TestClient) | ✅ Uploaded a real PDF as staff (original filename preserved in metadata, `storage_filename` never exposed); listed and downloaded it as staff (bytes matched, forced-attachment header); created a portal link and listed/downloaded the same document with no login; confirmed a `.exe` upload → 422 and a 20MB+1-byte upload → 413; revoked the portal link and confirmed both document routes then 404; confirmed the on-disk filename was a generated UUID, never the original name, for every file written during this session |

## Follow-up items raised, not part of Sprint 016 scope

- Messaging/chat for the client portal — the other half of the gap deferred since Sprint 013, still unstarted.
- Content-sniffing/magic-byte validation beyond the extension allowlist — an accepted, documented gap (ADR-032), not fixed here.
- Virus scanning, S3/object storage, storage quotas — all explicitly deferred per user instruction for this sprint.
- File versioning or editing — upload-and-download only.
- The pre-existing `EmailAlreadyRegisteredError`/`is_active` interaction (Sprint 015's follow-up) remains unaddressed.
- `docs/ROADMAP.md`'s stale Sprint 008–016 table remains unreconciled.
- Sprint 017 is not started.
