"""Sample notifications so the dashboard isn't empty on a fresh install.

Safe to delete once real notifications are being created by the modules
that produce them.

Sprint 012 (ADR-029) — seeded rows have no tenant (tenant_id=None), so
they're invisible to every real tenant's authenticated GET /notifications.
The "already seeded" guard below can no longer use
notification_service.list_all() (now requires a real tenant_id) — it
checks the table directly instead, same convention app/activity/seed.py
now follows.
"""

from app.database import crud
from app.database.database import SessionLocal
from app.notifications.models import NotificationCreate, NotificationType
from app.notifications.service import notification_service

_SEED_NOTIFICATIONS = [
    NotificationCreate(
        title="Quote approved",
        message="Sarah Whitfield approved her Calacatta Gold quote.",
        type=NotificationType.SUCCESS,
    ),
    NotificationCreate(
        title="Quotes expiring soon",
        message="3 quotes expire within the next 7 days.",
        type=NotificationType.WARNING,
    ),
    NotificationCreate(
        title="AI Estimator is live",
        message="Try the new AI-assisted quote estimator from the dashboard.",
        type=NotificationType.INFO,
    ),
    NotificationCreate(
        title="PDF generation failed",
        message="Quote PDF for James Okafor could not be generated. Retry from Quotes.",
        type=NotificationType.ERROR,
    ),
]


def seed_notifications() -> None:
    # Sprint 002: notification_service is now backed by Postgres, so this
    # guard is what prevents every app restart from inserting duplicate seed
    # rows — it only seeds a genuinely empty notifications table. Sprint 012:
    # checked directly against the table (unfiltered) since there's no
    # tenant yet at startup to scope notification_service.list_all() by.
    db = SessionLocal()
    try:
        if crud.count_notifications(db) > 0:
            return  # already seeded
    finally:
        db.close()
    for notification in _SEED_NOTIFICATIONS:
        notification_service.create(notification)
