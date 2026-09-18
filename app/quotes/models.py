import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Sprint 033 (Workstream C). Plain strings (no native enum), same
# convention as Quote.status etc. — validated here at the Pydantic
# boundary. Every type shares identical area math (quantity x length x
# width); island/waterfall_panel carry a small additional flat
# installation surcharge for pricing continuity with Sprint 032 (see
# app/quotes/calculator.py), not because they need different dimensions.
ITEM_TYPES = {"worktop", "island", "splashback", "upstand", "sill", "waterfall_panel", "other"}


class QuoteItemRequest(BaseModel):
    item_type: str = "worktop"
    material: str
    thickness: str

    quantity: int = 1
    length_mm: float
    # Defaults to the standard UK worktop depth (650mm) — for a linear
    # item (splashback/upstand/sill) this is that item's own height/
    # depth, not a worktop depth; always independent per item, never
    # inherited from another item on the same quote.
    width_mm: float = 650
    thickness_mm: float | None = None
    unit_input: str = "mm"

    notes: str | None = None

    # Sprint 042 (GeoCore Premium OS Plan 03) — Stone Quote Engine V2.
    # Both optional and additive: when `catalogue_surface_id` is set,
    # app/quotes/calculator.py resolves price from the Master Catalogue
    # + the caller's own tenant_catalogue_overrides row instead of the
    # free-text `material`/`thickness` lookup against the old flat
    # `materials` table — `material`/`thickness` above are still
    # required (the API's own request shape is unchanged) and are used
    # as the human-readable label on the line; nothing about the
    # existing free-text path changes when this is omitted.
    catalogue_surface_id: uuid.UUID | None = None
    catalogue_variant_id: uuid.UUID | None = None

    @field_validator("item_type")
    @classmethod
    def _item_type_must_be_known(cls, value: str) -> str:
        if value not in ITEM_TYPES:
            raise ValueError(f"item_type must be one of {sorted(ITEM_TYPES)}")
        return value


class QuoteItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    item_type: str
    material: str
    thickness: str
    quantity: int
    length_mm: float
    width_mm: float
    thickness_mm: float | None
    unit_input: str
    notes: str | None
    price_per_slab: float | None
    slabs: int | None
    line_total: float | None


class QuoteRequest(BaseModel):
    customer: str

    postcode: str | None = None

    # Sprint 033 (Workstream C) — the source of truth. A quote is one or
    # more independent line items; nothing here forces a splashback to
    # share a worktop's dimensions or vice versa.
    items: list[QuoteItemRequest] | None = None

    # --- Backward-compatible single-item alias (the Sprint 032 and
    # earlier flat shape) — still accepted over the API, wrapped into a
    # single "worktop" `items` entry when `items` isn't given directly.
    # Never read past construction; app/quotes/calculator.py and
    # app/quotes/service.py only ever look at `items`. ---
    material: str | None = None
    thickness: str | None = None
    quantity: int = 1
    length_mm: float | None = None
    width_mm: float = 650
    thickness_mm: float | None = None
    unit_input: str = "mm"
    kitchen_length: float | None = None  # Sprint 032's own legacy alias

    # Sprint 007: optional link to a real customer record. `customer` (the
    # free-text name) stays required and unchanged — /estimate's regex path
    # has no way to resolve a real customer, so a plain name must keep
    # working standalone. The `quotes` table only has customer_id (FK), no
    # text name column, so an unlinked quote's customer name lives only in
    # the calculated response, not in the persisted row.
    customer_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _build_items(self) -> "QuoteRequest":
        if self.items:
            return self

        length_mm = self.length_mm
        unit_input = self.unit_input
        if length_mm is None and self.kitchen_length is not None:
            length_mm = self.kitchen_length * 1000
            unit_input = "m"

        if length_mm is None or self.material is None or self.thickness is None:
            raise ValueError(
                "Provide `items`, or the legacy `material`/`thickness`/`length_mm` "
                "(or `kitchen_length`) fields for a single-item quote."
            )

        self.items = [
            QuoteItemRequest(
                item_type="worktop",
                material=self.material,
                thickness=self.thickness,
                quantity=self.quantity,
                length_mm=length_mm,
                width_mm=self.width_mm,
                thickness_mm=self.thickness_mm,
                unit_input=unit_input,
            )
        ]
        return self


class QuoteOut(BaseModel):
    """The persisted row's identity, layered onto QuoteCalculator's dict
    response — added once persistence exists (Sprint 007)."""

    id: uuid.UUID
    created_at: datetime
