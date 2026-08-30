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
        """Sprint 021 (docs/SPRINTS/sprint-021.md §4). Project-level
        idempotent: a Project already linked to a Customer returns that same
        Customer instead of creating another one — the existing linked
        Customer is authoritative, never overwritten by a retry's payload.
        Still deliberately does not yet handle a non-"enquiry" status (409)
        or activity logging — those are later RED/GREEN cycles."""
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            return None

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

        return customer


project_service = ProjectService()
