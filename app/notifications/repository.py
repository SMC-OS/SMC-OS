from abc import ABC, abstractmethod

from app.notifications.models import Notification


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
