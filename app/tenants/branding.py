"""Tenant logo upload and serving (Sprint 036, Workstream I).

Until this sprint, "add your logo" meant pasting a URL into a text field —
which is not a feature a builder can use, and which puts a customer-facing
document's branding at the mercy of a third-party host that may go away.

This module reuses the security posture app/documents/service.py
established in Sprint 016 (ADR-032), because it is the same problem:

  * an **allowlist** of extensions, not a denylist. SVG is excluded even
    though it is the obvious format for a logo — SVG is XML that can carry
    script, and this file is served back to browsers.
  * the size limit is enforced against **bytes actually written**, never a
    Content-Length header a client can lie about.
  * the storage filename is always a fresh uuid4 plus the validated
    extension. The user-supplied filename is never used to build a path,
    so traversal is prevented by construction rather than by sanitising.

Two things are deliberately different from documents:

  * the limit is 2MB, not 20MB. A logo that big is a mistake, and this
    file is fetched on every settings page load.
  * replacing a logo deletes the previous file. A document is a record and
    is kept; a logo is current-state, and orphaned files accumulating on a
    volume forever is a real operational cost with no upside.
"""

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings

MAX_LOGO_BYTES = 2 * 1024 * 1024

# No .svg — see the module docstring. No .heic either: it is a photo
# format no browser reliably renders, so accepting it would produce a
# logo that silently fails to display.
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

_CHUNK_SIZE = 256 * 1024

_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class LogoTooLargeError(Exception):
    """Upload exceeded MAX_LOGO_BYTES. The partial file has already been
    deleted before this is raised."""


class DisallowedLogoTypeError(Exception):
    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(extension)


def content_type_for(storage_filename: str) -> str:
    return _CONTENT_TYPES.get(Path(storage_filename).suffix.lower(), "application/octet-stream")


def logo_path(storage_filename: str) -> Path:
    return Path(settings.upload_dir) / storage_filename


def save_logo(file: UploadFile) -> str:
    """Write the uploaded logo and return its generated storage filename.

    Deliberately knows nothing about tenants or the database: the caller
    persists the returned filename against the right row, which keeps this
    function trivially testable and keeps the storage rules in one place.
    """
    extension = Path(file.filename or "logo").suffix.lower()
    if extension not in ALLOWED_LOGO_EXTENSIONS:
        raise DisallowedLogoTypeError(extension)

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_filename = f"logo-{uuid.uuid4()}{extension}"
    destination = upload_dir / storage_filename

    size_bytes = 0
    with destination.open("wb") as out_file:
        while True:
            chunk = file.file.read(_CHUNK_SIZE)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > MAX_LOGO_BYTES:
                out_file.close()
                destination.unlink(missing_ok=True)
                raise LogoTooLargeError(size_bytes)
            out_file.write(chunk)

    return storage_filename


def delete_logo(storage_filename: str | None) -> None:
    """Remove a superseded logo file. `missing_ok` because a file already
    gone is the desired end state — a redeploy that reset an ephemeral
    volume must not make replacing a logo fail."""
    if not storage_filename:
        return
    logo_path(storage_filename).unlink(missing_ok=True)
