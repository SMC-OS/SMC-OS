from app.notifications.models import Notification, NotificationCreate
from app.notifications.repository import NotificationRepository, PostgresNotificationRepository


class NotificationService:
    def __init__(self, repository: NotificationRepository | None = None) -> None:
        # Sprint 001 defaulted this to InMemoryNotificationRepository().
        # Sprint 002 swaps the default to PostgresNotificationRepository()
        # per ADR-001 — the constructor signature, and everything above it
        # (router, service methods), is unchanged.
        self.repository = repository or PostgresNotificationRepository()

    def list_all(self, limit: int = 50) -> list[Notification]:
        return self.repository.list(limit=limit)

    def unread_count(self) -> int:
        return len([n for n in self.repository.list(limit=1000) if not n.read])

    def create(self, notification: NotificationCreate) -> Notification:
        return self.repository.add(Notification(**notification.model_dump()))

    def mark_read(self, notification_id: str) -> Notification | None:
        return self.repository.mark_read(notification_id)


# Singleton used by the router. Sprint 002: now backed by Postgres by
# default (see repository.py) — the router and every caller above this line
# are unchanged, exactly as ADR-001 intended.
notification_service = NotificationService()
