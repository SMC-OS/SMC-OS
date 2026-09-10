import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.auth.models import UserRole
from app.customers.models import CustomerCreate, CustomerOut
from app.projects.models import (
    PipelineStageOut,
    ProjectAssignmentUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectPipelineOut,
    ProjectStatusUpdate,
    ProjectUpdate,
)
from app.projects.service import (
    AssignedUserNotFoundError,
    CustomerNotFoundError,
    InvalidProjectTransitionError,
    ProjectNotInEnquiryStateError,
    project_service,
)
from app.database.database import get_db
from app.database.models import User

router = APIRouter(
    prefix="/projects", tags=["projects"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    limit: int = 20, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return project_service.list_all(db, tenant_id=current_user.tenant_id, limit=limit)


@router.get("/meta/pipeline", response_model=ProjectPipelineOut)
def get_pipeline(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """The caller's own project pipeline, with the moves each stage allows.

    Declared before `/{project_id}` because FastAPI matches routes in
    declaration order and "meta" would otherwise be parsed as a project
    UUID (the same ordering app/quotes/router.py's /meta routes rely on).

    Served from the backend rather than hardcoded per client for the same
    reason /automations/meta is: a UI must never be able to offer a stage
    or a transition this tenant's pipeline does not have.
    """
    pipeline = project_service.pipeline(db, current_user.tenant_id)
    return ProjectPipelineOut(
        stages=[
            PipelineStageOut(
                key=stage.key,
                label=stage.label,
                role=stage.role,
                position=stage.position,
                is_terminal=stage.is_terminal,
                is_side_state=stage.is_side_state,
                allowed_transitions=list(pipeline.allowed_transitions(stage.key)),
            )
            for stage in pipeline.stages
        ]
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = project_service.get(db, project_id, tenant_id=current_user.tenant_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return project_service.create(db, data, tenant_id=current_user.tenant_id)
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sprint 036 (Workstream F) — edit a project's own details. No
    require_role, matching create_project's posture: recording a site
    address or a start date is routine work, not a tenant-control
    decision. Status still has its own separately-gated endpoint with its
    own transition rules, which this cannot reach."""
    try:
        project = project_service.update(
            db, project_id, tenant_id=current_user.tenant_id, data=data
        )
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/{project_id}/status", response_model=ProjectOut)
def update_project_status(
    project_id: uuid.UUID,
    data: ProjectStatusUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        project = project_service.update_status(
            db, project_id, current_user.tenant_id, data.status
        )
    except InvalidProjectTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid status transition",
        )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/{project_id}/assign", response_model=ProjectOut)
def assign_project(
    project_id: uuid.UUID,
    data: ProjectAssignmentUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    try:
        project = project_service.assign(
            db, project_id, current_user.tenant_id, data.assigned_user_id
        )
    except AssignedUserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("/{project_id}/convert-to-customer", response_model=CustomerOut)
def convert_project_to_customer(
    project_id: uuid.UUID,
    data: CustomerCreate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        customer = project_service.convert_to_customer(
            db, project_id, current_user.tenant_id, data
        )
    except ProjectNotInEnquiryStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only enquiry projects can be converted to customers",
        )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return customer
