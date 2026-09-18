"""GeoCore Premium OS Plan 04 (Sprint 043) — the project financial
domain. Pydantic schemas only; the arithmetic lives in service.py so it
can be unit tested with no HTTP/DB round trip.

Trade-neutral by construction: nothing here assumes stone, a slab, a
material or a trade-specific vocabulary — a bathroom refit and a kitchen
worktop run are priced through exactly the same shapes.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

COST_CATEGORIES = {"material", "labour", "subcontractor", "plant", "transport", "other"}
COST_STATES = {"budgeted", "committed", "actual"}

COST_DATA_STATUSES = {"none", "partial", "complete"}


class ProjectCostEntryIn(BaseModel):
    """Create/update body for one cost ledger row. `total_cost` is always
    required and is always the number every aggregate sums — quantity/
    unit/unit_cost are optional detail a caller may supply to *derive*
    it (the frontend multiplies quantity x unit_cost into total_cost
    before or after submitting; this schema does not silently recompute
    one from the other, so an explicitly-typed total is never
    overwritten by a stale quantity x unit_cost)."""

    category: str
    state: str
    description: str = Field(min_length=1, max_length=500)
    supplier_or_payee: str | None = None
    reference: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_cost: float | None = None
    total_cost: float
    cost_date: date | None = None
    due_date: date | None = None

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        if value not in COST_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(COST_CATEGORIES)}")
        return value

    @field_validator("state")
    @classmethod
    def _known_state(cls, value: str) -> str:
        if value not in COST_STATES:
            raise ValueError(f"state must be one of {sorted(COST_STATES)}")
        return value

    @field_validator("total_cost")
    @classmethod
    def _not_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("total_cost must not be negative")
        return value


class ProjectCostEntryUpdate(BaseModel):
    """All optional — a PATCH touches only the fields it names."""

    category: str | None = None
    state: str | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)
    supplier_or_payee: str | None = None
    reference: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_cost: float | None = None
    total_cost: float | None = None
    cost_date: date | None = None
    due_date: date | None = None

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str | None) -> str | None:
        if value is not None and value not in COST_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(COST_CATEGORIES)}")
        return value

    @field_validator("state")
    @classmethod
    def _known_state(cls, value: str | None) -> str | None:
        if value is not None and value not in COST_STATES:
            raise ValueError(f"state must be one of {sorted(COST_STATES)}")
        return value

    @field_validator("total_cost")
    @classmethod
    def _not_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("total_cost must not be negative")
        return value


class ProjectCostEntryOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    category: str
    state: str
    description: str
    supplier_or_payee: str | None
    reference: str | None
    quantity: float | None
    unit: str | None
    unit_cost: float | None
    total_cost: float
    cost_date: date | None
    due_date: date | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CostSummary(BaseModel):
    """One entry per COST_STATES key, 0.0 if none recorded — never a
    sparse dict, same never-partial contract as app/dashboard/models.py's
    PipelineCounts."""

    budgeted_cost: float
    committed_cost: float
    actual_cost: float
    forecast_cost: float
    cost_data_status: str
    cost_entry_count: int


class ContractSummary(BaseModel):
    """`base_contract_value`/`current_contract_value` are `None` when
    there is no safe, non-fabricated source for them (Task 9) — never a
    guessed zero. `approved_variations_total` is always a real number
    (0.0 when none are approved yet), since it is always safely
    computable regardless of whether a base contract is known."""

    base_contract_value: float | None
    base_contract_source: str | None
    approved_variations_total: float
    current_contract_value: float | None


class ProfitabilitySummary(BaseModel):
    """`None` on any figure that would otherwise be fabricated — a
    missing contract value, zero cost data, or a zero/negative contract
    denominator. `actual_*` fields are labelled distinctly from
    `forecast_*` and must never be presented interchangeably (Task 11)."""

    forecast_gross_profit: float | None
    forecast_gross_margin_percent: float | None
    actual_gross_profit: float | None
    actual_gross_margin_percent: float | None
    margin_risk: bool


class ProjectFinancialSummary(BaseModel):
    project_id: uuid.UUID
    contract: ContractSummary
    costs: CostSummary
    profitability: ProfitabilitySummary
