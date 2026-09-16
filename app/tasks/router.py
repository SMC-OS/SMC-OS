"""Tasks API (Sprint 036).

No require_role: creating and completing a task is routine day-to-day
work, the same posture as customers, projects, documents and portal links
— not a tenant-control decision like team management or billing.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access
from app.database.database import get_db
from app.database.models import User
from app.tasks.models import TaskCreate, TaskOut, TaskStatusUpdate
from app.tasks.service import (
    AssignedUserNotFoundError,
    TaskNotFoundError,
    task_service,
)

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_billing_access)])


@router.get("", response_model=list[TaskOut])
def list_tasks(
    # Exposed to clients as ?status=, but named status_filter in Python:
    # a parameter called `status` would shadow the fastapi `status` module
    # this file uses for its response codes. Query(alias=...) keeps the
    # public name clean without the shadowing.
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    return task_service.list_all(
        db, current_user.tenant_id, status=status_filter, limit=min(limit, 200)
    )


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    try:
        return task_service.create(
            db, data, current_user.tenant_id, actor_user_id=current_user.id
        )
    except AssignedUserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.patch("/{task_id}/status", response_model=TaskOut)
def update_task_status(
    task_id: uuid.UUID,
    data: TaskStatusUpdate,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    try:
        return task_service.set_status(db, task_id, current_user.tenant_id, data.status)
    except TaskNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
