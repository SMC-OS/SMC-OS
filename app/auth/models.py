import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict


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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
