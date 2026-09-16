import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.auth.password_policy import validate_password_strength


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

    # Sprint 038 — not columns on Invitation itself (absent from the ORM
    # row, so model_validate(row) leaves these None); populated by the
    # router from the invitation's latest app.communications.Communication
    # row, if one exists. `status` above is unchanged (still the
    # membership lifecycle: pending/accepted/revoked/expired) —
    # delivery_status is the separate, truthful record of whether the
    # invitation *email* itself reached a mailbox, so a "pending" (not yet
    # accepted) invitation whose email failed to send doesn't quietly look
    # the same as one that's sitting unread in someone's inbox.
    delivery_status: str | None = None
    delivery_failure_detail: str | None = None


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
    # Sprint 039 Production Readiness Defect Gate, final auth gate — same
    # policy as SignupRequest.password and ResetPasswordRequest.new_password
    # (app.auth.password_policy); previously unvalidated.
    password: str

    @field_validator("password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        return validate_password_strength(value)
