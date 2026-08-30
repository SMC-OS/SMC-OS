"""ProjectService — the first module to move a record through a status
pipeline (Sprint 006). Route-level code taking a request-scoped session via
get_db(), same pattern app/customers/ and app/materials/ established
(ADR-019) — no repository interface, that pattern was for the pre-database
era (ADR-001).
"""

import uuid

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.customers.models import CustomerCreate
from app.projects.models import ProjectCreate, ProjectStatus
from app.database import crud
from app.database.models import Customer, Project


class CustomerNotFoundError(Exception):
    """Raised by create() when data.customer_id doesn't belong to the
    caller's own tenant (Sprint 012, ADR-029) — otherwise a project could
    be linked to another tenant's customer by guessing/knowing its id, a
    relationship-level tenant-boundary bypass the id/get_project_by_id
    checks alone don't cover."""


class ProjectNotInEnquiryStateError(Exception):
    """Raised by convert_to_customer() when the tenant-scoped Project's
    status isn't "enquiry" (Sprint 021, docs/SPRINTS/sprint-021.md §4,
    Decision 1) — same service-raises-a-domain-error /
    router-maps-to-HTTP convention as QuoteApprovalStateError
    (app/quotes/service.py)."""


class ProjectService:
    def list_all(self, db: Session, tenant_id: uuid.UUID, limit: int = 20) -> list[Project]:
        return crud.list_projects(db, tenant_id, limit=limit)

    def get(self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID) -> Project | None:
        return crud.get_project_by_id(db, project_id, tenant_id)

    def create(self, db: Session, data: ProjectCreate, tenant_id: uuid.UUID) -> Project:
        if data.customer_id is not None and crud.get_customer_by_id(
            db, data.customer_id, tenant_id
        ) is None:
            raise CustomerNotFoundError(data.customer_id)

        project = crud.create_project(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=data.name,
            customer_id=data.customer_id,
            notes=data.notes,
            status=ProjectStatus.ENQUIRY.value,
        )
        # Sprint 004 established this pattern for customers — the backend
        # logs its own ActivityEvent, replacing a standalone frontend call.
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.PROJECT_CREATED,
                title="Project started",
                description=project.name,
            ),
            tenant_id=tenant_id,
        )
        return project

    def update_status(
        self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID, status: ProjectStatus
    ) -> Project | None:
        return crud.update_project_status(db, project_id, tenant_id, status.value)

    def convert_to_customer(
        self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID, data: CustomerCreate
    ) -> Customer | None:
        """Sprint 021 (docs/SPRINTS/sprint-021.md §4). Conversion is only
        allowed while the Project is still "enquiry" — including an
        already-linked Project that has since advanced past it, which must
        still be rejected rather than idempotently returning its Customer
        (status is checked before the idempotency short-circuit below).
        Project-level idempotent within that: a Project already linked to a
        Customer returns that same Customer instead of creating another one
        — the existing linked Customer is authoritative, never overwritten
        by a retry's payload, and this early return happens before activity
        logging below, so a retry emits no additional ENQUIRY_CONVERTED
        event — only the first real conversion does."""
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            return None

        if project.status != ProjectStatus.ENQUIRY.value:
            raise ProjectNotInEnquiryStateError(project.status)

        if project.customer_id is not None:
            existing_customer = crud.get_customer_by_id(db, project.customer_id, tenant_id)
            if existing_customer is not None:
                return existing_customer

        customer = crud.create_customer(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=data.name,
            email=data.email,
            phone=data.phone,
        )
        crud.update_project_customer(db, project_id, tenant_id, customer.id)

        # Sprint 021 — same backend-logs-its-own-ActivityEvent convention as
        # QUOTE_HANDED_OFF (app/quotes/service.py). Safe content only: no
        # email/phone/name, just the two ids involved in the transition.
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.ENQUIRY_CONVERTED,
                title="Enquiry converted",
                description=f"Project {project.id} converted to customer {customer.id}",
            ),
            tenant_id=tenant_id,
        )

        return customer


project_service = ProjectService()
