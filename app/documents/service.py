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

# The served media type comes from the allowlisted extension, never from
# the uploader's Content-Type header: a ".pdf" declared as text/html must not
# be served as HTML. Keyed by the same extensions as ALLOWED_EXTENSIONS.
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain; charset=utf-8",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
    ".webp": "image/webp",
}


def media_type_for(filename: str) -> str:
    return MEDIA_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


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


class DocumentDeleteError(Exception):
    """The document could not be removed without leaving metadata behind."""


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

        document_id = uuid.uuid4()
        size_bytes = 0
        try:
            with destination.open("wb") as out_file:
                while True:
                    chunk = file.file.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > MAX_UPLOAD_BYTES:
                        raise FileTooLargeError(size_bytes)
                    out_file.write(chunk)

            return crud.create_document(
                db,
                id=document_id,
                tenant_id=tenant_id,
                customer_id=customer_id,
                uploaded_by_user_id=uploaded_by_user_id,
                original_filename=original_filename,
                storage_filename=storage_filename,
                content_type=media_type_for(storage_filename),
                size_bytes=size_bytes,
            )
        except BaseException:
            # QA-UPLOAD-ORPHAN: the bytes are written before the row, so any
            # failure (oversize, disk error, database error) must not leave an
            # unreferenced file behind.
            self._discard_unreferenced_file(db, document_id, destination)
            raise

    @staticmethod
    def _discard_unreferenced_file(db: Session, document_id: uuid.UUID, destination: Path) -> None:
        """Remove `destination` only when the document row is CONFIRMED absent.

        If the commit actually succeeded but its acknowledgement was lost, the
        row exists and the file is its only copy: deleting it would leave a
        dangling row, which is worse than an orphan. If the database cannot be
        asked, the file is kept (an orphan is detectable and harmless; data
        loss is not)."""
        try:
            db.rollback()
            if db.get(Document, document_id) is not None:
                return
        except Exception:
            return
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass

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

    def delete_document(self, db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
        """Delete only a caller-visible document. A missing byte is harmless:
        the authoritative metadata is still removed, making retries safe."""
        row = self.get_document(db, tenant_id, document_id)
        try:
            self.file_path(row).unlink(missing_ok=True)
        except OSError as exc:
            raise DocumentDeleteError() from exc
        db.delete(row)
        db.commit()


document_service = DocumentService()
