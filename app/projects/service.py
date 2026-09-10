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
from app.automations.dispatcher import automation_dispatcher
from app.customers.models import CustomerCreate
from app.projects import pipeline as pipeline_module
from app.projects import pipeline_config
from app.projects.models import ProjectCreate, ProjectUpdate
from app.database import crud
from app.database.models import Customer, Project


class CustomerNotFoundError(Exception):
    """Raised by create() when data.customer_id doesn't belong to the
    caller's own tenant (Sprint 012, ADR-029) — otherwise a project could
    be linked to another tenant's customer by guessing/knowing its id, a
    relationship-level tenant-boundary bypass the id/get_project_by_id
    checks alone don't cover."""


class ProjectNotInEnquiryStateError(Exception):
    """Raised by convert_to_customer() when the tenant-scoped Project is no
    longer at a `lead`-role stage (Sprint 021, docs/SPRINTS/sprint-021.md
    §4, Decision 1) — same service-raises-a-domain-error /
    router-maps-to-HTTP convention as QuoteApprovalStateError
    (app/quotes/service.py).

    Sprint 039 changed the gate from `status == "enquiry"` to the stage's
    trade-neutral *role*, so it means the same thing for a stone tenant
    (whose lead stage is called "enquiry") and for a tenant on the
    standard pipeline (whose lead stage is called "lead"). The name is
    kept because it is what the router, its HTTP message and its tests
    already say, and "enquiry" is still the product word for a job at
    this stage."""


class InvalidProjectTransitionError(Exception):
    """Raised by update_status() when the requested stage is not one the
    Project's current stage allows.

    Sprint 023 enforced this against a fixed linear sequence. Sprint 039
    (Workstream D) enforces it against the caller's own pipeline graph
    (app/projects/pipeline.py) instead, which still covers every case
    Sprint 023 did — a repeat, a skip, any backward move, any transition
    out of a terminal stage — and adds two more: a stage key this tenant's
    pipeline does not contain at all, and an attempt to reach a terminal
    stage by coming off hold."""


class AssignedUserNotFoundError(Exception):
    """Raised by assign() when assigned_user_id doesn't resolve to a user
    in the caller's own tenant (Sprint 023 §5) — same
    tenant-scoped-lookup-hides-existence convention as
    CustomerNotFoundError above."""


_with_role = pipeline_config.attach_role


class ProjectService:
    def pipeline(self, db: Session, tenant_id: uuid.UUID):
        """This tenant's own pipeline. Exposed so the router can serve
        `GET /projects/meta/pipeline` without reaching past the service
        into pipeline_config itself."""
        return pipeline_config.resolve(db, tenant_id)

    def list_all(self, db: Session, tenant_id: uuid.UUID, limit: int = 20) -> list[Project]:
        pipeline = pipeline_config.resolve(db, tenant_id)
        return [
            _with_role(project, pipeline)
            for project in crud.list_projects(db, tenant_id, limit=limit)
        ]

    def get(self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID) -> Project | None:
        return _with_role(
            crud.get_project_by_id(db, project_id, tenant_id),
            pipeline_config.resolve(db, tenant_id),
        )

    def create(self, db: Session, data: ProjectCreate, tenant_id: uuid.UUID) -> Project:
        if data.customer_id is not None and crud.get_customer_by_id(
            db, data.customer_id, tenant_id
        ) is None:
            raise CustomerNotFoundError(data.customer_id)

        # Sprint 039 — a new job starts at whatever this tenant calls its
        # first stage, never at a hardcoded "enquiry".
        pipeline = pipeline_config.resolve(db, tenant_id)

        project = crud.create_project(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=data.name,
            customer_id=data.customer_id,
            notes=data.notes,
            status=pipeline.initial_stage().key,
            project_type=data.project_type,
            description=data.description,
            site_address_line1=data.site_address_line1,
            site_address_line2=data.site_address_line2,
            site_city=data.site_city,
            site_postcode=data.site_postcode,
            start_date=data.start_date,
            target_completion_date=data.target_completion_date,
            estimated_value=data.estimated_value,
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
        automation_dispatcher.dispatch_project_created(db, project)
        return _with_role(project, pipeline)

    def update(
        self,
        db: Session,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        data: ProjectUpdate,
    ) -> Project | None:
        """Sprint 036 (Workstream F). Partial update of a project's own
        details — never its status, which keeps its own endpoint and its
        own linear-transition rules (update_status below).

        A customer_id the caller doesn't own raises CustomerNotFoundError,
        the same relationship-linkage check create() already performs: an
        UPDATE is exactly as capable of linking a project to another
        tenant's customer as an INSERT is.
        """
        changes = data.model_dump(exclude_unset=True)

        if changes.get("customer_id") is not None and crud.get_customer_by_id(
            db, changes["customer_id"], tenant_id
        ) is None:
            raise CustomerNotFoundError(changes["customer_id"])

        pipeline = pipeline_config.resolve(db, tenant_id)
        if not changes:
            return _with_role(crud.get_project_by_id(db, project_id, tenant_id), pipeline)
        return _with_role(crud.update_project(db, project_id, tenant_id, changes), pipeline)

    def update_status(
        self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID, status: str
    ) -> Project | None:
        """Move a project to another stage of its tenant's own pipeline.

        Sprint 039 (Workstream D): the target must be in the current
        stage's `allowed_transitions` (app/projects/pipeline.py) — which
        keeps Sprint 023's no-skip/no-reverse/terminal-is-terminal rules
        and adds hold, resume and cancel. Anything else raises
        InvalidProjectTransitionError, including a stage key this tenant's
        pipeline does not contain.

        The status write and its PROJECT_STATUS_CHANGED activity are one
        transaction, same caller-owned-transaction pattern as Sprint
        021/022."""
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            return None

        pipeline = pipeline_config.resolve(db, tenant_id)

        # Captured as a plain str, not read from `project` again below:
        # crud.update_project_status's query re-fetches the same row via
        # SQLAlchemy's identity map, so `project` and that row are the same
        # Python object — mutating one's `.status` mutates both in place.
        previous_status = project.status

        if status not in pipeline.allowed_transitions(previous_status):
            raise InvalidProjectTransitionError(previous_status, status)

        try:
            updated = crud.update_project_status(
                db, project_id, tenant_id, status, commit=False
            )
            activity_service.log(
                ActivityEventCreate(
                    type=ActivityType.PROJECT_STATUS_CHANGED,
                    title="Project status changed",
                    description=f"Project {project_id} moved from {previous_status} to {status}",
                ),
                tenant_id=tenant_id,
                db=db,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        # Sprint 036 (Workstream G) — dispatched only after the status
        # write and its activity event have committed together, and
        # outside the try/except above on purpose: an automation must
        # never be able to roll back the transition that triggered it.
        automation_dispatcher.dispatch_project_status_changed(
            db, updated, previous_status
        )
        return _with_role(updated, pipeline)

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

        return _with_role(updated, pipeline_config.resolve(db, tenant_id))

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

        # Sprint 039 — gated on the stage's trade-neutral role, so this
        # means the same thing whatever this tenant calls its first stage.
        pipeline = pipeline_config.resolve(db, tenant_id)
        if pipeline.role_of(project.status) != pipeline_module.LEAD:
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
