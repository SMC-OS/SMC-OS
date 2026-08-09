"""Sample notifications so the dashboard isn't empty on a fresh install.

Safe to delete once real notifications are being created by the modules
that produce them.
"""

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
    if notification_service.list_all(limit=1):
        return
    for notification in _SEED_NOTIFICATIONS:
        notification_service.create(notification)
