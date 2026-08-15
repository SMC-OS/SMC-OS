import uuid

from app.activity.models import ActivityEvent, ActivityEventCreate, ActivityType
from app.activity.repository import ActivityRepository, PostgresActivityRepository


class ActivityService:
    def __init__(self, repository: ActivityRepository | None = None) -> None:
        # Sprint 001 defaulted this to InMemoryActivityRepository(). Sprint 002
        # swaps the default to PostgresActivityRepository() per ADR-001 — the
        # constructor signature, and everything above it (router, service
        # methods), is unchanged.
        self.repository = repository or PostgresActivityRepository()

    def list_recent(
        self, tenant_id: uuid.UUID, limit: int = 20, type: ActivityType | None = None
    ) -> list[ActivityEvent]:
        events = self.repository.list(tenant_id=tenant_id, limit=limit if type is None else 1000)
        if type is not None:
            events = [e for e in events if e.type == type]
        return events[:limit]

    def log(self, event: ActivityEventCreate, tenant_id: uuid.UUID | None = None) -> ActivityEvent:
        return self.repository.add(ActivityEvent(**event.model_dump()), tenant_id=tenant_id)


# Singleton used by the router. Sprint 002: now backed by Postgres by
# default (see repository.py) — the router and every caller above this line
# are unchanged, exactly as ADR-001 intended.
activity_service = ActivityService()
