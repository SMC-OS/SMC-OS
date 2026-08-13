import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.tenants.models import TenantCreate, TenantOut
from app.tenants.service import tenant_service

# Sprint 008: requires the existing seeded-owner token (get_current_user),
# same posture as app/customers/router.py — NOT tenant-scoped auth (that's
# Sprint 009). This just avoids an unauthenticated public write endpoint by
# reusing the one auth gate that already exists. These routes are internal
# scaffolding, not yet wired to any real signup flow.
router = APIRouter(
    prefix="/tenants", tags=["tenants"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[TenantOut])
def list_tenants(limit: int = 20, db: Session = Depends(get_db)):
    return tenant_service.list_all(db, limit=limit)


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    tenant = tenant_service.get(db, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(data: TenantCreate, db: Session = Depends(get_db)):
    return tenant_service.create(db, data)
