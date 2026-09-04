import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.auth.models import UserRole
from app.database.database import get_db
from app.database.models import User
from app.tenants.models import (
    TenantCreate,
    TenantOut,
    TenantProfileOut,
    TenantProfileUpdate,
)
from app.tenants.service import tenant_service

# Sprint 008: requires the existing seeded-owner token (get_current_user),
# same posture as app/customers/router.py — NOT tenant-scoped auth (that's
# Sprint 009). This just avoids an unauthenticated public write endpoint by
# reusing the one auth gate that already exists. These routes are internal
# scaffolding, not yet wired to any real signup flow.
#
# Sprint 012 (ADR-029) — GET (list) and GET/{id} previously returned every
# tenant in the system to any authenticated caller (a real cross-tenant
# leak: name/slug/status of every other company, predating this sprint).
# Both now return only the caller's own tenant. POST was audited per
# ADR-029 and left unchanged: creating a new, unlinked tenant doesn't read
# or expose any other tenant's existing data, so it isn't an isolation
# leak — it's a separate, pre-existing tenant-lifecycle question (should
# this route even still be reachable now that POST /api/v1/auth/signup is
# the real way to create a workspace?) explicitly out of scope for a
# tenant-*isolation* sprint.
router = APIRouter(
    prefix="/tenants", tags=["tenants"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[TenantOut])
def get_my_tenant(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # `limit` is accepted (unused) only to avoid a 422 for existing callers
    # passing ?limit= — the response is always the caller's own tenant, at
    # most one row, never another tenant's.
    tenant = tenant_service.get(db, current_user.tenant_id)
    return [tenant] if tenant is not None else []


# Sprint 034 — company identity. Declared BEFORE /{tenant_id} on purpose:
# FastAPI matches in declaration order, and "me" would otherwise be parsed
# as a uuid path param and 422 before ever reaching this handler.
#
# Both routes are hard-scoped to the caller's own tenant — there is no
# tenant_id parameter to tamper with, so no cross-tenant write is
# expressible through this API at all (ADR-029's posture, enforced by
# construction rather than by a check).
@router.get("/me/profile", response_model=TenantProfileOut)
def get_my_company_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant = tenant_service.get(db, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.patch("/me/profile", response_model=TenantProfileOut)
def update_my_company_profile(
    data: TenantProfileUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    """Owner-only: this is the business's legal and statutory identity as it
    appears on every quote and invoice its customers receive, so it sits
    alongside billing and team management rather than with general staff
    settings."""
    tenant = tenant_service.update_identity(db, current_user.tenant_id, data)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Cross-tenant lookups 404, never 403 (ADR-028's precedent) — confirming
    # that another tenant's id exists at all is itself a leak.
    if tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant = tenant_service.get(db, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(data: TenantCreate, db: Session = Depends(get_db)):
    return tenant_service.create(db, data)
