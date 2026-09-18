import uuid
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator

from app.trades.catalogue import TRADE_KEYS
from app.workflows.models import ProjectWorkflowSummary


class ProjectStatus(str, Enum):
    """The job pipeline (docs/ROADMAP.md, Sprint 006). Stored as a plain
    String column (app/database/models.py's Project.status), not a native
    Postgres enum — same convention as ActivityType/NotificationType."""

    ENQUIRY = "enquiry"
    QUOTED = "quoted"
    BOOKED = "booked"
    TEMPLATED = "templated"
    FABRICATED = "fabricated"
    INSTALLED = "installed"
    COMPLETE = "complete"


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
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ProjectStatus
    created_at: datetime
    quote_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None
    # GeoCore Premium OS Plan 01 (Sprint 040) — the workflow-facing view
    # of this project, alongside `status` above which stays present and
    # correct unchanged throughout this migration period. Never optional:
    # workflow_template_id/workflow_stage_id are NOT NULL as of this
    # plan's migration, so every Project row has one.
    workflow: ProjectWorkflowSummary


class ProjectStatusUpdate(BaseModel):
    status: ProjectStatus


class ProjectAssignmentUpdate(BaseModel):
    """Sprint 023 (docs/SPRINTS/sprint-023.md). `assigned_user_id: null` is
    a valid, explicit unassignment — not "field omitted"."""

    assigned_user_id: uuid.UUID | None
