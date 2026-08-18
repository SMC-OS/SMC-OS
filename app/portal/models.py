import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.messages.models import MAX_MESSAGE_BODY_LENGTH


class PortalLinkCreate(BaseModel):
    customer_id: uuid.UUID


class PortalLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    created_by_user_id: uuid.UUID
    status: str
    expires_at: datetime
    created_at: datetime


class PortalLinkCreateOut(PortalLinkOut):
    """Same shape as PortalLinkOut, plus the one-time raw token. Only ever
    returned from the create-link response — the token is never
    retrievable again afterwards (only its hash is persisted)."""

    token: str


class PortalProjectOut(BaseModel):
    """What the (unauthenticated) customer sees for one of their projects.
    `notes` is deliberately excluded — it may hold internal staff remarks
    never meant for the customer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    created_at: datetime


class PortalQuoteOut(BaseModel):
    """What the (unauthenticated) customer sees for one of their quotes —
    no customer_id or other internal cross-references."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material: str
    thickness: str
    kitchen_length: float
    price_before_vat: float
    vat: float
    total: float
    created_at: datetime


class PortalPublicOut(BaseModel):
    """The full public view for a token — always 200, even for a revoked
    or expired link (status tells the story, same convention as
    InvitationPublicOut). customer_name is name only, never email/phone:
    the portal confirms identity by possession of the link, not by
    echoing PII back."""

    status: str
    tenant_name: str
    customer_name: str
    expires_at: datetime
    projects: list[PortalProjectOut] = []
    quotes: list[PortalQuoteOut] = []


class PortalMessageCreate(BaseModel):
    """A customer-authored message, posted via their portal token (Sprint
    017, ADR-033) — the first write payload a public portal route accepts.
    Same length cap as the staff-authored side (MessageCreate)."""

    body: str = Field(min_length=1, max_length=MAX_MESSAGE_BODY_LENGTH)

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("message_body_blank", "Message body must not be blank")
        return value
