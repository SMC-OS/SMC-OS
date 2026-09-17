"""The workflow service — resolving which template/stage a new project
binds to, and (from Task 5 onward) evaluating and performing transitions.

Task 4 covers only the read-side and the initial-binding lookup;
transition/hold/resume/cancel land in app/workflows/service.py's own
later additions without changing what's here.
"""

import uuid

from sqlalchemy.orm import Session

from app.database import crud
from app.workflows.catalogue import template_for_trade
from app.workflows.models import ProjectWorkflowSummary, WorkflowRole


def resolve_initial_binding(db: Session, trade_key: str | None) -> tuple[uuid.UUID, uuid.UUID]:
    """The (workflow_template_id, workflow_stage_id) a brand-new project
    for this trade should be born with — always the template's own first
    (position 0) stage, i.e. "Enquiry". An unknown/absent trade never
    silently becomes stone: `template_for_trade` itself already falls
    back to the safe general template.

    A real DB lookup, not a re-derivation from the Python catalogue's own
    key-slugging — the seeded rows are the single source of truth once
    the migration has run, and this keeps this function correct even if
    catalogue.py's slugging logic changes in a later sprint."""
    template_key = template_for_trade(trade_key).key
    template = crud.get_system_workflow_template_by_key(db, template_key)
    if template is None:
        # Should not happen outside a broken/unmigrated database — the
        # general fallback template is always seeded. Fail loudly rather
        # than binding a project to nothing.
        raise WorkflowTemplateNotSeededError(template_key)
    stages = crud.list_workflow_stages(db, template.id)
    first_stage = next(s for s in stages if s.position == 0)
    return template.id, first_stage.id


def get_project_workflow(db: Session, project, tenant_id: uuid.UUID) -> ProjectWorkflowSummary | None:
    """The current workflow summary for an already-bound project. Returns
    None only if the project itself doesn't belong to the caller's tenant
    (the router maps that to 404, same as every other project lookup) —
    never for a project with no binding, since that's now a schema
    invariant (workflow_template_id/workflow_stage_id are NOT NULL)."""
    if project is None or project.tenant_id != tenant_id:
        return None
    template = crud.get_workflow_template(db, project.workflow_template_id)
    stage = crud.get_workflow_stage(db, project.workflow_stage_id)
    return ProjectWorkflowSummary(
        template_key=template.key,
        template_name=template.name,
        stage_key=stage.key,
        stage_label=stage.label,
        role=WorkflowRole(stage.role),
    )


class WorkflowTemplateNotSeededError(Exception):
    """Raised by resolve_initial_binding when even the general fallback
    template is missing — a migration/environment problem, never a
    reachable state via any normal request."""
