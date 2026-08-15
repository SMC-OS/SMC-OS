import uuid

from app.notifications.models import Notification, NotificationCreate
from app.notifications.repository import NotificationRepository, PostgresNotificationRepository


class NotificationService:
    def __init__(self, repository: NotificationRepository | None = None) -> None:
        # Sprint 001 defaulted this to InMemoryNotificationRepository().
        # Sprint 002 swaps the default to PostgresNotificationRepository()
        # per ADR-001 — the constructor signature, and everything above it
        # (router, service methods), is unchanged.
        self.repository = repository or PostgresNotificationRepository()

    def list_all(self, tenant_id: uuid.UUID, limit: int = 50) -> list[Notification]:
        return self.repository.list(tenant_id=tenant_id, limit=limit)

    def unread_count(self, tenant_id: uuid.UUID) -> int:
        return len(
            [n for n in self.repository.list(tenant_id=tenant_id, limit=1000) if not n.read]
        )

    def create(
        self, notification: NotificationCreate, tenant_id: uuid.UUID | None = None
    ) -> Notification:
        return self.repository.add(Notification(**notification.model_dump()), tenant_id=tenant_id)

    def mark_read(self, notification_id: str, tenant_id: uuid.UUID) -> Notification | None:
        return self.repository.mark_read(notification_id, tenant_id=tenant_id)


# Singleton used by the router. Sprint 002: now backed by Postgres by
# default (see repository.py) — the router and every caller above this line
# are unchanged, exactly as ADR-001 intended.
notification_service = NotificationService()
