"""GeoCore Premium OS Plan 01 (Sprint 040, Task 5) — the trade-adaptive
workflow engine's own endpoints, mounted alongside app/projects/router.py
under the same /projects/{project_id} path family since they're all views
of/actions on one Project.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access, require_role
from app.auth.models import UserRole
from app.database import crud
from app.database.database import get_db
from app.database.models import User
from app.projects.models import ProjectOut
from app.workflows.models import (
    ProjectWorkflowDetail,
    WorkflowHistoryEntry,
    WorkflowTransitionRequest,
)
from app.workflows.service import (
    WorkflowGateBlockedError,
    WorkflowStageNotFoundError,
    WorkflowTerminalStateError,
    WorkflowTransitionNotAllowedError,
    get_project_workflow_detail,
    get_project_workflow_history,
    transition_project_workflow,
)

router = APIRouter(
    prefix="/projects", tags=["workflows"], dependencies=[Depends(require_billing_access)]
)


@router.get("/{project_id}/workflow", response_model=ProjectWorkflowDetail)
def get_workflow(
    project_id: uuid.UUID,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    project = crud.get_project_by_id(db, project_id, current_user.tenant_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return get_project_workflow_detail(db, project, current_user.tenant_id)


@router.get("/{project_id}/workflow/history", response_model=list[WorkflowHistoryEntry])
def get_workflow_history(
    project_id: uuid.UUID,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    project = crud.get_project_by_id(db, project_id, current_user.tenant_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return get_project_workflow_history(db, project, current_user.tenant_id)


@router.post("/{project_id}/workflow/transition", response_model=ProjectOut)
def transition_workflow(
    project_id: uuid.UUID,
    data: WorkflowTransitionRequest,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    project = crud.get_project_by_id(db, project_id, current_user.tenant_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        updated = transition_project_workflow(
            db,
            project,
            current_user.tenant_id,
            data.target_stage_key,
            data.reason,
            current_user.id,
        )
    except WorkflowStageNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{data.target_stage_key}' is not a stage in this project's workflow",
        )
    except WorkflowTerminalStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This project's workflow is already in a terminal state",
        )
    except WorkflowTransitionNotAllowedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot move this project to '{data.target_stage_key}' from its current stage",
        )
    except WorkflowGateBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"'{exc.target_stage_key}' has unmet entry requirements",
                "blocked_requirements": [blocker.model_dump() for blocker in exc.blockers],
            },
        )

    return updated
