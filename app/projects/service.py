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


class InvalidProjectTransitionError(Exception):
    """Raised by update_status() when the requested status isn't the exact
    next value in the linear pipeline for the Project's current status
    (Sprint 023, docs/SPRINTS/sprint-023.md §4/Decision 4) — covers a
    repeat, a skip, any backward move, and any transition attempted from
    the terminal "complete" status."""


class AssignedUserNotFoundError(Exception):
    """Raised by assign() when assigned_user_id doesn't resolve to a user
    in the caller's own tenant (Sprint 023 §5) — same
    tenant-scoped-lookup-hides-existence convention as
    CustomerNotFoundError above."""


# The linear pipeline (Sprint 006, unchanged): each status's only valid
# next value is the one immediately after it here. "complete" has none —
# it is terminal (Sprint 023 §4).
_STATUS_SEQUENCE = list(ProjectStatus)


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
        """Sprint 023 (docs/SPRINTS/sprint-023.md §4): only the exact next
        value in `_STATUS_SEQUENCE` is accepted — a repeat, a skip, any
        backward move, or any transition from the terminal "complete"
        status raises InvalidProjectTransitionError. The status write and
        its PROJECT_STATUS_CHANGED activity are one transaction, same
        caller-owned-transaction pattern as Sprint 021/022."""
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            return None

        # Captured as a plain str, not read from `project` again below:
        # crud.update_project_status's query re-fetches the same row via
        # SQLAlchemy's identity map, so `project` and that row are the same
        # Python object — mutating one's `.status` mutates both in place.
        previous_status = project.status

        current_index = _STATUS_SEQUENCE.index(ProjectStatus(previous_status))
        next_status = (
            _STATUS_SEQUENCE[current_index + 1]
            if current_index + 1 < len(_STATUS_SEQUENCE)
            else None
        )
        if status != next_status:
            raise InvalidProjectTransitionError(previous_status, status.value)

        try:
            updated = crud.update_project_status(
                db, project_id, tenant_id, status.value, commit=False
            )
            activity_service.log(
                ActivityEventCreate(
                    type=ActivityType.PROJECT_STATUS_CHANGED,
                    title="Project status changed",
                    description=f"Project {project_id} moved from {previous_status} to {status.value}",
                ),
                tenant_id=tenant_id,
                db=db,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        return updated

    def assign(
        self,
        db: Session,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        assigned_user_id: uuid.UUID | None,
    ) -> Project | None:
        """Sprint 023 §5. `assigned_user_id: None` always succeeds (no
        lookup needed) — an explicit unassignment, not a no-op. The
        assignment write and its PROJECT_ASSIGNED activity are one
        transaction, same pattern as update_status above."""
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            return None

        if assigned_user_id is not None:
            target_user = crud.get_user_by_id(db, assigned_user_id)
            if target_user is None or target_user.tenant_id != tenant_id:
                raise AssignedUserNotFoundError(assigned_user_id)

        description = (
            f"Project {project_id} assigned to {assigned_user_id}"
            if assigned_user_id is not None
            else f"Project {project_id} unassigned"
        )

        try:
            updated = crud.update_project_assignment(
                db, project_id, tenant_id, assigned_user_id, commit=False
            )
            activity_service.log(
                ActivityEventCreate(
                    type=ActivityType.PROJECT_ASSIGNED,
                    title="Project assigned",
                    description=description,
                ),
                tenant_id=tenant_id,
                db=db,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        return updated

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
        event — only the first real conversion does.

        The three writes below (Customer, Project.customer_id, the
        ENQUIRY_CONVERTED activity) are one logical transaction: each write
        happens with commit=False on this same request-scoped `db`, and
        this method commits exactly once at the end. If any step raises —
        including activity_service.log, since it's passed this same `db` —
        the whole transaction rolls back and the original exception
        propagates; nothing partial survives."""
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            return None

        if project.status != ProjectStatus.ENQUIRY.value:
            raise ProjectNotInEnquiryStateError(project.status)

        if project.customer_id is not None:
            existing_customer = crud.get_customer_by_id(db, project.customer_id, tenant_id)
            if existing_customer is not None:
                return existing_customer

        try:
            customer = crud.create_customer(
                db,
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name=data.name,
                email=data.email,
                phone=data.phone,
                commit=False,
            )
            crud.update_project_customer(db, project_id, tenant_id, customer.id, commit=False)

            # Sprint 021 — same backend-logs-its-own-ActivityEvent
            # convention as QUOTE_HANDED_OFF (app/quotes/service.py). Safe
            # content only: no email/phone/name, just the two ids involved
            # in the transition. Passing `db` folds this write into the
            # same not-yet-committed transaction as the two writes above.
            activity_service.log(
                ActivityEventCreate(
                    type=ActivityType.ENQUIRY_CONVERTED,
                    title="Enquiry converted",
                    description=f"Project {project.id} converted to customer {customer.id}",
                ),
                tenant_id=tenant_id,
                db=db,
            )

            db.commit()
        except Exception:
            db.rollback()
            raise

        return customer


project_service = ProjectService()
