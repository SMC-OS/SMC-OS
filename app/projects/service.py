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
from app.projects.models import ProjectCreate, ProjectStatus
from app.database import crud
from app.database.models import Project


class ProjectService:
    def list_all(self, db: Session, limit: int = 20) -> list[Project]:
        return crud.list_projects(db, limit=limit)

    def get(self, db: Session, project_id: uuid.UUID) -> Project | None:
        return crud.get_project_by_id(db, project_id)

    def create(self, db: Session, data: ProjectCreate) -> Project:
        project = crud.create_project(
            db,
            id=uuid.uuid4(),
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
            )
        )
        return project

    def update_status(
        self, db: Session, project_id: uuid.UUID, status: ProjectStatus
    ) -> Project | None:
        return crud.update_project_status(db, project_id, status.value)


project_service = ProjectService()
