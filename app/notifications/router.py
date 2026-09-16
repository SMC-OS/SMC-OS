from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_billing_access
from app.database.models import User
from app.notifications.models import Notification, NotificationCreate
from app.notifications.service import notification_service

# Sprint 012 (ADR-029) — this router had no auth at all before this sprint
# (docs/USER_ROLES.md §1's "still true" list). Now gated like every other
# business-data module, and every read/write is scoped to the caller's
# tenant. Sprint 024 additionally scopes reads/marks to the caller's own
# user id (docs/SPRINTS/sprint-024.md §6) — tenant-wide broadcasts (the
# only kind that existed before Sprint 024) are unaffected.
router = APIRouter(
    prefix="/notifications", tags=["notifications"], dependencies=[Depends(require_billing_access)]
)


@router.get("", response_model=list[Notification])
def list_notifications(limit: int = 50, current_user: User = Depends(require_billing_access)):
    return notification_service.list_all(
        tenant_id=current_user.tenant_id, user_id=current_user.id, limit=limit
    )


@router.get("/unread-count")
def unread_count(current_user: User = Depends(require_billing_access)):
    return {
        "unread": notification_service.unread_count(
            tenant_id=current_user.tenant_id, user_id=current_user.id
        )
    }


@router.post("", response_model=Notification)
def create_notification(
    notification: NotificationCreate, current_user: User = Depends(require_billing_access)
):
    return notification_service.create(notification, tenant_id=current_user.tenant_id)


@router.patch("/{notification_id}/read", response_model=Notification)
def mark_read(notification_id: str, current_user: User = Depends(require_billing_access)):
    updated = notification_service.mark_read(
        notification_id, tenant_id=current_user.tenant_id, user_id=current_user.id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return updated
