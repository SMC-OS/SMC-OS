import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Plain strings, same no-native-enum convention as Project.status.
TASK_STATUSES = {"open", "done", "cancelled"}


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str | None = None
    due_at: datetime | None = None
    assigned_user_id: uuid.UUID | None = None
    # Free-form link to whatever this task is about — the same
    # deliberately-unconstrained polymorphic reference NotificationRecord
    # uses. Validated for tenant ownership in the service, never by an FK,
    # because no single FK can point at three different tables.
    source_type: str | None = None
    source_id: uuid.UUID | None = None


class TaskStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str) -> str:
        if value not in TASK_STATUSES:
            raise ValueError(f"status must be one of {sorted(TASK_STATUSES)}")
        return value


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str | None
    status: str
    due_at: datetime | None
    assigned_user_id: uuid.UUID | None
    source_type: str | None
    source_id: uuid.UUID | None
    completed_at: datetime | None
    created_at: datetime
