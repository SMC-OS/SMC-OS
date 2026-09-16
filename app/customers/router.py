import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_verified_email
from app.customers.models import (
    CustomerContextOut,
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
)
from app.customers.service import customer_service
from app.database.database import get_db
from app.database.models import User

router = APIRouter(
    prefix="/customers", tags=["customers"], dependencies=[Depends(require_verified_email)]
)


@router.get("", response_model=list[CustomerOut])
def list_customers(
    limit: int = 20, current_user: User = Depends(require_verified_email), db: Session = Depends(get_db)
):
    return customer_service.list_all(db, tenant_id=current_user.tenant_id, limit=limit)


# Sprint 036 (Workstream D) — declared BEFORE /{customer_id} so the
# literal path segment wins: FastAPI matches in declaration order, and a
# later static route under a uuid param would be unreachable. (Same
# ordering rule app/tenants/router.py documents for /me/profile.)
@router.get("/{customer_id}/context", response_model=CustomerContextOut)
def get_customer_context(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    """Everything the customer detail page needs to show business context
    rather than raw fields: this customer's quotes, their projects, and
    the money those represent. One call rather than three so the page has
    no partially-loaded intermediate state.

    Every underlying query is filtered by BOTH customer_id and the
    caller's own tenant_id (see crud.list_quotes_by_customer) — the
    customer id being valid is never treated as proof of ownership.
    """
    context = customer_service.get_context(
        db, customer_id, tenant_id=current_user.tenant_id
    )
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return context


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    customer = customer_service.get(db, customer_id, tenant_id=current_user.tenant_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    data: CustomerCreate,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    return customer_service.create(db, data, tenant_id=current_user.tenant_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: uuid.UUID,
    data: CustomerUpdate,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    """Sprint 036 (Workstream D). No require_role: editing a customer's
    address is routine work, the same posture as creating one — matching
    the customer/project/document/portal-link precedent rather than the
    Owner-only gating reserved for tenant-control decisions (team, billing,
    company identity).

    A customer belonging to another tenant 404s rather than 403s (ADR-028).
    """
    customer = customer_service.update(
        db, customer_id, tenant_id=current_user.tenant_id, data=data
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer
