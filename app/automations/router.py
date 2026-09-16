"""Automations API (Sprint 036, Workstream G).

Role posture: reading automations and their run history is open to any
authenticated member of the workspace (Owner or Staff) — knowing what the
system will do to your work is not a privilege. Creating, editing,
enabling and deleting a rule is **Owner-only**: an automation is
workspace-wide configuration that produces work for other people, in the
same class as team management, billing and company identity, not routine
day-to-day work like adding a customer.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role, require_verified_email
from app.auth.models import UserRole
from app.automations import templates as template_catalogue
from app.automations import triggers as trigger_catalogue
from app.automations.actions import ACTION_TYPES, CUSTOMER_FACING_ACTION_TYPES
from app.automations.conditions import OPS
from app.automations.models import (
    AutomationCreate,
    AutomationFromTemplate,
    AutomationOut,
    AutomationRunOut,
    AutomationUpdate,
)
from app.automations.service import AutomationNotFoundError, automation_service
from app.core.config import settings
from app.database.database import get_db
from app.database.models import User

router = APIRouter(
    prefix="/automations", tags=["automations"], dependencies=[Depends(require_verified_email)]
)


# --- Vocabulary. Static, no tenant data, so no role gate beyond the
# router-level require_verified_email. Served from the backend rather than
# duplicated in the frontend so the builder UI cannot offer a trigger or
# action the engine does not implement. ---


@router.get("/meta")
def automation_meta():
    return {
        "triggers": [
            {
                "key": trigger.key,
                "label": trigger.label,
                "description": trigger.description,
                "kind": trigger.kind,
                "subject_type": trigger.subject_type,
            }
            for trigger in trigger_catalogue.TRIGGERS
        ],
        "actions": sorted(ACTION_TYPES),
        "customer_facing_actions": sorted(CUSTOMER_FACING_ACTION_TYPES),
        "operators": sorted(OPS),
        # Stated in the API, not only in the UI, so any client is told the
        # same truth. Sprint 038 (Phase 2): flips honestly to whether a
        # real email provider is actually configured — never hardcoded
        # true just because the code path now exists, since an
        # unconfigured environment (no RESEND_API_KEY) must keep telling
        # the truth about what it can currently do.
        "delivery": {
            "external_delivery_available": bool(settings.resend_api_key),
            "note": (
                "GeoCore can email your customer directly for actions marked "
                "customer-facing. Every other automation still acts inside "
                "your workspace only — nothing else is sent without a "
                "person reviewing it first."
            )
            if settings.resend_api_key
            # Exact original Sprint 036 wording, unchanged — the frontend
            # only ever renders this note in the unconfigured branch
            # (apps/web/app/automations/page.tsx), and
            # apps/web/e2e/automations.spec.ts asserts this precise phrase
            # as "the honesty constraint, asserted in the product itself".
            # Sprint 038 does not get to quietly change a sentence that
            # test exists specifically to hold in place.
            else (
                "Automations act inside your workspace only. GeoCore does not "
                "send email, SMS or messages to customers; a drafted message "
                "is prepared for a person to review and send."
            ),
        },
    }


@router.get("/templates")
def list_templates():
    """Seeded templates. Definitions only — nothing is written to a
    workspace until someone activates one via POST /automations/templates."""
    return [
        {
            "key": template.key,
            "name": template.name,
            "description": template.description,
            "trigger_type": template.trigger_type,
            "conditions": list(template.conditions),
            "actions": list(template.actions),
        }
        for template in template_catalogue.TEMPLATES
    ]


@router.get("/runs", response_model=list[AutomationRunOut])
def list_runs(
    automation_id: uuid.UUID | None = None,
    limit: int = 50,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    """Execution history — successes, skips (with the reason) and failures
    (with the message). This is the only place an automation failure is
    visible, which is why it is a first-class endpoint rather than a log."""
    try:
        return automation_service.list_runs(
            db, current_user.tenant_id, automation_id=automation_id, limit=min(limit, 200)
        )
    except AutomationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")


@router.get("", response_model=list[AutomationOut])
def list_automations(
    current_user: User = Depends(require_verified_email), db: Session = Depends(get_db)
):
    return automation_service.list_all(db, current_user.tenant_id)


@router.get("/{automation_id}", response_model=AutomationOut)
def get_automation(
    automation_id: uuid.UUID,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    automation = automation_service.get(db, automation_id, current_user.tenant_id)
    if automation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")
    return automation


@router.post("", response_model=AutomationOut, status_code=status.HTTP_201_CREATED)
def create_automation(
    data: AutomationCreate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    return automation_service.create(
        db, data, current_user.tenant_id, actor_user_id=current_user.id
    )


@router.post(
    "/templates", response_model=AutomationOut, status_code=status.HTTP_201_CREATED
)
def activate_template(
    data: AutomationFromTemplate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    """Activate a seeded template as a real, editable rule in this
    workspace. The created automation is an ordinary automation from that
    moment on — `template_key` records where it came from, and editing it
    never re-syncs it to the template."""
    return automation_service.create_from_template(
        db, data, current_user.tenant_id, actor_user_id=current_user.id
    )


@router.patch("/{automation_id}", response_model=AutomationOut)
def update_automation(
    automation_id: uuid.UUID,
    data: AutomationUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    try:
        return automation_service.update(db, automation_id, current_user.tenant_id, data)
    except AutomationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(
    automation_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    try:
        automation_service.delete(db, automation_id, current_user.tenant_id)
    except AutomationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
