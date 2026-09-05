"""TaskService — internal work items (Sprint 036).

A task is the unit of "somebody needs to do this" that the automation
engine, the dashboard attention list, the project detail page and the
calendar all needed and none of them had. Kept deliberately small: a
title, an optional body, an optional due date, an assignee, a link to
whatever it is about, and three states.

What it is not: a project-management suite. There are no subtasks,
dependencies, checklists, estimates or boards, because Sprint 036's
contract is to establish the correct extensible foundation rather than to
overbuild one.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.database import crud
from app.database.models import Task
from app.tasks.models import TaskCreate


class TaskNotFoundError(Exception):
    """Unknown id, or one belonging to another tenant — 404, never 403."""


class AssignedUserNotFoundError(Exception):
    """assigned_user_id doesn't resolve to a user in the caller's own
    tenant. Same relationship-linkage check as ProjectService.assign
    (Sprint 023): an id being valid is not proof it is yours."""


class TaskService:
    def list_all(
        self, db: Session, tenant_id: uuid.UUID, status: str | None = None, limit: int = 50
    ) -> list[Task]:
        return crud.list_tasks(db, tenant_id, status=status, limit=limit)

    def create(
        self,
        db: Session,
        data: TaskCreate,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> Task:
        if data.assigned_user_id is not None:
            assignee = crud.get_user_by_id(db, data.assigned_user_id)
            if assignee is None or assignee.tenant_id != tenant_id:
                raise AssignedUserNotFoundError(data.assigned_user_id)

        return crud.create_task(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=data.title,
            body=data.body,
            due_at=data.due_at,
            assigned_user_id=data.assigned_user_id,
            created_by_user_id=actor_user_id,
            source_type=data.source_type,
            source_id=data.source_id,
            # No dedupe_key: a person creating the same task twice on
            # purpose is their business. Only automations dedupe.
            dedupe_key=None,
        )

    def set_status(
        self, db: Session, task_id: uuid.UUID, tenant_id: uuid.UUID, status: str
    ) -> Task:
        # completed_at is set only for "done". Cancelling a task is not
        # completing it, and recording a completion time for work that was
        # abandoned would make any future "how long do tasks take" reading
        # wrong.
        completed_at = datetime.now(timezone.utc) if status == "done" else None
        task = crud.update_task_status(db, task_id, tenant_id, status, completed_at)
        if task is None:
            raise TaskNotFoundError(task_id)

        if status == "done":
            activity_service.log(
                ActivityEventCreate(
                    type=ActivityType.TASK_COMPLETED,
                    title="Task completed",
                    description=task.title,
                ),
                tenant_id=tenant_id,
            )
        return task


task_service = TaskService()
