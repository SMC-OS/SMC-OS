"""GeoCore Premium OS Plan 04 (Sprint 043) — the variation (change order)
domain. Pricing/VAT is not reinvented here: app/variations/service.py
calls app/quotes/general.py's `price()` directly against these item
shapes, the same rounding and tax rule a general quote already uses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# draft: fully editable. sent: items/title locked, may be approved/
# rejected/voided. approved/rejected/void: terminal — a correction is a
# new, separate variation (Task 24), never a rewrite of this one.
VARIATION_STATUSES = {"draft", "sent", "approved", "rejected", "void"}

# `draft` may go straight to approved/rejected, same as a Quote's own
# `_APPROVABLE_STATUSES = {"draft", "sent"}` (app/quotes/service.py) —
# "send" records that the customer has actually seen it, but approving
# something never sent is not a distinct error case.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"sent", "approved", "rejected", "void"},
    "sent": {"approved", "rejected", "void"},
    "approved": set(),
    "rejected": set(),
    "void": set(),
}

# Same MAX_LINES cap and reasoning as app/quotes/general.py.
MAX_ITEMS = 200


class VariationItemIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    quantity: float = 1.0
    unit: str = "item"
    unit_price: float = 0.0

    @field_validator("quantity", "unit_price")
    @classmethod
    def _not_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("must not be negative")
        return value


class VariationItemOut(BaseModel):
    id: uuid.UUID
    description: str
    quantity: float
    unit: str
    unit_price: float
    line_total: float

    model_config = {"from_attributes": True}


class VariationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    requested_by: str | None = None
    vat_rate: float = 0.20
    items: list[VariationItemIn] = Field(default_factory=list, max_length=MAX_ITEMS)

    @field_validator("vat_rate")
    @classmethod
    def _sane_vat_rate(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("vat_rate must be a rate between 0 and 1 (e.g. 0.2 for 20%)")
        return value


class VariationUpdate(BaseModel):
    """Draft-only (see VariationService.update) — same "a document
    someone else may already be holding is never silently rewritten"
    posture as GeneralQuoteUpdate."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    requested_by: str | None = None
    vat_rate: float | None = None
    items: list[VariationItemIn] | None = Field(default=None, max_length=MAX_ITEMS)

    @field_validator("vat_rate")
    @classmethod
    def _sane_vat_rate(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("vat_rate must be a rate between 0 and 1 (e.g. 0.2 for 20%)")
        return value


class VariationOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    reference: str
    title: str
    description: str | None
    status: str
    vat_rate: float
    subtotal: float
    vat: float
    total: float
    requested_by: str | None
    approved_at: datetime | None
    approved_by_user_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    items: list[VariationItemOut] = []

    model_config = {"from_attributes": True}
