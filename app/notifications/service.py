from app.notifications.models import Notification, NotificationCreate
from app.notifications.repository import (
    InMemoryNotificationRepository,
    NotificationRepository,
)


class NotificationService:
    def __init__(self, repository: NotificationRepository | None = None) -> None:
        self.repository = repository or InMemoryNotificationRepository()

    def list_all(self, limit: int = 50) -> list[Notification]:
        return self.repository.list(limit=limit)

    def unread_count(self) -> int:
        return len([n for n in self.repository.list(limit=1000) if not n.read])

    def create(self, notification: NotificationCreate) -> Notification:
        return self.repository.add(Notification(**notification.model_dump()))

    def mark_read(self, notification_id: str) -> Notification | None:
        return self.repository.mark_read(notification_id)


notification_service = NotificationService()
