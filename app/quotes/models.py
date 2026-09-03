import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class QuoteRequest(BaseModel):
    customer: str

    material: str

    thickness: str

    # Sprint 032 (Workstream C) — structured dimensions replace the old
    # ambiguous single `kitchen_length` float as the request's source of
    # truth. Canonical unit is millimetres; `unit_input` records what the
    # caller actually entered in, for transparency/traceability only.
    quantity: int = 1
    length_mm: float | None = None
    # Defaults to the standard UK worktop depth (650mm) when the caller
    # doesn't have/need an independent width — never silently invented
    # when the caller *does* supply one.
    width_mm: float = 650
    thickness_mm: float | None = None
    unit_input: str = "mm"

    # Backward-compatible alias for pre-Sprint-032 callers — metres,
    # matching the field this replaced. If length_mm isn't given, it's
    # derived from this instead of rejecting the request. New callers
    # should send length_mm directly.
    kitchen_length: float | None = None

    island: bool = False

    waterfall: int = 0

    splashback: bool = False
    # Independent linear length for the splashback — required (validated
    # in app/quotes/validator.py) whenever `splashback` is True, so it
    # never silently reuses the worktop run's own length.
    splashback_length_mm: float | None = None

    upstands: bool = False
    upstands_length_mm: float | None = None

    postcode: str | None = None

    # Sprint 007: optional link to a real customer record. `customer` (the
    # free-text name) stays required and unchanged — /estimate's regex path
    # has no way to resolve a real customer, so a plain name must keep
    # working standalone. The `quotes` table only has customer_id (FK), no
    # text name column, so an unlinked quote's customer name lives only in
    # the calculated response, not in the persisted row.
    customer_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _resolve_length_mm(self) -> "QuoteRequest":
        if self.length_mm is None:
            if self.kitchen_length is None:
                raise ValueError("length_mm (or legacy kitchen_length) is required.")
            self.length_mm = self.kitchen_length * 1000
            self.unit_input = "m"
        return self


class QuoteOut(BaseModel):
    """The persisted row's identity, layered onto QuoteCalculator's dict
    response — added once persistence exists (Sprint 007)."""

    id: uuid.UUID
    created_at: datetime
