import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

# Sprint 036 (Workstream D). Plain strings, same no-native-enum
# convention as Project.status / User.role — validated here at the
# Pydantic boundary, not by a DB constraint.
CUSTOMER_TYPES = {"individual", "company"}


class CustomerCreate(BaseModel):
    """The create body. `name` stays the only required field, and the three
    original fields keep their exact names and positions, so the body every
    existing caller sends ({name, email, phone}) is still valid — including
    the enquiry-conversion path (Sprint 021) and the E2E suite.

    Sprint 036 adds the rest of a construction customer record. `name` is
    deliberately still the person you deal with even for a company
    customer: `company_name` is the organisation, `name` is the human who
    answers the phone, and collapsing the two would lose the contact on
    every commercial job.
    """

    name: str
    email: str | None = None
    phone: str | None = None

    customer_type: str = "individual"
    company_name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postcode: str | None = None
    notes: str | None = None

    @field_validator("customer_type")
    @classmethod
    def _known_customer_type(cls, value: str) -> str:
        if value not in CUSTOMER_TYPES:
            raise ValueError(f"customer_type must be one of {sorted(CUSTOMER_TYPES)}")
        return value


class CustomerUpdate(BaseModel):
    """Partial update (Sprint 036). Every field is optional *and* the
    service applies `model_dump(exclude_unset=True)`, so "field omitted"
    (leave it alone) stays distinguishable from "field explicitly null"
    (clear it) — a distinction a plain Optional-with-default model loses.
    """

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    customer_type: str | None = None
    company_name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postcode: str | None = None
    notes: str | None = None

    @field_validator("customer_type")
    @classmethod
    def _known_customer_type(cls, value: str | None) -> str | None:
        if value is not None and value not in CUSTOMER_TYPES:
            raise ValueError(f"customer_type must be one of {sorted(CUSTOMER_TYPES)}")
        return value


class CustomerOut(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class CustomerQuoteSummary(BaseModel):
    """A quote as the customer detail page shows it. Deliberately a
    summary, not the full quote serialization: the page needs identity,
    money and state, and shipping every slab dimension of every stone
    quote through this endpoint would make it grow without bound as a
    customer accumulates work."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quote_kind: str
    title: str | None = None
    trade: str | None = None
    status: str
    currency: str
    total: float | None = None
    valid_until: date | None = None
    created_at: datetime


class CustomerProjectSummary(BaseModel):
    """Sprint 039 adds `status_label`/`status_role`, resolved server-side
    against the tenant's own pipeline, so this panel renders a job's stage
    without a second round trip for the pipeline it already had to read."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    status_label: str | None = None
    status_role: str | None = None
    project_type: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    estimated_value: float | None = None
    created_at: datetime


class CustomerContextOut(BaseModel):
    """One call backing the customer detail page's business context.

    `quoted_value` and `approved_value` carry the same meaning the
    dashboard already established in Sprint 025: a quote total is a price
    offered or committed to, never recognised revenue. They are named
    accordingly here too so no reader can mistake one for the other.
    """

    customer: CustomerOut
    quotes: list[CustomerQuoteSummary]
    projects: list[CustomerProjectSummary]
    quoted_value: float
    approved_value: float
    open_projects: int
