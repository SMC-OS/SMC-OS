"""The workflow service — resolving which template/stage a new project
binds to (Task 4), and evaluating/performing transitions, Hold, Resume and
Cancel (Task 5).
"""

import uuid

from sqlalchemy.orm import Session

from app.automations.dispatcher import automation_dispatcher
from app.database import crud
from app.database.models import Project, WorkflowStage
from app.workflows.catalogue import template_for_trade
from app.workflows.models import (
    ProjectWorkflowDetail,
    ProjectWorkflowSummary,
    WorkflowHistoryEntry,
    WorkflowRole,
    WorkflowTransitionOption,
)


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


def is_legacy_binding(db: Session, project: Project) -> bool:
    """True only for a project still bound to the immutable legacy_v1
    template — the one case where the old PATCH /projects/{id}/status
    endpoint is still allowed to move the project (Task 5)."""
    template = crud.get_workflow_template(db, project.workflow_template_id)
    return template is not None and template.key == "legacy_v1"


def _allowed_target_stages(db: Session, project: Project, current: WorkflowStage) -> list[WorkflowStage]:
    """The real WorkflowStage rows a project on `current` could move to
    next. Terminal stages (Complete, Cancelled) have none. A project
    on_hold's only edges are the graph's own on_hold -> cancelled plus the
    synthetic Resume option below (never a static graph edge, since its
    target is per-project) — every other stage's options come straight
    from the seeded WorkflowTransition graph."""
    if current.is_terminal:
        return []

    options = [
        crud.get_workflow_stage(db, edge.to_stage_id)
        for edge in crud.list_allowed_transitions(db, project.workflow_template_id, current.id)
    ]

    if WorkflowRole(current.role) == WorkflowRole.ON_HOLD and project.workflow_previous_active_stage_id:
        resume_target = crud.get_workflow_stage(db, project.workflow_previous_active_stage_id)
        if resume_target is not None:
            options.insert(0, resume_target)

    return options


def get_project_workflow_detail(
    db: Session, project: Project, tenant_id: uuid.UUID
) -> ProjectWorkflowDetail | None:
    """GET /projects/{id}/workflow (Task 5) — the current stage plus every
    stage the project could legally move to next. `blocked_requirements`
    is always [] here; Task 6 populates it from that target stage's own
    gate_definitions without changing this function's shape."""
    if project is None or project.tenant_id != tenant_id:
        return None

    template = crud.get_workflow_template(db, project.workflow_template_id)
    stage = crud.get_workflow_stage(db, project.workflow_stage_id)

    allowed = [
        WorkflowTransitionOption(
            stage_key=option.key,
            stage_label=option.label,
            role=WorkflowRole(option.role),
            blocked_requirements=[],
        )
        for option in _allowed_target_stages(db, project, stage)
    ]

    return ProjectWorkflowDetail(
        template_key=template.key,
        template_name=template.name,
        stage_key=stage.key,
        stage_label=stage.label,
        role=WorkflowRole(stage.role),
        is_terminal=stage.is_terminal,
        allowed_transitions=allowed,
    )


def get_project_workflow_history(
    db: Session, project: Project, tenant_id: uuid.UUID
) -> list[WorkflowHistoryEntry] | None:
    """GET /projects/{id}/workflow/history (Task 5) — the append-only
    audit trail, newest-last (same order list_project_workflow_history
    already returns), with each row's stage ids resolved to their stable
    key/label for display."""
    if project is None or project.tenant_id != tenant_id:
        return None

    rows = crud.list_project_workflow_history(db, project.id, tenant_id)
    entries = []
    for row in rows:
        from_stage = crud.get_workflow_stage(db, row.from_stage_id) if row.from_stage_id else None
        to_stage = crud.get_workflow_stage(db, row.to_stage_id)
        entries.append(
            WorkflowHistoryEntry(
                id=row.id,
                from_stage_key=from_stage.key if from_stage else None,
                from_stage_label=from_stage.label if from_stage else None,
                to_stage_key=to_stage.key,
                to_stage_label=to_stage.label,
                actor_user_id=row.actor_user_id,
                reason=row.reason,
                created_at=row.created_at,
            )
        )
    return entries


def transition_project_workflow(
    db: Session,
    project: Project,
    tenant_id: uuid.UUID,
    target_stage_key: str,
    reason: str | None,
    actor_user_id: uuid.UUID | None,
) -> Project:
    """Move a project to `target_stage_key` — a normal forward move, Hold,
    Resume or Cancel are all the same operation here, distinguished only
    by which stage the caller names (Task 5).

    The stage write and its ProjectWorkflowHistory row are one atomic
    transaction (mirrors ProjectService.update_status); the automation
    dispatch below happens strictly after that commit and is never allowed
    to roll the transition back."""
    current = crud.get_workflow_stage(db, project.workflow_stage_id)
    if current.is_terminal:
        raise WorkflowTerminalStateError(current.key)

    target = crud.get_workflow_stage_by_key(db, project.workflow_template_id, target_stage_key)
    if target is None:
        raise WorkflowStageNotFoundError(target_stage_key)

    is_resume = (
        WorkflowRole(current.role) == WorkflowRole.ON_HOLD
        and project.workflow_previous_active_stage_id == target.id
    )

    if not is_resume:
        edge = crud.get_workflow_transition(db, project.workflow_template_id, current.id, target.id)
        if edge is None:
            raise WorkflowTransitionNotAllowedError(current.key, target_stage_key)

    if WorkflowRole(target.role) == WorkflowRole.ON_HOLD:
        # Entering Hold: remember where we were so Resume has somewhere
        # to go back to.
        new_previous_active_stage_id = current.id
    elif is_resume:
        # Leaving Hold via Resume: the "previously active" pointer has
        # just been consumed.
        new_previous_active_stage_id = None
    else:
        new_previous_active_stage_id = project.workflow_previous_active_stage_id

    try:
        updated = crud.update_project_workflow(
            db,
            project.id,
            tenant_id,
            workflow_stage_id=target.id,
            workflow_previous_active_stage_id=new_previous_active_stage_id,
            commit=False,
        )
        crud.create_project_workflow_history(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=project.id,
            from_stage_id=current.id,
            to_stage_id=target.id,
            actor_user_id=actor_user_id,
            reason=reason,
            commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    automation_dispatcher.dispatch_project_workflow_transitioned(db, updated, to_stage_key=target.key)
    return updated


class WorkflowTemplateNotSeededError(Exception):
    """Raised by resolve_initial_binding when even the general fallback
    template is missing — a migration/environment problem, never a
    reachable state via any normal request."""


class WorkflowStageNotFoundError(Exception):
    """Raised by transition_project_workflow when target_stage_key doesn't
    name a real stage within the project's own bound template."""


class WorkflowTransitionNotAllowedError(Exception):
    """Raised by transition_project_workflow when the target stage isn't a
    legal move from the project's current stage — no seeded graph edge,
    and not a Resume (the one non-graph-edge move)."""


class WorkflowTerminalStateError(Exception):
    """Raised by transition_project_workflow when the project's current
    stage is terminal (Complete or Cancelled) — nothing may move a
    finished or cancelled project any further."""
