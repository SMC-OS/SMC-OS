import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


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
    name: str
    customer_id: uuid.UUID | None = None
    notes: str | None = None


class ProjectOut(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ProjectStatus
    created_at: datetime
    quote_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None


class ProjectStatusUpdate(BaseModel):
    status: ProjectStatus


class ProjectAssignmentUpdate(BaseModel):
    """Sprint 023 (docs/SPRINTS/sprint-023.md). `assigned_user_id: null` is
    a valid, explicit unassignment — not "field omitted"."""

    assigned_user_id: uuid.UUID | None
