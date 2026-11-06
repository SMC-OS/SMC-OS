"""GeoCore Premium OS Plan 05 (Sprint 044) — the procurement + materials
operations domain. Pydantic schemas and pure calculation functions only;
the arithmetic lives here so it can be unit tested with no HTTP/DB round
trip, the same "pure function, DB access stays in the orchestrating
call" shape app/financials/service.py already established.

Trade-neutral by construction: a requirement/PO item may optionally
carry stone catalogue identity, but nothing here requires it — a
construction material with only a free-text description prices and
tracks identically.
"""

import math
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

# --- Material requirements ---------------------------------------------

REQUIREMENT_STATUSES = {
    "planned",
    "required",
    "ordered",
    "partially_received",
    "received",
    "allocated",
    "consumed",
    "cancelled",
}

# A requirement's own status only ever advances along this path via
# procurement events (Task 13) — never backwards, and never past
# `allocated`/`consumed` automatically. `cancelled` is reachable from
# any non-terminal status.
REQUIREMENT_FORWARD_ORDER = [
    "planned",
    "required",
    "ordered",
    "partially_received",
    "received",
    "allocated",
    "consumed",
]

# A requirement blocks a "materials ready" workflow gate (Task 27) while
# its status is one of these — i.e. everything short of the material
# actually being received.
REQUIREMENT_BLOCKING_STATUSES = {"planned", "required", "ordered", "partially_received"}


class MaterialRequirementIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    catalogue_surface_id: uuid.UUID | None = None
    catalogue_variant_id: uuid.UUID | None = None
    custom_material_name: str | None = None
    material_family: str | None = None
    required_quantity: float | None = None
    unit: str | None = None
    required_by_date: date | None = None
    preferred_supplier_id: uuid.UUID | None = None
    status: str = "required"
    notes: str | None = None
    source_type: str | None = None
    source_id: uuid.UUID | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str) -> str:
        if value not in REQUIREMENT_STATUSES:
            raise ValueError(f"status must be one of {sorted(REQUIREMENT_STATUSES)}")
        return value

    @field_validator("required_quantity")
    @classmethod
    def _not_negative(cls, value: float | None) -> float | None:
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("required_quantity must be a finite number, not negative")
        return value


class MaterialRequirementUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=500)
    catalogue_surface_id: uuid.UUID | None = None
    catalogue_variant_id: uuid.UUID | None = None
    custom_material_name: str | None = None
    material_family: str | None = None
    required_quantity: float | None = None
    unit: str | None = None
    required_by_date: date | None = None
    preferred_supplier_id: uuid.UUID | None = None
    status: str | None = None
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is not None and value not in REQUIREMENT_STATUSES:
            raise ValueError(f"status must be one of {sorted(REQUIREMENT_STATUSES)}")
        return value


class MaterialRequirementOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    description: str
    catalogue_surface_id: uuid.UUID | None
    catalogue_variant_id: uuid.UUID | None
    custom_material_name: str | None
    material_family: str | None
    required_quantity: float | None
    unit: str | None
    required_by_date: date | None
    preferred_supplier_id: uuid.UUID | None
    status: str
    notes: str | None
    source_type: str | None
    source_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Purchase orders -----------------------------------------------------

PO_STATUSES = {"draft", "approved", "ordered", "partially_received", "received", "cancelled"}

# Draft is the only freely editable status (Task 8). Approval locks
# pricing; ordered/partially_received/received are receiving-progress
# states layered on top, and partially_received/received are always
# *derived* from receipt data (Task 12), never set directly by a caller.
PO_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"approved", "cancelled"},
    "approved": {"ordered", "cancelled"},
    "ordered": {"partially_received", "received", "cancelled"},
    "partially_received": {"received", "cancelled"},
    "received": set(),
    "cancelled": set(),
}

MAX_PO_ITEMS = 200


class PurchaseOrderItemIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    material_requirement_id: uuid.UUID | None = None
    catalogue_surface_id: uuid.UUID | None = None
    catalogue_variant_id: uuid.UUID | None = None
    quantity: float = 1.0
    unit: str = "item"
    unit_cost: float = 0.0

    @field_validator("quantity", "unit_cost")
    @classmethod
    def _not_negative(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("must be a finite number, not negative")
        return value


class PurchaseOrderItemOut(BaseModel):
    id: uuid.UUID
    material_requirement_id: uuid.UUID | None
    catalogue_surface_id: uuid.UUID | None
    catalogue_variant_id: uuid.UUID | None
    description: str
    quantity: float
    unit: str
    unit_cost: float
    line_total: float
    quantity_received: float = 0.0

    model_config = {"from_attributes": True}


class PurchaseOrderCreate(BaseModel):
    project_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    expected_delivery_date: date | None = None
    notes: str | None = None
    vat_rate: float = 0.20
    items: list[PurchaseOrderItemIn] = Field(default_factory=list, max_length=MAX_PO_ITEMS)

    @field_validator("vat_rate")
    @classmethod
    def _sane_vat_rate(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("vat_rate must be a rate between 0 and 1 (e.g. 0.2 for 20%)")
        return value


class PurchaseOrderUpdate(BaseModel):
    """Draft-only (see ProcurementService.update_purchase_order)."""

    supplier_id: uuid.UUID | None = None
    expected_delivery_date: date | None = None
    notes: str | None = None
    vat_rate: float | None = None
    items: list[PurchaseOrderItemIn] | None = Field(default=None, max_length=MAX_PO_ITEMS)

    @field_validator("vat_rate")
    @classmethod
    def _sane_vat_rate(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("vat_rate must be a rate between 0 and 1 (e.g. 0.2 for 20%)")
        return value


class OrderPurchaseOrderRequest(BaseModel):
    """Body of POST /purchase-orders/{id}/order (Task 9) — internal
    tracking only; GeoCore never claims a live supplier integration."""

    supplier_reference: str | None = None
    expected_delivery_date: date | None = None


class PurchaseOrderOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    supplier_id: uuid.UUID | None
    reference: str
    status: str
    order_date: date | None
    expected_delivery_date: date | None
    received_date: date | None
    supplier_reference: str | None
    notes: str | None
    vat_rate: float
    subtotal: float
    vat: float
    total: float
    created_by_user_id: uuid.UUID | None
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[PurchaseOrderItemOut] = []
    is_late: bool = False

    model_config = {"from_attributes": True}


# --- Receipts --------------------------------------------------------------


class PurchaseReceiptItemIn(BaseModel):
    purchase_order_item_id: uuid.UUID
    quantity_received: float

    @field_validator("quantity_received")
    @classmethod
    def _positive(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("quantity_received must be a finite number greater than zero")
        return value


class PurchaseReceiptCreate(BaseModel):
    received_at: datetime
    delivery_reference: str | None = None
    notes: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    items: list[PurchaseReceiptItemIn] = Field(min_length=1, max_length=MAX_PO_ITEMS)


class LinkRequirementRequest(BaseModel):
    material_requirement_id: uuid.UUID


class PurchaseReceiptItemOut(BaseModel):
    id: uuid.UUID
    purchase_order_item_id: uuid.UUID
    quantity_received: float

    model_config = {"from_attributes": True}


class PurchaseReceiptOut(BaseModel):
    id: uuid.UUID
    purchase_order_id: uuid.UUID
    received_at: datetime
    received_by_user_id: uuid.UUID | None
    delivery_reference: str | None
    notes: str | None
    created_at: datetime
    items: list[PurchaseReceiptItemOut] = []

    model_config = {"from_attributes": True}


class OverReceiptError(Exception):
    """Raised when a receipt would take a PO item's total received
    quantity above what was ordered (Task 11) — rejected by default,
    never silently clamped or ignored."""

    def __init__(self, item_id: uuid.UUID, ordered: float, already_received: float, attempted: float):
        self.item_id = item_id
        self.ordered = ordered
        self.already_received = already_received
        self.attempted = attempted
        super().__init__(
            f"purchase order item {item_id}: {already_received} + {attempted} would exceed "
            f"ordered quantity {ordered}"
        )


# --- Allocations -------------------------------------------------------


class MaterialAllocationCreate(BaseModel):
    material_requirement_id: uuid.UUID | None = None
    purchase_order_item_id: uuid.UUID | None = None
    quantity: float
    notes: str | None = None

    @field_validator("quantity")
    @classmethod
    def _positive(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("quantity must be a finite number greater than zero")
        return value


class MaterialAllocationOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    material_requirement_id: uuid.UUID | None
    purchase_order_item_id: uuid.UUID | None
    quantity: float
    allocated_by_user_id: uuid.UUID | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Pure calculation functions -----------------------------------------


# Quantities are binary floats: 1.1 + 1.1 + 1.1 > 3.3. Comparisons allow for
# that rounding so a genuine final delivery is neither refused nor left short.
QUANTITY_TOLERANCE = 1e-6


def quantity_reached(actual: float, target: float) -> bool:
    return actual >= target - QUANTITY_TOLERANCE


def derive_po_status(current_status: str, ordered_qty: float, received_qty: float) -> str:
    """Task 12 — receiving progress is always derived from real receipt
    data, never toggled independently. Only meaningful once a PO has
    left `draft`/`approved` (i.e. is at least `ordered`); a draft or
    approved-but-not-yet-ordered PO is untouched by this function."""
    if current_status not in {"ordered", "partially_received", "received"}:
        return current_status
    if ordered_qty <= 0 or received_qty <= 0:
        return "ordered"
    if quantity_reached(received_qty, ordered_qty):
        return "received"
    return "partially_received"


def requirement_progress(
    required_quantity: float | None,
    requirement_unit: str | None,
    lines: list[tuple[float, float, str | None]],
) -> str | None:
    """Receiving state of a whole requirement from all its live PO lines,
    each `(ordered, received, unit)`. Returns None with no lines.

    A requirement is only `received` when what arrived covers what the job
    needs: its required_quantity when the units can honestly be compared,
    otherwise every linked line being fully delivered. Quantities in
    different units are never added together to reach a verdict."""
    if not lines:
        return None
    total_received = sum(received for _, received, _ in lines)
    if total_received <= QUANTITY_TOLERANCE:
        return "ordered"
    units_comparable = requirement_unit is None or all(
        unit is None or unit.strip().casefold() == requirement_unit.strip().casefold() for _, _, unit in lines
    )
    if required_quantity is not None and units_comparable:
        complete = quantity_reached(total_received, required_quantity)
    else:
        complete = all(quantity_reached(received, ordered) for ordered, received, _ in lines)
    return "received" if complete else "partially_received"


def is_po_late(status: str, expected_delivery_date: date | None, today: date) -> bool:
    """Task 26 — a PO is late only when it has a real expected delivery
    date that has passed and it is not yet done. A missing expected date
    is never classified as late (never fabricate a delivery date)."""
    if expected_delivery_date is None:
        return False
    if status in {"received", "cancelled"}:
        return False
    return expected_delivery_date < today


def next_requirement_status(current: str, po_item_status: str) -> str | None:
    """Task 13 — safe forward-only progression of a requirement in
    response to its linked PO item's own receiving state. Returns None
    when no change should happen (the requirement is already at or past
    the implied status, or is in a state (`allocated`/`consumed`/
    `cancelled`) that procurement events must never overwrite)."""
    if current in {"allocated", "consumed", "cancelled"}:
        return None
    if current not in REQUIREMENT_FORWARD_ORDER:
        return None
    target = {
        "ordered": "ordered",
        "partially_received": "partially_received",
        "received": "received",
    }.get(po_item_status)
    if target is None:
        return None
    if REQUIREMENT_FORWARD_ORDER.index(target) <= REQUIREMENT_FORWARD_ORDER.index(current):
        return None
    return target
