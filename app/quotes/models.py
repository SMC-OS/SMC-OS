import uuid
from datetime import datetime

from pydantic import BaseModel


class QuoteRequest(BaseModel):
    customer: str

    material: str

    thickness: str

    kitchen_length: float

    island: bool = False

    waterfall: int = 0

    splashback: bool = False

    upstands: bool = False

    postcode: str | None = None

    # Sprint 007: optional link to a real customer record. `customer` (the
    # free-text name) stays required and unchanged — /estimate's regex path
    # has no way to resolve a real customer, so a plain name must keep
    # working standalone. The `quotes` table only has customer_id (FK), no
    # text name column, so an unlinked quote's customer name lives only in
    # the calculated response, not in the persisted row.
    customer_id: uuid.UUID | None = None


class QuoteOut(BaseModel):
    """The persisted row's identity, layered onto QuoteCalculator's dict
    response — added once persistence exists (Sprint 007)."""

    id: uuid.UUID
    created_at: datetime
