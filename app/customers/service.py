"""CustomerService — the first real /api/v1/customers logic (Sprint 004).

Route-level code taking a request-scoped session via get_db(), same pattern
app/auth/ established in Sprint 003 (ADR-019) — no repository-interface
layer, that pattern was specifically for the pre-database era (ADR-001).
"""

import uuid

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.customers.models import CustomerCreate
from app.database import crud
from app.database.models import Customer


class CustomerService:
    def list_all(self, db: Session, tenant_id: uuid.UUID, limit: int = 20) -> list[Customer]:
        return crud.list_customers(db, tenant_id, limit=limit)

    def get(self, db: Session, customer_id: uuid.UUID, tenant_id: uuid.UUID) -> Customer | None:
        return crud.get_customer_by_id(db, customer_id, tenant_id)

    def create(self, db: Session, data: CustomerCreate, tenant_id: uuid.UUID) -> Customer:
        customer = crud.create_customer(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=data.name,
            email=data.email,
            phone=data.phone,
        )
        # Sprint 004: the backend now logs this itself, replacing the
        # frontend's previous standalone api.logActivity() call — creation
        # and its activity record happen atomically in one place.
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.CUSTOMER_ADDED,
                title="New customer added",
                description=customer.name,
            ),
            tenant_id=tenant_id,
        )
        return customer


customer_service = CustomerService()
