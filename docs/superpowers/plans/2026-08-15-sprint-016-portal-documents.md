# Sprint 016 — Client Portal Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let staff upload a file against a customer, and let that customer download it through their existing portal link — no account, no login — closing the documents half of the client-portal gap deferred since Sprint 013.

**Architecture:** A new `app/documents/` module owns upload/list/staff-download (crud, service, router — one-module-per-concern convention). The two customer-facing public routes live in `app/portal/router.py`, not `app/documents/router.py` — this repo's established convention: the existing invoice-download route (`GET /token/{token}/invoice/{quote_id}`) already lives in `app/portal/router.py` and calls into a sibling module (`app/quotes/pdf.py`) for its actual content; the two new document routes follow the identical shape, adding `list_customer_documents`/`get_customer_document` methods to `PortalService` itself (mirroring `get_customer_quote`'s exact validation pattern: active-token check, then a match against both `tenant_id` AND `customer_id`, one shared "not found" error for every failure so a caller can't distinguish cases) and calling `document_service.file_path()` to serve the file. Storage is local disk under a new `upload_dir` config path; the stored filename is always a generated UUID, never the user-supplied name.

**Tech Stack:** FastAPI/SQLAlchemy 2.0 backend (Python 3.12, `.venv`), Next.js 16/React 19 frontend (TypeScript, Tailwind v4, pnpm/Turborepo), pytest, Alembic, `python-multipart` (new dependency — required for FastAPI's `UploadFile`, not currently in `requirements.txt`).

**Spec:** `docs/superpowers/specs/2026-08-15-sprint-016-portal-documents-design.md`

## Global Constraints

- Upload security policy (spec §5), binding, not a placeholder:
  - Max file size: 20 MB, enforced against actual bytes written (not a trusted `Content-Length` header) — `413` on violation.
  - Storage filename: `uuid4()` + the validated extension. The user-supplied filename is NEVER used to construct a filesystem path.
  - Original filename: DB metadata only (`Document.original_filename`), used solely for display and the download `Content-Disposition`/`filename=` value.
  - Every download sets `Content-Disposition: attachment` — no route ever serves a file inline.
  - Extension allowlist ONLY: `.pdf .doc .docx .xls .xlsx .txt .jpg .jpeg .png .heic .webp`. Anything else → `422`. This is an allowlist, not a denylist — do not implement this as "block known-dangerous extensions."
  - No content-sniffing/magic-byte validation beyond the extension check (accepted, documented gap — do not add this).
  - No virus scanning, no S3/object storage, no storage quotas this sprint — do not add any of these.
- Documents are customer-level, not project-level. `Document.customer_id` is the only relationship column beyond `tenant_id`/`uploaded_by_user_id` — do not add a `project_id` column.
- No reactivation/versioning/editing of an uploaded document — upload and download only.
- No `require_role` usage anywhere in this module — any authenticated tenant user may upload/list/download (staff-side), matching customer/project/portal-link creation precedent.
- `docs/ROADMAP.md` must NOT be modified.
- New ADR-032 required in `docs/DECISIONS.md` (spec §17 — first binary-upload feature in this codebase).
- Sprint 015 (commit `3117457`) must not be reopened or modified.
- No messaging code of any kind — out of scope entirely (spec §16).
- Do not push to any remote at any point in this plan — commits are local only unless the user separately asks.

---

## Task 1: Database migration, `Document` model, and the new dependency

**Files:**
- Modify: `app/database/models.py` (new `Document` class)
- Modify: `app/core/config.py` (`upload_dir` setting)
- Modify: `requirements.txt` (add `python-multipart`)
- Modify: `.gitignore` (exclude the local `uploads/` directory)
- Create: `alembic/versions/<generated>_add_documents_table.py`

**Interfaces:**
- Consumes: nothing from an earlier task.
- Produces: `Document` ORM model, `settings.upload_dir` — consumed by Task 2's crud/service/router and Task 3's portal-side additions.

- [ ] **Step 1: Add `python-multipart` to `requirements.txt`**

FastAPI's `UploadFile`/multipart form parsing requires this package and it is not currently installed (confirmed absent from `requirements.txt`). Add it alphabetically:

```
python-multipart==0.0.20
```

Run: `.venv/Scripts/pip.exe install python-multipart==0.0.20` to install it into the existing venv (do not recreate the venv).

- [ ] **Step 2: Add the `Document` model**

In `app/database/models.py`, add a new class after `PortalLink`'s class definition:

```python
class Document(Base):
    """A file uploaded by staff against a customer, downloadable by staff
    and via that customer's portal link (Sprint 016, ADR-032). Customer-
    level, not project-level — same reasoning as PortalLink (ADR-030): one
    customer's document list serves all their concurrent jobs, no
    project-picker UI needed. storage_filename is a generated UUID-based
    name, never the user-supplied original_filename — original_filename is
    display/metadata only, never interpreted as a filesystem path (path
    traversal prevention by construction, see app/documents/service.py).
    No relationship() (repo convention) — every FK here is a plain column,
    resolved via explicit crud lookups.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_filename: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

`Integer`, `String`, `DateTime`, `ForeignKey`, `UUID`, `Mapped`, `mapped_column`, `func`, `uuid`, `datetime` are all already imported at the top of this file — no new imports needed.

- [ ] **Step 3: Add the `upload_dir` setting**

In `app/core/config.py`, inside `class Settings(BaseSettings):`, add after `portal_link_expire_days`:

```python
    # Sprint 016 (docs/DECISIONS.md ADR-032) — local disk directory for
    # uploaded client-portal documents. Created on startup if missing.
    # Deliberately NOT S3/object storage this sprint — accepted limitation:
    # does not survive a redeploy to a different host, does not scale past
    # one running instance. See ADR-032.
    upload_dir: str = "./uploads"
```

- [ ] **Step 4: Add `uploads/` to `.gitignore`**

Add a new line under the "Python (backend: app/)" section (or its own small section):

```
uploads/
```

- [ ] **Step 5: Generate the migration**

Run: `.venv/Scripts/python.exe -m alembic revision --autogenerate -m "add documents table"`

Expected: a new file under `alembic/versions/`. Open it and confirm it contains exactly one `op.create_table("documents", ...)` in `upgrade()` with all 8 columns (`id`, `tenant_id`, `customer_id`, `uploaded_by_user_id`, `original_filename`, `storage_filename`, `content_type`, `size_bytes`, `created_at` — 9 total including `id`), the 3 FK constraints (to `tenants`, `customers`, `users`), and the `unique=True` constraint on `storage_filename`; and exactly one `op.drop_table("documents")` in `downgrade()` — nothing else. If autogenerate detected any other change, stop and report it as a concern — that would mean pre-existing drift, not this task's job to fix.

- [ ] **Step 6: Round-trip verification**

Run, in order:
```
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic downgrade -1
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
```

Expected: all four succeed; the final check reports "No new upgrade operations detected."

- [ ] **Step 7: Commit**

```bash
git add app/database/models.py app/core/config.py requirements.txt .gitignore alembic/versions/
git commit -m "feat: Sprint 016 - add documents table, upload_dir setting, python-multipart dependency

Additive-only migration. Customer-level attachment (not project-level),
matching PortalLink's precedent. python-multipart is required for
FastAPI's UploadFile and was not previously a dependency."
```

---

## Task 2: Backend — `app/documents/` module (upload, list, staff download)

**Files:**
- Modify: `app/database/crud.py`
- Create: `app/documents/__init__.py` (empty, matches `app/users/__init__.py`/`app/invitations/__init__.py` convention)
- Create: `app/documents/models.py`
- Create: `app/documents/service.py`
- Create: `app/documents/router.py`
- Modify: `app/api/v1/__init__.py`
- Create: `tests/test_documents.py`

**Interfaces:**
- Consumes: `Document` model, `settings.upload_dir` (Task 1).
- Produces: `POST /api/v1/documents`, `GET /api/v1/documents`, `GET /api/v1/documents/{id}/download` — consumed by Task 4 (frontend `api.uploadDocument`/`getDocuments`/`downloadDocument`). `document_service.file_path(row) -> Path`, `document_service.get_document(db, tenant_id, document_id) -> Document` — consumed by Task 3's portal-side routes (via `document_service.file_path`, not `get_document` — Task 3 needs its own tenant+customer-scoped lookup, see Task 3's Interfaces).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_documents.py`:

```python
"""Sprint 016 — app/documents/ (docs/DECISIONS.md ADR-032).

Covers the full lifecycle through the HTTP layer: upload (success,
cross-tenant customer_id rejected, oversized rejected, disallowed
extension rejected), staff list/download, cross-tenant staff download
rejected. Portal-token-side access (list/download/isolation/revoked-link)
is covered separately in this same file once Task 3 adds those routes.
"""

import io
import uuid

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Document

TEST_CUSTOMER_NAME = "Pytest Documents Customer"


def _cleanup():
    db = SessionLocal()
    try:
        customer_ids = [
            row.id for row in db.query(Customer).filter(Customer.name == TEST_CUSTOMER_NAME).all()
        ]
        if customer_ids:
            db.execute(delete(Document).where(Document.customer_id.in_(customer_ids)))
        db.execute(
            delete(ActivityLog).where(ActivityLog.description == TEST_CUSTOMER_NAME)
        )
        db.execute(delete(Customer).where(Customer.name == TEST_CUSTOMER_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def created_customer(client, auth_headers):
    _cleanup()
    r = client.post("/api/v1/customers", json={"name": TEST_CUSTOMER_NAME}, headers=auth_headers)
    yield r.json()
    _cleanup()


def _pdf_bytes(size: int = 100) -> bytes:
    return b"%PDF-1.4\n" + (b"0" * size)


def test_upload_document_success(client, auth_headers, created_customer):
    r = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["original_filename"] == "contract.pdf"
    assert body["size_bytes"] == len(_pdf_bytes())
    assert "storage_filename" not in body  # never exposed to any client


def test_upload_document_cross_tenant_customer_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_customer
):
    r = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404


def test_upload_document_too_large_returns_413(client, auth_headers, created_customer):
    oversized = io.BytesIO(b"0" * (20 * 1024 * 1024 + 1))
    r = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("big.pdf", oversized, "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 413


def test_upload_document_disallowed_extension_returns_422(client, auth_headers, created_customer):
    r = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("script.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_list_documents_is_tenant_scoped(client, auth_headers, created_customer):
    client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    r = client.get(f"/api/v1/documents?customer_id={created_customer['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert any(d["original_filename"] == "contract.pdf" for d in r.json())


def test_download_document_success(client, auth_headers, created_customer):
    upload = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = upload.json()["id"]
    r = client.get(f"/api/v1/documents/{doc_id}/download", headers=auth_headers)
    assert r.status_code == 200
    assert r.content == _pdf_bytes()
    assert 'attachment; filename="contract.pdf"' in r.headers["content-disposition"]


def test_download_document_cross_tenant_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_customer
):
    upload = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = upload.json()["id"]
    r = client.get(f"/api/v1/documents/{doc_id}/download", headers=other_tenant_auth_headers)
    assert r.status_code == 404


def test_download_unknown_document_returns_404(client, auth_headers):
    r = client.get(f"/api/v1/documents/{uuid.uuid4()}/download", headers=auth_headers)
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_documents.py -v`

Expected: every test fails (404/import error) — `/api/v1/documents` doesn't exist yet.

- [ ] **Step 3: Create `app/documents/__init__.py`**

Empty file, matching `app/users/__init__.py`'s precedent.

- [ ] **Step 4: Add crud helpers**

In `app/database/crud.py`, near the existing `create_portal_link`/`list_portal_links` functions, add:

```python
def create_document(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    uploaded_by_user_id: uuid.UUID,
    original_filename: str,
    storage_filename: str,
    content_type: str,
    size_bytes: int,
) -> Document:
    row = Document(
        id=id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        uploaded_by_user_id=uploaded_by_user_id,
        original_filename=original_filename,
        storage_filename=storage_filename,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_document_by_id(db: Session, document_id: uuid.UUID) -> Document | None:
    return db.get(Document, document_id)


def list_documents(
    db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None = None
) -> list[Document]:
    stmt = select(Document).where(Document.tenant_id == tenant_id)
    if customer_id is not None:
        stmt = stmt.where(Document.customer_id == customer_id)
    stmt = stmt.order_by(Document.created_at.desc())
    return list(db.scalars(stmt))
```

Add `Document` to this file's existing `from app.database.models import ...` line. `select`, `Session`, `uuid` are already imported.

- [ ] **Step 5: Create `app/documents/models.py`**

```python
"""Sprint 016 (docs/DECISIONS.md ADR-032) — client-portal document
upload/download. See app/documents/service.py for the upload security
policy (size cap, extension allowlist, generated storage filename).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    """Deliberately excludes storage_filename — the on-disk name is never
    exposed to any client, staff or portal."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
```

- [ ] **Step 6: Create `app/documents/service.py`**

```python
"""DocumentService — Sprint 016 (docs/DECISIONS.md ADR-032).

Upload security policy (binding, see the design spec's §5 for the full
rationale — do not weaken any of this without a new decision):
  - MAX_UPLOAD_BYTES: 20MB, enforced against actual bytes written, not a
    trusted Content-Length header (a client can lie about Content-Length;
    it cannot lie about how many bytes it actually sends before an early
    abort).
  - ALLOWED_EXTENSIONS: an allowlist, not a denylist. .svg and .html/.htm
    are deliberately excluded even though sometimes treated as
    "documents" — both have real inline-script-execution histories.
  - Storage filename is always uuid4() + the validated extension — the
    user-supplied original_filename is NEVER used to construct a
    filesystem path (path traversal prevented by construction, not by
    sanitization).
  - No content-sniffing/magic-byte validation beyond the extension check
    — an accepted, documented gap (see ADR-032), not a silent one.
"""

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import crud
from app.database.models import Document

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt",
    ".jpg", ".jpeg", ".png", ".heic", ".webp",
}

_CHUNK_SIZE = 1024 * 1024


class CustomerNotFoundError(Exception):
    """customer_id doesn't resolve under the caller's own tenant — the
    same relationship-linkage-bypass check ADR-029 added elsewhere,
    reused from PortalService.create_link()."""


class FileTooLargeError(Exception):
    """Upload exceeded MAX_UPLOAD_BYTES; the partial file on disk (if any)
    has already been deleted before this is raised."""


class DisallowedFileTypeError(Exception):
    """extension is not in ALLOWED_EXTENSIONS."""

    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(extension)


class DocumentNotFoundError(Exception):
    """Unknown id, or an id that belongs to a different tenant."""


class DocumentService:
    def upload_document(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        uploaded_by_user_id: uuid.UUID,
        customer_id: uuid.UUID,
        file: UploadFile,
    ) -> Document:
        if crud.get_customer_by_id(db, customer_id, tenant_id) is None:
            raise CustomerNotFoundError(customer_id)

        original_filename = file.filename or "upload"
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise DisallowedFileTypeError(extension)

        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        storage_filename = f"{uuid.uuid4()}{extension}"
        destination = upload_dir / storage_filename

        size_bytes = 0
        with destination.open("wb") as out_file:
            while True:
                chunk = file.file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > MAX_UPLOAD_BYTES:
                    out_file.close()
                    destination.unlink(missing_ok=True)
                    raise FileTooLargeError(size_bytes)
                out_file.write(chunk)

        return crud.create_document(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            uploaded_by_user_id=uploaded_by_user_id,
            original_filename=original_filename,
            storage_filename=storage_filename,
            content_type=file.content_type or "application/octet-stream",
            size_bytes=size_bytes,
        )

    def list_documents(
        self, db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None = None
    ) -> list[Document]:
        return crud.list_documents(db, tenant_id, customer_id=customer_id)

    def get_document(self, db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        row = crud.get_document_by_id(db, document_id)
        if row is None or row.tenant_id != tenant_id:
            raise DocumentNotFoundError(document_id)
        return row

    def file_path(self, row: Document) -> Path:
        return Path(settings.upload_dir) / row.storage_filename


document_service = DocumentService()
```

- [ ] **Step 7: Create `app/documents/router.py`**

```python
"""Sprint 016 (docs/DECISIONS.md ADR-032). No require_role — any
authenticated tenant user may upload/list/download, matching the
customer/project/portal-link creation precedent (routine work, not a
tenant-control decision).
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.database.models import User
from app.documents.models import DocumentOut
from app.documents.service import (
    CustomerNotFoundError,
    DisallowedFileTypeError,
    DocumentNotFoundError,
    FileTooLargeError,
    document_service,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    customer_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return document_service.upload_document(
            db,
            tenant_id=current_user.tenant_id,
            uploaded_by_user_id=current_user.id,
            customer_id=customer_id,
            file=file,
        )
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    except FileTooLargeError:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 20MB limit",
        )
    except DisallowedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{exc.extension}' is not allowed",
        )


@router.get("", response_model=list[DocumentOut])
def list_documents(
    customer_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return document_service.list_documents(db, current_user.tenant_id, customer_id=customer_id)


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = document_service.get_document(db, current_user.tenant_id, document_id)
    except DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return FileResponse(
        path=document_service.file_path(row),
        media_type=row.content_type,
        filename=row.original_filename,
    )
```

`FileResponse` sets `Content-Disposition: attachment; filename="..."` by default when `filename` is passed — satisfies the Global Constraints' forced-download requirement without extra code.

- [ ] **Step 8: Mount the router**

In `app/api/v1/__init__.py`, the imports are alphabetical by module name (`core`, `auth`, `customers`, `invitations`, `portal`, `projects`, `quotes`, `tenants`, `users`). Add the import after `from app.customers.router import router as customers_router` and before `from app.invitations.router import router as invitations_router`:

```python
from app.documents.router import router as documents_router
```

Add the corresponding `include_router` call in the same relative position, after `api_router.include_router(customers_router)` and before `api_router.include_router(invitations_router)`:

```python
api_router.include_router(documents_router)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_documents.py -v`

Expected: all 8 tests pass.

- [ ] **Step 10: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: `153 passed` (145 existing + 8 new).

- [ ] **Step 11: Manual on-disk check**

After Step 9's test run (or a fresh manual upload via `/docs`), inspect the configured `upload_dir` directory: confirm filenames on disk look like `<uuid>.pdf`, never `contract.pdf` or any other original name.

- [ ] **Step 12: Commit**

```bash
git add app/database/crud.py app/documents/ app/api/v1/__init__.py tests/test_documents.py
git commit -m "feat: Sprint 016 - add documents module (upload, list, staff download)

New app/documents/ module: POST/GET /api/v1/documents, GET
/api/v1/documents/{id}/download. Enforces the upload security policy
(20MB cap checked against actual bytes, extension allowlist, generated
storage filename never derived from user input). No require_role,
matching customer/project/portal-link creation precedent."
```

---

## Task 3: Backend — portal-token document access (list + download)

**Files:**
- Modify: `app/portal/service.py`
- Modify: `app/portal/router.py`
- Modify: `tests/test_documents.py`

**Interfaces:**
- Consumes: `document_service.file_path()` (Task 2), `crud.list_documents`/`crud.get_document_by_id` (Task 2), `PortalService.get_link_by_token`/`derive_status` (pre-existing, Sprint 013).
- Produces: `GET /api/v1/portal-links/token/{token}/documents`, `GET /api/v1/portal-links/token/{token}/documents/{document_id}/download` — consumed by Task 4 (frontend `api.getPortalDocuments`/`downloadPortalDocument`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_documents.py`:

```python
def test_portal_lists_only_that_customers_documents(client, auth_headers, created_customer):
    client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()

    r = client.get(f"/api/v1/portal-links/token/{link['token']}/documents")
    assert r.status_code == 200
    assert any(d["original_filename"] == "contract.pdf" for d in r.json())


def test_portal_downloads_document_successfully(client, auth_headers, created_customer):
    upload = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = upload.json()["id"]
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()

    r = client.get(f"/api/v1/portal-links/token/{link['token']}/documents/{doc_id}/download")
    assert r.status_code == 200
    assert r.content == _pdf_bytes()
    assert 'attachment; filename="contract.pdf"' in r.headers["content-disposition"]


def test_portal_cannot_download_another_customers_document(client, auth_headers, created_customer):
    """A document belonging to a different customer in the SAME tenant,
    requested through a portal link scoped to created_customer, must 404
    — this is the relationship-bypass check on the public path, distinct
    from cross-tenant isolation."""
    other = client.post(
        "/api/v1/customers", json={"name": "Pytest Documents Other Customer"}, headers=auth_headers
    ).json()
    try:
        upload = client.post(
            f"/api/v1/documents?customer_id={other['id']}",
            files={"file": ("other.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
            headers=auth_headers,
        )
        doc_id = upload.json()["id"]
        link = client.post(
            "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
        ).json()

        r = client.get(f"/api/v1/portal-links/token/{link['token']}/documents/{doc_id}/download")
        assert r.status_code == 404
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(Document).where(Document.customer_id == other["id"]))
            db.execute(delete(Customer).where(Customer.id == other["id"]))
            db.commit()
        finally:
            db.close()


def test_portal_revoked_link_cannot_access_documents(client, auth_headers, created_customer):
    upload = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = upload.json()["id"]
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()
    client.delete(f"/api/v1/portal-links/{link['id']}", headers=auth_headers)

    r = client.get(f"/api/v1/portal-links/token/{link['token']}/documents/{doc_id}/download")
    assert r.status_code == 404
```

Add `from app.database.database import SessionLocal` to this file's imports if not already present from Task 2's version (it is not — Task 2's version didn't need it; add it now).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_documents.py -k portal -v`

Expected: all 4 new tests fail (404 — routes don't exist yet, or the routes 404 generically rather than exercising real logic).

- [ ] **Step 3: Add methods to `PortalService`**

In `app/portal/service.py`, add after `get_customer_quote`:

```python
    def list_customer_documents(self, db: Session, token: str) -> list[Document]:
        """Same active-token requirement as get_customer_quote — a
        revoked/expired link lists no documents, not an empty-but-200
        equivalent of get_public_view()'s convention (there is no
        meaningful "still show something" state for a document list on a
        dead link)."""
        row = self.get_link_by_token(db, token)
        if row is None or self.derive_status(row) != "active":
            raise PortalLinkNotFoundError(token)
        return crud.list_documents(db, row.tenant_id, customer_id=row.customer_id)

    def get_customer_document(self, db: Session, token: str, document_id: uuid.UUID) -> Document:
        """Mirrors get_customer_quote's exact shape: the document must
        belong to both the token's tenant_id AND its customer_id — not
        tenant alone, or one portal link could pull a different
        customer's document within the same tenant. Every failure raises
        the same PortalLinkNotFoundError so a caller can't distinguish
        "bad token" from "document not yours.\""""
        row = self.get_link_by_token(db, token)
        if row is None or self.derive_status(row) != "active":
            raise PortalLinkNotFoundError(token)

        document = crud.get_document_by_id(db, document_id)
        if document is None or document.tenant_id != row.tenant_id or document.customer_id != row.customer_id:
            raise PortalLinkNotFoundError(document_id)
        return document
```

Add `Document` to this file's existing `from app.database.models import ...` line.

- [ ] **Step 4: Add the two routes**

In `app/portal/router.py`, add after `download_portal_invoice`:

```python
@router.get("/token/{token}/documents", response_model=list[DocumentOut])
def list_portal_documents(token: str, db: Session = Depends(get_db)):
    try:
        return portal_service.list_customer_documents(db, token)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found")


@router.get("/token/{token}/documents/{document_id}/download")
def download_portal_document(token: str, document_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        row = portal_service.get_customer_document(db, token, document_id)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return FileResponse(
        path=document_service.file_path(row),
        media_type=row.content_type,
        filename=row.original_filename,
    )
```

Add two imports at the top of this file:
```python
from fastapi.responses import FileResponse
```
(add `FileResponse` to the existing `from fastapi import ...` line's neighbor import, or as its own line — `Response` is already imported from `fastapi` for the invoice route; `FileResponse` comes from `fastapi.responses`, a separate import)
```python
from app.documents.models import DocumentOut
from app.documents.service import document_service
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_documents.py -v`

Expected: all 12 tests in this file pass (8 from Task 2 + 4 new).

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: `157 passed` (153 from Task 2 + 4 new).

- [ ] **Step 7: Commit**

```bash
git add app/portal/service.py app/portal/router.py tests/test_documents.py
git commit -m "feat: Sprint 016 - add portal-token document list/download

Two new public routes on app/portal/router.py, mirroring the existing
invoice-download route's exact shape (active-token requirement, match on
both tenant_id AND customer_id, one shared not-found error). A revoked or
expired link cannot list or download documents."
```

---

## Task 4: Frontend — Documents card on customer page, Documents section on portal page

**Files:**
- Create: `apps/web/types/document.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/customers/[id]/page.tsx`
- Modify: `apps/web/app/portal/[token]/page.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/documents`, `GET /api/v1/documents`, `GET /api/v1/documents/{id}/download`, `GET /api/v1/portal-links/token/{token}/documents`, `GET /api/v1/portal-links/token/{token}/documents/{document_id}/download` (Tasks 2/3).
- Produces: nothing consumed by a later task — leaf UI change.

- [ ] **Step 1: Create `apps/web/types/document.ts`**

```typescript
// Sprint 016 — mirrors app/documents/models.py's DocumentOut.

export interface DocumentOut {
  id: string;
  tenant_id: string;
  customer_id: string;
  uploaded_by_user_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}
```

- [ ] **Step 2: Add API client methods**

In `apps/web/lib/api.ts`, add the import alongside the other `@/types/*` imports:

```typescript
import type { DocumentOut } from "@/types/document";
```

The base URL constant in this file is `API_BASE_URL` (not `API_BASE`), `ApiError`'s constructor signature is `new ApiError(message: string, status: number)`, and `getToken`/`clearToken` come from `@/lib/auth-storage` (already imported). Downloads in this codebase use a blob-fetch-and-trigger-save pattern (see `downloadInvoice`/`downloadPortalInvoice`, both already in this file), not a bare URL string — mirror that exact shape, not a URL-returning function. Add these five methods inside the exported `api` object, near the portal-link methods (after `getPortalByToken`/`downloadPortalInvoice`) and the quotes methods (after `downloadInvoice`) respectively — upload/list/staff-download go with the general methods, the two public ones go with the portal methods:

```typescript
  // Sprint 016 — multipart upload, cannot reuse request()'s JSON-only
  // Content-Type/body handling. Mirrors request()'s auth-header and
  // 401-clearing behavior manually; browser sets the multipart
  // Content-Type boundary automatically when body is a FormData instance
  // (must NOT set Content-Type manually here).
  uploadDocument: async (customerId: string, file: File): Promise<DocumentOut> => {
    const token = getToken();
    const formData = new FormData();
    formData.append("file", file);

    let res: Response;
    try {
      res = await fetch(
        `${API_BASE_URL}/api/v1/documents?customer_id=${customerId}`,
        {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData,
        }
      );
    } catch {
      throw new ApiError(`Could not reach the API at /documents`, 0);
    }

    if (!res.ok) {
      if (res.status === 401) clearToken();
      const body = await res.json().catch(() => ({}));
      throw new ApiError(
        body.detail ?? `Request to /documents failed with ${res.status}`,
        res.status
      );
    }
    return res.json();
  },

  getDocuments: (customerId: string) =>
    request<DocumentOut[]>(`/documents?customer_id=${customerId}`),

  // Sprint 016 — same blob-download-and-save pattern as downloadInvoice,
  // parameterized by filename since documents don't have a predictable
  // name the way "invoice-<id>.pdf" does.
  downloadDocument: async (id: string, filename: string): Promise<void> => {
    const token = getToken();
    let res: Response;

    try {
      res = await fetch(`${API_BASE_URL}/api/v1/documents/${id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      throw new ApiError(`Could not reach the API at /documents/${id}/download`, 0);
    }

    if (!res.ok) {
      if (res.status === 401) clearToken();
      throw new ApiError(
        `Request to /documents/${id}/download failed with ${res.status}`,
        res.status
      );
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },

  // Public — no token required, matches getPortalByToken/downloadPortalInvoice.
  getPortalDocuments: (token: string) =>
    request<DocumentOut[]>(`/portal-links/token/${token}/documents`),

  downloadPortalDocument: async (
    token: string,
    documentId: string,
    filename: string
  ): Promise<void> => {
    let res: Response;
    try {
      res = await fetch(
        `${API_BASE_URL}/api/v1/portal-links/token/${token}/documents/${documentId}/download`
      );
    } catch {
      throw new ApiError(
        `Could not reach the API at /portal-links/token/${token}/documents/${documentId}/download`,
        0
      );
    }

    if (!res.ok) {
      throw new ApiError(
        `Request to /portal-links/token/${token}/documents/${documentId}/download failed with ${res.status}`,
        res.status
      );
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
```

- [ ] **Step 3: Add the Documents card to the customer detail page**

In `apps/web/app/customers/[id]/page.tsx`, add a `DocumentOut` import: `import type { DocumentOut } from "@/types/document";`

Add state (alongside the existing `portalLinks`/`linksError` state):

```typescript
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [downloadingDocId, setDownloadingDocId] = useState<string | null>(null);
```

Add a load function (alongside `loadPortalLinks`):

```typescript
  function loadDocuments(customerId: string) {
    setDocumentsError(null);
    api
      .getDocuments(customerId)
      .then(setDocuments)
      .catch((err) =>
        setDocumentsError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }
```

In the existing `.then((c) => { setCustomer(c); loadPortalLinks(c.id); })` mount chain, add `loadDocuments(c.id);` alongside `loadPortalLinks(c.id);`.

Add an upload handler:

```typescript
  async function handleUploadDocument(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !customer) return;
    setUploading(true);
    setDocumentsError(null);
    try {
      await api.uploadDocument(customer.id, file);
      loadDocuments(customer.id);
    } catch (err) {
      setDocumentsError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function handleDownloadDocument(doc: DocumentOut) {
    setDownloadingDocId(doc.id);
    try {
      await api.downloadDocument(doc.id, doc.original_filename);
    } catch (err) {
      setDocumentsError(err instanceof ApiError ? err.message : "Download failed.");
    } finally {
      setDownloadingDocId(null);
    }
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
```

Add a new `<Card>` alongside the existing portal-link/invitations-style cards on this page — place it after the existing "Client portal" card:

```tsx
          <Card>
            <CardHeader>
              <CardTitle>Documents</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="border-b border-border p-5">
                <label className="flex items-center gap-3">
                  <span className="text-sm text-muted">
                    {uploading ? "Uploading…" : "Upload a document"}
                  </span>
                  <input
                    type="file"
                    onChange={handleUploadDocument}
                    disabled={uploading}
                    accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.jpg,.jpeg,.png,.heic,.webp"
                    className="text-sm text-foreground"
                  />
                </label>
              </div>
              {documentsError && (
                <p className="p-5 text-sm text-danger">{documentsError}</p>
              )}
              {documents === null && !documentsError && (
                <p className="p-5 text-center text-sm text-muted">Loading…</p>
              )}
              {documents && documents.length === 0 && (
                <p className="p-5 text-center text-sm text-muted">No documents yet.</p>
              )}
              {documents && documents.length > 0 && (
                <ul className="divide-y divide-border">
                  {documents.map((doc) => (
                    <li key={doc.id} className="flex items-center gap-3 px-5 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {doc.original_filename}
                        </p>
                        <p className="truncate text-xs text-muted">
                          {formatFileSize(doc.size_bytes)} · {formatDate(doc.created_at)}
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={downloadingDocId === doc.id}
                        onClick={() => handleDownloadDocument(doc)}
                      >
                        {downloadingDocId === doc.id ? "Downloading…" : "Download"}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
```

Note the list render condition is `{documents && documents.length > 0 && (...)}` — deliberately not gated on `!documentsError`, per this plan's frontend render-gate lesson.

- [ ] **Step 4: Add the Documents section to the portal page**

`apps/web/app/portal/[token]/page.tsx` currently fetches `portal` (projects/quotes/invoice download) via one `useEffect` on mount; documents are a separate endpoint not bundled into `PortalPublicOut`, so they need their own state and fetch, rendered only when `portal.status === "active"` (matching how the Projects/Quotes cards are already gated).

Add an import: `import type { DocumentOut } from "@/types/document";`

Add state (alongside `portal`/`loadError`):

```typescript
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [downloadingDocId, setDownloadingDocId] = useState<string | null>(null);
```

Add a download handler (alongside `handleDownloadInvoice`):

```typescript
  async function handleDownloadDocument(doc: DocumentOut) {
    setDownloadingDocId(doc.id);
    setDocumentsError(null);
    try {
      await api.downloadPortalDocument(params.token, doc.id, doc.original_filename);
    } catch {
      setDocumentsError("Could not download that document. Try again.");
    } finally {
      setDownloadingDocId(null);
    }
  }
```

In the existing `useEffect` that calls `api.getPortalByToken(params.token)`, add a second, independent fetch for documents (not chained — a failed documents fetch must not block the projects/quotes view that already works):

```typescript
  useEffect(() => {
    api
      .getPortalByToken(params.token)
      .then(setPortal)
      .catch((err) =>
        setLoadError(
          err instanceof ApiError && err.status === 404
            ? "This link isn't valid."
            : "Something went wrong."
        )
      );
    api
      .getPortalDocuments(params.token)
      .then(setDocuments)
      .catch((err) =>
        setDocumentsError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }, [params.token]);
```

Add a new `<Card>` inside the `{!loadError && portal && portal.status === "active" && (<div className="flex flex-col gap-6">` block, after the existing "Quotes" card and before the "This link expires..." paragraph:

```tsx
          <Card>
            <CardHeader>
              <CardTitle>Documents</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {documentsError && (
                <p className="p-5 text-sm text-danger">{documentsError}</p>
              )}
              {documents && documents.length === 0 && (
                <p className="p-5 text-center text-sm text-muted">No documents yet.</p>
              )}
              {documents && documents.length > 0 && (
                <ul className="divide-y divide-border">
                  {documents.map((doc) => (
                    <li key={doc.id} className="flex items-center gap-3 px-5 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {doc.original_filename}
                        </p>
                        <p className="truncate text-xs text-muted">
                          {formatDate(doc.created_at)}
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => handleDownloadDocument(doc)}
                        disabled={downloadingDocId === doc.id}
                      >
                        {downloadingDocId === doc.id ? "Downloading…" : "Download"}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
```

Same render-gate rule applies: `{documents && documents.length > 0 && (...)}`, not gated on `!documentsError`.

- [ ] **Step 5: Manual trace verification**

Read both resulting files once, tracing: (a) a customer with zero documents — no crash, sensible empty state; (b) a failed list load — error shown, no stale/undefined-state crash; (c) a successful upload — list reloads and shows the new document without a page refresh.

- [ ] **Step 6: Commit**

```bash
git add apps/web/types/document.ts apps/web/lib/api.ts "apps/web/app/customers/[id]/page.tsx" "apps/web/app/portal/[token]/page.tsx"
git commit -m "feat: Sprint 016 - add document upload/list UI to customer page and portal page

Customer page gets an upload form + document list. Portal page gets a
read-only document list with download links, alongside the existing
project/quote/invoice content."
```

---

## Task 5: Full verification pass

**Files:** none modified — verification only.

**Interfaces:**
- Consumes: Tasks 1–4 must all be committed first.
- Produces: a pass/fail verdict gating Task 6/7/8.

- [ ] **Step 1: Full backend suite** — `.venv/Scripts/python.exe -m pytest tests/ -q` — expect `157 passed`.
- [ ] **Step 2: Migration round-trip** — `alembic check`, `downgrade -1`, `upgrade head`, `alembic check` again — expect clean throughout.
- [ ] **Step 3: Frontend lint** — `pnpm lint` — expect 0 errors/warnings.
- [ ] **Step 4: Frontend build** — `pnpm build` — expect clean compile, TypeScript passing inside build (no standalone `check-types` script for `apps/web`), same route count as Sprint 015's baseline (15 routes — this task adds no new route, only content on two existing routes).
- [ ] **Step 5: `git diff --check`** — against the commit before Task 1 — expect exit 0.
- [ ] **Step 6: Record results** — no git action, keep exact figures for Task 7's docs and Task 8's audit.

---

## Task 6: Manual smoke test

**Files:** none modified.

- [ ] **Step 1: Start the app** (uvicorn + `pnpm dev`, against the local Postgres instance).
- [ ] **Step 2: Upload as staff** — upload a real small PDF against an existing customer via the new UI (or `/docs`). Confirm it appears in the customer page's Documents list, and confirm on disk (`upload_dir`) that the stored filename is a generated UUID, not the original name.
- [ ] **Step 3: Staff download** — download it from the customer page; confirm the browser saves it under the *original* filename, and the bytes match.
- [ ] **Step 4: Portal access** — open the customer's existing (or a newly generated) portal link; confirm the Documents section lists the file and download works, with no login.
- [ ] **Step 5: Rejection checks** — attempt an upload with a disallowed extension (e.g. rename a file to `.exe`) via `/docs` or the UI; confirm `422`. Attempt an oversized file if practical, or confirm via `/docs` with a crafted large payload; confirm `413`.
- [ ] **Step 6: Revoked-link check** — revoke the portal link used in Step 4; confirm the documents routes now 404 for that token.
- [ ] **Step 7: Clean up and record** — stop the dev servers; keep pass/fail results for Task 7/8.

---

## Task 7: Docs — ADR-032, sprint record, changelog, doc touch-ups; commit

**Files:**
- Modify: `docs/DECISIONS.md` (new ADR-032)
- Create: `docs/SPRINTS/sprint-016.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/USER_ROLES.md`
- Modify: `docs/SYSTEM_ARCHITECTURE.md`
- Modify: `docs/API_SPEC.md`

**Interfaces:**
- Consumes: real results from Task 5/6 — this task's audit table must use those figures, not invented ones.
- Produces: nothing consumed by a later task.

- [ ] **Step 1: Write ADR-032** in `docs/DECISIONS.md`, after ADR-031, following its format. Cover: local-disk choice and its stated limitation, generated-filename rationale (path traversal prevention by construction), customer-level (not project-level) attachment, and the complete upload security policy (size cap enforced against actual bytes, extension allowlist not denylist with `.svg`/`.html` explicitly excluded, no content-sniffing this sprint as an accepted gap, no virus scanning/S3/quotas as accepted deferrals).
- [ ] **Step 2: Write `docs/SPRINTS/sprint-016.md`** following `sprint-015.md`'s structure exactly, using only the real Task 5/6 results.
- [ ] **Step 3: Add the `docs/CHANGELOG.md` entry** at the top, above Sprint #015's entry, matching its format/density.
- [ ] **Step 4: Update `docs/USER_ROLES.md`** — note that the client-portal's document/invoice-download paragraph (Sprint 013's original "deliberately deferred" note) now has documents implemented; messaging remains deferred.
- [ ] **Step 5: Update `docs/SYSTEM_ARCHITECTURE.md`** — add `app/documents/` to the module table/folder listing; note the two new routes on `app/portal/router.py`'s existing entry; add `upload_dir` to the config/settings section if one exists.
- [ ] **Step 6: Update `docs/API_SPEC.md`** — add a "Document routes" section and table rows for all 5 new routes, matching the existing table's columns exactly (same approach Sprint 015 used for `/users`).
- [ ] **Step 7: Confirm `docs/ROADMAP.md` is untouched** (`git diff docs/ROADMAP.md` — no output) and `docs/SPRINTS/sprint-015.md`/its changelog entry are unmodified.
- [ ] **Step 8: Commit**

```bash
git add docs/DECISIONS.md docs/SPRINTS/sprint-016.md docs/CHANGELOG.md docs/USER_ROLES.md docs/SYSTEM_ARCHITECTURE.md docs/API_SPEC.md
git commit -m "docs: Sprint 016 - record client portal document upload/download (ADR-032)

Closes the documents half of the gap deferred since Sprint 013, named
again in Sprint 014's and Sprint 015's follow-ups. Messaging remains
deferred. Roadmap untouched."
```

---

## Task 8: Final scope-creep review before commit

**Files:** none modified — review only. This is the explicit final gate the user requested before any of this sprint's work is considered committable as a whole.

- [ ] **Step 1: Full diff stat** — `git diff --stat <commit before Task 1>..HEAD` — confirm every file matches this plan's declared file list (Tasks 1–7's "Files" sections combined) and nothing else appears.
- [ ] **Step 2: Confirm no messaging code** — grep the full diff for `message`/`chat`/`thread` (case-insensitive); any hit must be investigated and justified or removed — this sprint must not have grown to include messaging.
- [ ] **Step 3: Confirm no S3/quota/virus-scanning code** — grep the diff for `boto3`, `s3`, `quota`, `clamav`, `virus`; any hit must be investigated — these were explicitly ruled out for this sprint.
- [ ] **Step 4: Confirm `docs/ROADMAP.md` and Sprint 015's files are untouched** — `git diff docs/ROADMAP.md docs/SPRINTS/sprint-015.md` — expect no output.
- [ ] **Step 5: Confirm the upload policy is actually enforced as specified** — re-read `app/documents/service.py`'s `MAX_UPLOAD_BYTES`/`ALLOWED_EXTENSIONS` values against §5 of the spec verbatim; confirm no value was silently changed during implementation.
- [ ] **Step 6: Final security/tenant-isolation review** — a dedicated read-through, distinct from Step 5's value check: (a) every route in `app/documents/router.py` and the two new routes in `app/portal/router.py` — confirm each one that touches a specific customer's data validates `tenant_id` (staff routes) or resolves `tenant_id`/`customer_id` from the token row itself, never from caller input (public routes); (b) confirm `storage_filename` never appears in any response model or is ever echoed back to a client (`DocumentOut` excludes it — reconfirm the Pydantic model still excludes it after implementation, not just as originally planned); (c) confirm every download route sets a forced-download header (no route serves a file with a content-type/disposition that would render inline); (d) re-run the 12 `tests/test_documents.py` cases mentally against this checklist — each of the 4 portal-side tests should map to one of (a)-(c) above.
- [ ] **Step 7: `git status --short`** — run and record the exact output for the final report; confirm nothing outside this sprint's declared file list is modified or untracked.
- [ ] **Step 8: Report** — a short pass/fail summary of Steps 1–7, presented to the user alongside the rest of the sprint's final report. No commit happens as part of this task — it is a review gate, not a code change.

---

## Explicit non-goals (carried from spec)

- Messaging/chat for the client portal.
- File versioning or editing.
- Virus scanning, S3/object storage, storage quotas.
- Content-sniffing/magic-byte validation beyond the extension allowlist.
- Project-level document attachment.
- Any change to portal token design, auth, or tenant-isolation semantics.
- No push to any remote — every commit in this plan is local.
- No work on Sprint 017 or `docs/ROADMAP.md`.
