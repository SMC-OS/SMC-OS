import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.projects.models import ProjectCreate, ProjectOut, ProjectStatusUpdate
from app.projects.service import CustomerNotFoundError, project_service
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


@router.patch("/{project_id}/status", response_model=ProjectOut)
def update_project_status(
    project_id: uuid.UUID,
    data: ProjectStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = project_service.update_status(
        db, project_id, current_user.tenant_id, data.status
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
