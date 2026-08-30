"""Sprint 022 — Appointment / Site Visit Scheduling. See
docs/SPRINTS/sprint-022.md's Locked Contract for the full rationale behind
every shape below.
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AppointmentTransitionTarget(str, Enum):
    """Decision 2 (sprint-022.md): the status-update request can only ever
    express a valid target — there is no path this sprint that submits
    `scheduled`, so the schema itself doesn't allow it, rather than
    allowing it and rejecting it in the service."""

    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AppointmentCreate(BaseModel):
    scheduled_at: datetime
    notes: str | None = None

    @field_validator("scheduled_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        # Decision 5 (sprint-022.md) — the first client-supplied datetime
        # this codebase has ever accepted; a naive value is rejected rather
        # than silently assumed to be any particular timezone.
        if value.tzinfo is None:
            raise ValueError("scheduled_at must include timezone information")
        return value


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentTransitionTarget


class AppointmentOut(BaseModel):
    """Exposes tenant_id and created_by_user_id directly, matching
    DocumentOut/PortalLinkOut's shape (both child-of-parent audit
    entities) rather than CustomerOut/ProjectOut's narrower one."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    created_by_user_id: uuid.UUID
    scheduled_at: datetime
    status: AppointmentStatus
    notes: str | None = None
    created_at: datetime
