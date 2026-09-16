from fastapi import APIRouter, Depends

from app.activity.models import ActivityEvent, ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.auth.dependencies import require_billing_access
from app.database.models import User

# Sprint 012 (ADR-029) — this router had no auth at all before this sprint
# (docs/USER_ROLES.md §1's "still true" list). Now gated like every other
# business-data module, and every read/write is scoped to the caller's
# tenant. Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix —
# gate is require_billing_access (require_verified_email plus billing/
# trial activation, Sprint 039's final auth + trial gate), not bare
# get_current_user.
router = APIRouter(
    prefix="/activity", tags=["activity"], dependencies=[Depends(require_billing_access)]
)


@router.get("", response_model=list[ActivityEvent])
def list_activity(
    limit: int = 20,
    type: ActivityType | None = None,
    current_user: User = Depends(require_billing_access),
):
    return activity_service.list_recent(tenant_id=current_user.tenant_id, limit=limit, type=type)


@router.post("", response_model=ActivityEvent)
def create_activity(event: ActivityEventCreate, current_user: User = Depends(require_billing_access)):
    return activity_service.log(event, tenant_id=current_user.tenant_id)
