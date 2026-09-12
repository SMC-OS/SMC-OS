import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    """Sprint 010 — formalizes `role` as a fixed set of values instead of
    a free string. Stored as a plain String column on `users`
    (app/database/models.py), same convention as ProjectStatus/
    ActivityType/NotificationType — no native Postgres enum, no DB CHECK
    constraint; validated at the Pydantic/API boundary only.

    STAFF exists here because it's part of the anticipated permission
    model (docs/USER_ROLES.md §2), but there is still no way to create a
    Staff user — that's Sprint 011's invitations. Every user today is an
    Owner.
    """

    OWNER = "Owner"
    STAFF = "Staff"


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    """Sprint 009 — creates a new Tenant + its first User (Owner) in one
    call. See app/auth/service.py's AuthService.signup()."""

    company_name: str
    name: str
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: UserRole | None = None
    # Sprint 009 — every user now belongs to exactly one tenant. Built via
    # AuthService.build_user_out(), not automatic from_attributes validation
    # (tenant_name isn't a column on `users`, it's resolved from `tenants`).
    tenant_id: uuid.UUID
    tenant_name: str
    # Sprint 039 Production Readiness Defect Gate, Blocker 1 — lets the
    # frontend show a clear verified/unverified state without a second
    # request. None means unverified (including every legacy user this
    # migration didn't backfill); a datetime is when verification
    # happened. Whether an unverified user is currently *blocked* by it
    # is a separate question the frontend doesn't need to compute itself
    # (see app/auth/dependencies.py's require_verified_email).
    email_verified_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MessageResponse(BaseModel):
    """Generic {"message": "..."} body for endpoints that intentionally
    reveal nothing more specific than a human-readable status line — see
    ForgotPasswordRequest's endpoint, where the whole point is a response
    that is identical whether or not the account exists (Sprint 039
    Production Readiness Defect Gate, Blocker 2)."""

    message: str


class VerifyEmailConfirmRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    # Sprint 039 Blocker 2's password policy: a minimum length only — no
    # character-class rules (no invented "must contain a symbol" beyond
    # what this product has ever asked of a password, including at
    # signup, which enforces nothing at all beyond "non-empty").
    new_password: str = Field(min_length=8)
