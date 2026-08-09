from fastapi import APIRouter, HTTPException

from app.notifications.models import Notification, NotificationCreate
from app.notifications.service import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[Notification])
def list_notifications(limit: int = 50):
    return notification_service.list_all(limit=limit)


@router.get("/unread-count")
def unread_count():
    return {"unread": notification_service.unread_count()}


@router.post("", response_model=Notification)
def create_notification(notification: NotificationCreate):
    return notification_service.create(notification)


@router.patch("/{notification_id}/read", response_model=Notification)
def mark_read(notification_id: str):
    updated = notification_service.mark_read(notification_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return updated
