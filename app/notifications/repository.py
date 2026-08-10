import uuid
from abc import ABC, abstractmethod

from app.database import crud
from app.database.database import SessionLocal
from app.notifications.models import Notification, NotificationType


class NotificationRepository(ABC):
    """Storage interface for notifications.

    Same pattern as `app.activity.repository`: swap the in-memory
    implementation for a PostgreSQL-backed one later without touching
    the service, router, or frontend.
    """

    @abstractmethod
    def list(self, limit: int = 50) -> list[Notification]: ...

    @abstractmethod
    def add(self, notification: Notification) -> Notification: ...

    @abstractmethod
    def mark_read(self, notification_id: str) -> Notification | None: ...


class InMemoryNotificationRepository(NotificationRepository):
    def __init__(self) -> None:
        self._notifications: list[Notification] = []

    def list(self, limit: int = 50) -> list[Notification]:
        return sorted(
            self._notifications, key=lambda n: n.timestamp, reverse=True
        )[:limit]

    def add(self, notification: Notification) -> Notification:
        self._notifications.append(notification)
        return notification

    def mark_read(self, notification_id: str) -> Notification | None:
        for notification in self._notifications:
            if notification.id == notification_id:
                notification.read = True
                return notification
        return None


class PostgresNotificationRepository(NotificationRepository):
    """Sprint 002: real persistence, behind the same interface as above.

    Opens/closes its own session per call — NotificationService is a
    module-level singleton (see service.py), not constructed per-request,
    so there's no request-scoped session to receive here.
    """

    def list(self, limit: int = 50) -> list[Notification]:
        with SessionLocal() as db:
            rows = crud.list_notifications(db, limit=limit)
            return [
                Notification(
                    id=str(row.id),
                    title=row.title,
                    message=row.message,
                    type=NotificationType(row.type),
                    timestamp=row.timestamp,
                    read=row.read,
                )
                for row in rows
            ]

    def add(self, notification: Notification) -> Notification:
        with SessionLocal() as db:
            crud.create_notification(
                db,
                id=uuid.UUID(notification.id),
                tenant_id=None,
                title=notification.title,
                message=notification.message,
                type=notification.type.value,
                timestamp=notification.timestamp,
                read=notification.read,
            )
        return notification

    def mark_read(self, notification_id: str) -> Notification | None:
        try:
            parsed_id = uuid.UUID(notification_id)
        except ValueError:
            # Not a valid UUID at all — same "not found" result the router
            # already turns into a 404, per docs/API_SPEC.md. Preserves the
            # in-memory repository's behaviour for a bad/unknown id: it never
            # raised, it just returned None.
            return None
        with SessionLocal() as db:
            row = crud.mark_notification_read(db, parsed_id)
            if row is None:
                return None
            return Notification(
                id=str(row.id),
                title=row.title,
                message=row.message,
                type=NotificationType(row.type),
                timestamp=row.timestamp,
                read=row.read,
            )
