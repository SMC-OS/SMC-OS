"""CustomerService — the first real /api/v1/customers logic (Sprint 004).

Route-level code taking a request-scoped session via get_db(), same pattern
app/auth/ established in Sprint 003 (ADR-019) — no repository-interface
layer, that pattern was specifically for the pre-database era (ADR-001).
"""

import uuid

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.automations.dispatcher import automation_dispatcher
from app.customers.models import (
    CustomerContextOut,
    CustomerCreate,
    CustomerProjectSummary,
    CustomerQuoteSummary,
    CustomerUpdate,
)
from app.database import crud
from app.projects import pipeline as project_pipeline
from app.projects import pipeline_config
from app.database.models import Customer


class CustomerService:
    def list_all(self, db: Session, tenant_id: uuid.UUID, limit: int = 20) -> list[Customer]:
        return crud.list_customers(db, tenant_id, limit=limit)

    def get(self, db: Session, customer_id: uuid.UUID, tenant_id: uuid.UUID) -> Customer | None:
        return crud.get_customer_by_id(db, customer_id, tenant_id)

    # Sprint 036 — a project is "open" until it reaches the end of the
    # pipeline. Defined here once rather than inline at each call site so
    # the dashboard and the customer page cannot disagree about it.
    #
    # Sprint 039 — expressed as trade-neutral *roles* rather than the
    # literal stage key "complete", which only ever closed a stone
    # tenant's jobs and silently counted every cancelled job as still
    # open.
    _CLOSED_PROJECT_ROLES = frozenset(project_pipeline.TERMINAL_ROLES)

    def get_context(
        self, db: Session, customer_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> CustomerContextOut | None:
        customer = crud.get_customer_by_id(db, customer_id, tenant_id)
        if customer is None:
            return None

        # The tenant-then-customer argument order matters: these are the
        # same helpers the customer portal uses (Sprint 013), reused rather
        # than reimplemented so a customer's quote list is defined in
        # exactly one place. Both filter on tenant_id as well as
        # customer_id — a customer id being valid is never treated as
        # proof of ownership (ADR-029).
        quotes = crud.list_quotes_by_customer(db, tenant_id, customer_id)
        projects = crud.list_projects_by_customer(db, tenant_id, customer_id)

        pipeline = pipeline_config.resolve(db, tenant_id)

        return CustomerContextOut(
            customer=customer,
            quotes=[CustomerQuoteSummary.model_validate(q) for q in quotes],
            projects=[_project_summary(p, pipeline) for p in projects],
            quoted_value=sum(q.total or 0.0 for q in quotes),
            approved_value=sum(
                q.total or 0.0 for q in quotes if q.status == "approved"
            ),
            open_projects=sum(
                1
                for p in projects
                if pipeline.role_of(p.status) not in self._CLOSED_PROJECT_ROLES
            ),
        )

    def update(
        self,
        db: Session,
        customer_id: uuid.UUID,
        tenant_id: uuid.UUID,
        data: CustomerUpdate,
    ) -> Customer | None:
        """Sprint 036 (Workstream D). `exclude_unset=True` is the whole
        contract: a field the client didn't send is left alone, a field it
        sent as null is genuinely cleared. Returns None for an unknown id
        or one belonging to another tenant — the caller turns that into a
        404, never a 403 (ADR-028: confirming another tenant's id exists is
        itself a leak)."""
        changes = data.model_dump(exclude_unset=True)
        if not changes:
            return crud.get_customer_by_id(db, customer_id, tenant_id)
        return crud.update_customer(db, customer_id, tenant_id, changes)

    def create(self, db: Session, data: CustomerCreate, tenant_id: uuid.UUID) -> Customer:
        customer = crud.create_customer(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=data.name,
            email=data.email,
            phone=data.phone,
            customer_type=data.customer_type,
            company_name=data.company_name,
            address_line1=data.address_line1,
            address_line2=data.address_line2,
            city=data.city,
            postcode=data.postcode,
            notes=data.notes,
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
        # Sprint 036 (Workstream G) — dispatched after the customer has
        # committed, and total: a broken automation records a failed run
        # and is swallowed, so adding a customer can never fail because of
        # a rule someone wrote.
        automation_dispatcher.dispatch_customer_created(db, customer)
        return customer


customer_service = CustomerService()


def _project_summary(project, pipeline) -> CustomerProjectSummary:
    """One project row with its stage resolved into words the panel can
    render directly. Falls back to the raw stage key rather than to a
    placeholder, same reasoning as the portal's own resolver."""
    out = CustomerProjectSummary.model_validate(project)
    stage = pipeline.get(project.status)
    out.status_label = stage.label if stage is not None else project.status
    out.status_role = stage.role if stage is not None else None
    return out
