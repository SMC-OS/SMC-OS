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
    # happened.
    email_verified_at: datetime | None = None
    # Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix —
    # whether this user is CURRENTLY blocked from normal application
    # access (app.auth.dependencies.is_verification_required's exact
    # predicate). Deliberately separate from email_verified_at: a legacy
    # user within their grace period has email_verified_at=None but
    # verification_required=False, and the frontend must route on this
    # field, not on email_verified_at directly, to match the backend's
    # own enforcement exactly rather than re-deriving the legacy-grace
    # math itself.
    verification_required: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class VerificationResendResponse(BaseModel):
    """Sprint 039 Production Readiness Defect Gate, Blocker 2 follow-up
    (verification resend/token hotfix) — a dedicated response for
    POST /auth/email/verify/resend, distinct from the shared
    MessageResponse every other endpoint below uses.

    The bug this fixes: resend_verification_email() returns 200
    whether it actually queued a new email or silently no-op'd because
    the caller was already verified — before this field existed, the
    frontend had no way to tell those apart, so a resend after
    verification looked exactly like a truthful "check your inbox"
    with no second email ever coming (confirmed live on staging,
    2026-09-16, against a real Resend-backed environment — not a
    hypothetical). `already_verified=True` lets the caller render an
    honest "you're already verified" instead.
    """

    message: str
    already_verified: bool


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
