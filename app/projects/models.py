import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.trades.catalogue import TRADE_KEYS


# Sprint 039 (Workstream D) removed `ProjectStatus`. A project's status is
# no longer a fixed enum shared by every business on GeoCore: the set of
# stages is per-tenant configuration (app/projects/pipeline_config.py) and
# the *meaning* of each stage is a trade-neutral role
# (app/projects/pipeline.py's ROLES). Sprint 006's stone-shaped enum
# survives as the `stone` template.
#
# Anything that used to compare against `ProjectStatus.ENQUIRY` now asks
# for the role instead — `pipeline.stage_for_role("lead")` — so the same
# code works for a stone tenant whose lead stage is called "enquiry" and a
# roofing tenant whose lead stage is called "lead".


class PipelineStageOut(BaseModel):
    """One stage of the caller's own pipeline, with the moves it allows.

    `allowed_transitions` is served rather than re-derived client-side for
    the same reason /automations/meta serves its trigger and action lists:
    a UI must not be able to offer a transition the engine will refuse.
    """

    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    role: str
    position: int
    is_terminal: bool
    is_side_state: bool
    allowed_transitions: list[str]


class ProjectPipelineOut(BaseModel):
    stages: list[PipelineStageOut]


class ProjectCreate(BaseModel):
    """Sprint 036 (Workstream F) expands this beyond name/customer/notes
    into a real construction job record. The three original fields keep
    their names and remain the only required-or-defaulted ones, so the
    body every existing caller sends — including quote handoff and the
    E2E suite — is still valid unchanged.

    `project_type` shares its vocabulary with `Quote.trade`
    (app/trades/catalogue.py) rather than defining a parallel list, so an
    approved quote hands its trade straight to the project it becomes.
    """

    name: str
    customer_id: uuid.UUID | None = None
    notes: str | None = None

    project_type: str | None = None
    description: str | None = None
    site_address_line1: str | None = None
    site_address_line2: str | None = None
    site_city: str | None = None
    site_postcode: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    estimated_value: float | None = None

    @field_validator("project_type")
    @classmethod
    def _known_project_type(cls, value: str | None) -> str | None:
        if value is not None and value not in TRADE_KEYS:
            raise ValueError(f"project_type must be one of {sorted(TRADE_KEYS)}")
        return value


class ProjectUpdate(BaseModel):
    """Partial update (Sprint 036). Same exclude_unset contract as
    CustomerUpdate: omitted means "leave alone", explicit null means
    "clear".

    `status` is deliberately absent. It has its own endpoint with its own
    linear-transition rules (ProjectService.update_status), and letting a
    general PATCH set it would route around them.
    """

    name: str | None = None
    customer_id: uuid.UUID | None = None
    notes: str | None = None
    project_type: str | None = None
    description: str | None = None
    site_address_line1: str | None = None
    site_address_line2: str | None = None
    site_city: str | None = None
    site_postcode: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    estimated_value: float | None = None

    @field_validator("project_type")
    @classmethod
    def _known_project_type(cls, value: str | None) -> str | None:
        if value is not None and value not in TRADE_KEYS:
            raise ValueError(f"project_type must be one of {sorted(TRADE_KEYS)}")
        return value


class ProjectOut(ProjectCreate):
    """Sprint 039: `status` is a stage *key* from this tenant's own
    pipeline — a plain string, because the valid set is configuration and
    differs between tenants. `status_role` is the trade-neutral meaning,
    served alongside it so no client has to map a tenant-specific name
    back onto a stage in the shared vocabulary."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    status_role: str | None = None
    created_at: datetime
    quote_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None


class ProjectStatusUpdate(BaseModel):
    """`status` is a stage key, validated against the caller's own
    pipeline in the service (not here): which keys are valid depends on
    the tenant, which a Pydantic model has no access to."""

    status: str


class ProjectAssignmentUpdate(BaseModel):
    """Sprint 023 (docs/SPRINTS/sprint-023.md). `assigned_user_id: null` is
    a valid, explicit unassignment — not "field omitted"."""

    assigned_user_id: uuid.UUID | None
