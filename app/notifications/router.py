from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.database.models import User
from app.notifications import categories as notification_categories
from app.notifications import preferences as notification_preferences
from app.notifications.models import (
    Notification,
    NotificationCreate,
    NotificationPreferenceOut,
    NotificationPreferencesUpdate,
)
from app.notifications.service import notification_service

# Sprint 012 (ADR-029) — this router had no auth at all before this sprint
# (docs/USER_ROLES.md §1's "still true" list). Now gated like every other
# business-data module, and every read/write is scoped to the caller's
# tenant. Sprint 024 additionally scopes reads/marks to the caller's own
# user id (docs/SPRINTS/sprint-024.md §6) — tenant-wide broadcasts (the
# only kind that existed before Sprint 024) are unaffected.
router = APIRouter(
    prefix="/notifications", tags=["notifications"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[Notification])
def list_notifications(limit: int = 50, current_user: User = Depends(get_current_user)):
    return notification_service.list_all(
        tenant_id=current_user.tenant_id, user_id=current_user.id, limit=limit
    )


# --- Preferences (Sprint 039, Workstream B) -----------------------------
#
# Declared before the `/{notification_id}/read` route below for the same
# reason app/projects/router.py's /meta/pipeline is declared before
# /{project_id}: FastAPI matches in declaration order.
#
# Not role-gated beyond the router's own get_current_user. These are a
# person's own settings about their own notifications — there is nothing
# here an Owner should be able to change on a colleague's behalf, and
# nothing a Staff member should be denied.


@router.get("/preferences", response_model=list[NotificationPreferenceOut])
def get_preferences(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Every category, with this user's effective setting for it.

    Always the complete list — stored rows and defaults alike — so the
    settings screen never has to know which rows happen to exist, and
    never has to carry its own copy of the category vocabulary.
    """
    resolved = notification_preferences.resolve(
        db, current_user.tenant_id, current_user.id
    )
    return [
        NotificationPreferenceOut(
            category=category.key,
            label=category.label,
            description=category.description,
            in_app=resolved[category.key]["in_app"],
            email=resolved[category.key]["email"],
        )
        for category in notification_categories.CATEGORIES
    ]


@router.put("/preferences", response_model=list[NotificationPreferenceOut])
def update_preferences(
    data: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store this user's choices.

    A partial update: only the categories named are written, so a client
    that knows about fewer categories than the server cannot reset the
    ones it has not heard of.
    """
    notification_preferences.replace(
        db,
        current_user.tenant_id,
        current_user.id,
        [update.model_dump() for update in data.preferences],
    )
    return get_preferences(current_user=current_user, db=db)


@router.get("/unread-count")
def unread_count(current_user: User = Depends(get_current_user)):
    return {
        "unread": notification_service.unread_count(
            tenant_id=current_user.tenant_id, user_id=current_user.id
        )
    }


@router.post("", response_model=Notification)
def create_notification(
    notification: NotificationCreate, current_user: User = Depends(get_current_user)
):
    return notification_service.create(notification, tenant_id=current_user.tenant_id)


@router.patch("/{notification_id}/read", response_model=Notification)
def mark_read(notification_id: str, current_user: User = Depends(get_current_user)):
    updated = notification_service.mark_read(
        notification_id, tenant_id=current_user.tenant_id, user_id=current_user.id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return updated
