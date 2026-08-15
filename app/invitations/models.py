import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InvitationCreate(BaseModel):
    email: str


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: str
    status: str
    invited_by_user_id: uuid.UUID
    expires_at: datetime
    created_at: datetime


class InvitationCreateOut(InvitationOut):
    """Same shape as InvitationOut, plus the one-time raw token. Only ever
    returned from the create-invitation response — the token is never
    retrievable again afterwards (only its hash is persisted)."""

    token: str


class InvitationPublicOut(BaseModel):
    """What the (unauthenticated) invitee sees on the accept page — no
    internal IDs, just enough to render the invite and let them decide
    whether to accept."""

    email: str
    role: str
    tenant_name: str
    status: str
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    name: str
    password: str
