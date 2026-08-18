"""Sprint 017 (docs/DECISIONS.md ADR-033) — client portal messaging.
MessageOut is shared by both the staff routes (app/messages/router.py) and
the public portal routes (app/portal/router.py), same pattern DocumentOut
already uses. sender_user_id identifies the authenticated staff sender
and is null for customer-authored portal messages.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

MAX_MESSAGE_BODY_LENGTH = 5000


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_MESSAGE_BODY_LENGTH)

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("message_body_blank", "Message body must not be blank")
        return value


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    sender_type: str
    sender_user_id: uuid.UUID | None
    body: str
    created_at: datetime
