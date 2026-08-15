from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.database.models import User
from app.notifications.models import Notification, NotificationCreate
from app.notifications.service import notification_service

# Sprint 012 (ADR-029) — this router had no auth at all before this sprint
# (docs/USER_ROLES.md §1's "still true" list). Now gated like every other
# business-data module, and every read/write is scoped to the caller's
# tenant.
router = APIRouter(
    prefix="/notifications", tags=["notifications"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[Notification])
def list_notifications(limit: int = 50, current_user: User = Depends(get_current_user)):
    return notification_service.list_all(tenant_id=current_user.tenant_id, limit=limit)


@router.get("/unread-count")
def unread_count(current_user: User = Depends(get_current_user)):
    return {"unread": notification_service.unread_count(tenant_id=current_user.tenant_id)}


@router.post("", response_model=Notification)
def create_notification(
    notification: NotificationCreate, current_user: User = Depends(get_current_user)
):
    return notification_service.create(notification, tenant_id=current_user.tenant_id)


@router.patch("/{notification_id}/read", response_model=Notification)
def mark_read(notification_id: str, current_user: User = Depends(get_current_user)):
    updated = notification_service.mark_read(notification_id, tenant_id=current_user.tenant_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return updated
