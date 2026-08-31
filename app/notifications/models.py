import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class NotificationType(str, Enum):
    SUCCESS = "success"
    WARNING = "warning"
    INFO = "info"
    ERROR = "error"


class NotificationCreate(BaseModel):
    title: str
    message: str
    type: NotificationType = NotificationType.INFO
    # Sprint 024 (docs/SPRINTS/sprint-024.md) — all optional so every
    # existing caller (app/portal/service.py's tenant-wide broadcast) is
    # unaffected. recipient_user_id: None means tenant-wide, unchanged.
    recipient_user_id: uuid.UUID | None = None
    source_type: str | None = None
    source_id: uuid.UUID | None = None
    dedupe_key: str | None = None


class Notification(NotificationCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    read: bool = False
