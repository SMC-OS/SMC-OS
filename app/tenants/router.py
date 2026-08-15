import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.database.models import User
from app.tenants.models import TenantCreate, TenantOut
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
