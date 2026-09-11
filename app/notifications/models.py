import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


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


# --- Preferences (Sprint 039, Workstream B) -----------------------------


class NotificationPreferenceOut(BaseModel):
    """One category with this user's effective setting for it.

    Carries `label`/`description` alongside the flags so the settings
    screen has no hardcoded copy of the category list — the same
    served-vocabulary convention as /automations/meta and
    /projects/meta/pipeline.
    """

    category: str
    label: str
    description: str
    in_app: bool
    email: bool


class NotificationPreferenceUpdate(BaseModel):
    """One category's new setting.

    `category` is validated against the real vocabulary here rather than
    being accepted and silently ignored: a client sending a category this
    build does not have is a bug worth a 422, not a no-op.
    """

    category: str
    in_app: bool
    email: bool

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        from app.notifications.categories import CATEGORY_KEYS

        if value not in CATEGORY_KEYS:
            raise ValueError(f"category must be one of {sorted(CATEGORY_KEYS)}")
        return value


class NotificationPreferencesUpdate(BaseModel):
    preferences: list[NotificationPreferenceUpdate] = Field(min_length=1)
