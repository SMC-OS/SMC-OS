import uuid

from pydantic import BaseModel, ConfigDict


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
    role: str | None = None
    # Sprint 009 — every user now belongs to exactly one tenant. Built via
    # AuthService.build_user_out(), not automatic from_attributes validation
    # (tenant_name isn't a column on `users`, it's resolved from `tenants`).
    tenant_id: uuid.UUID
    tenant_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
