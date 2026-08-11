import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.projects.models import ProjectCreate, ProjectOut, ProjectStatusUpdate
from app.projects.service import project_service
from app.database.database import get_db

router = APIRouter(
    prefix="/projects", tags=["projects"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[ProjectOut])
def list_projects(limit: int = 20, db: Session = Depends(get_db)):
    return project_service.list_all(db, limit=limit)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    project = project_service.get(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    return project_service.create(db, data)


@router.patch("/{project_id}/status", response_model=ProjectOut)
def update_project_status(
    project_id: uuid.UUID, data: ProjectStatusUpdate, db: Session = Depends(get_db)
):
    project = project_service.update_status(db, project_id, data.status)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
