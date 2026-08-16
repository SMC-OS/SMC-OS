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
