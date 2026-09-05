"""AutomationService — CRUD over a tenant's automation rules (Sprint 036).

Thin by design: the interesting logic is in engine.py (execution),
conditions.py (evaluation) and actions.py (effects). This layer exists to
own tenant scoping, template expansion and the one activity event a rule
change is worth.
"""

import uuid

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.automations import templates as template_catalogue
from app.automations.models import (
    AutomationCreate,
    AutomationFromTemplate,
    AutomationUpdate,
)
from app.database import crud
from app.database.models import Automation


class AutomationNotFoundError(Exception):
    """Unknown id, or one belonging to another tenant. The caller turns
    this into a 404, never a 403 (ADR-028)."""


class AutomationService:
    def list_all(self, db: Session, tenant_id: uuid.UUID) -> list[Automation]:
        return crud.list_automations(db, tenant_id)

    def get(self, db: Session, automation_id: uuid.UUID, tenant_id: uuid.UUID):
        return crud.get_automation_by_id(db, automation_id, tenant_id)

    def create(
        self,
        db: Session,
        data: AutomationCreate,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
        template_key: str | None = None,
    ) -> Automation:
        automation = crud.create_automation(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            trigger_type=data.trigger_type,
            # model_dump() rather than the model objects: the column is
            # JSONB and must receive plain JSON-shaped data, and dumping
            # here is what guarantees nothing but validated content is
            # stored.
            conditions=[c.model_dump() for c in data.conditions],
            actions=[a.model_dump() for a in data.actions],
            enabled=data.enabled,
            template_key=template_key,
            created_by_user_id=actor_user_id,
        )
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.AUTOMATION_CREATED,
                title="Automation created",
                description=automation.name,
            ),
            tenant_id=tenant_id,
        )
        return automation

    def create_from_template(
        self,
        db: Session,
        data: AutomationFromTemplate,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> Automation:
        template = template_catalogue.get(data.template_key)
        if template is None:  # pragma: no cover — the model already validated it
            raise AutomationNotFoundError(data.template_key)

        # Round-tripped through AutomationCreate rather than written
        # straight to the row: a template is data in this repository, and
        # it must satisfy exactly the same validation a user-authored rule
        # does. If a template is ever edited into something invalid, this
        # fails loudly at activation instead of writing an unrunnable rule.
        payload = AutomationCreate(
            name=template.name,
            description=template.description,
            trigger_type=template.trigger_type,
            conditions=list(template.conditions),
            actions=list(template.actions),
            enabled=data.enabled,
        )
        return self.create(
            db, payload, tenant_id, actor_user_id, template_key=template.key
        )

    def update(
        self,
        db: Session,
        automation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        data: AutomationUpdate,
    ) -> Automation:
        changes = data.model_dump(exclude_unset=True)
        if "conditions" in changes and changes["conditions"] is not None:
            changes["conditions"] = [dict(c) for c in changes["conditions"]]
        if "actions" in changes and changes["actions"] is not None:
            changes["actions"] = [dict(a) for a in changes["actions"]]

        updated = (
            crud.update_automation(db, automation_id, tenant_id, changes)
            if changes
            else crud.get_automation_by_id(db, automation_id, tenant_id)
        )
        if updated is None:
            raise AutomationNotFoundError(automation_id)
        return updated

    def delete(self, db: Session, automation_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        if not crud.delete_automation(db, automation_id, tenant_id):
            raise AutomationNotFoundError(automation_id)

    def list_runs(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        automation_id: uuid.UUID | None = None,
        limit: int = 50,
    ):
        # A run list scoped to one automation still validates that
        # automation belongs to the caller first: filtering runs by an id
        # the caller doesn't own would return an empty list rather than a
        # 404, which quietly confirms nothing but reads as "no history".
        if automation_id is not None and crud.get_automation_by_id(
            db, automation_id, tenant_id
        ) is None:
            raise AutomationNotFoundError(automation_id)
        return crud.list_automation_runs(
            db, tenant_id, automation_id=automation_id, limit=limit
        )


automation_service = AutomationService()
