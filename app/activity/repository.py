import uuid
from abc import ABC, abstractmethod

from app.activity.models import ActivityEvent, ActivityType
from app.database import crud
from app.database.database import SessionLocal


class ActivityRepository(ABC):
    """Storage interface for activity events.

    Swap `InMemoryActivityRepository` for a PostgreSQL-backed implementation
    once the database lands (Sprint 002) — `ActivityService`, the router, and
    the frontend do not need to change, because they only depend on this
    interface, not the storage mechanism behind it.
    """

    @abstractmethod
    def list(self, limit: int = 20) -> list[ActivityEvent]: ...

    @abstractmethod
    def add(self, event: ActivityEvent) -> ActivityEvent: ...


class InMemoryActivityRepository(ActivityRepository):
    """Temporary process-memory store. Resets on server restart."""

    def __init__(self) -> None:
        self._events: list[ActivityEvent] = []

    def list(self, limit: int = 20) -> list[ActivityEvent]:
        return sorted(self._events, key=lambda e: e.timestamp, reverse=True)[:limit]

    def add(self, event: ActivityEvent) -> ActivityEvent:
        self._events.append(event)
        return event


class PostgresActivityRepository(ActivityRepository):
    """Sprint 002: real persistence, behind the same interface as above.

    Opens/closes its own session per call rather than taking one via FastAPI
    dependency injection — ActivityService is constructed as a module-level
    singleton (see service.py), not per-request, so there's no request-scoped
    session to receive. See app/database/database.py's `get_db` for the
    dependency-injected version future route work can use instead.
    """

    def list(self, limit: int = 20) -> list[ActivityEvent]:
        with SessionLocal() as db:
            rows = crud.list_activity_log(db, limit=limit)
            return [
                ActivityEvent(
                    id=str(row.id),
                    type=ActivityType(row.type),
                    title=row.title,
                    description=row.description,
                    timestamp=row.timestamp,
                )
                for row in rows
            ]

    def add(self, event: ActivityEvent) -> ActivityEvent:
        with SessionLocal() as db:
            crud.create_activity_log(
                db,
                id=uuid.UUID(event.id),
                tenant_id=None,
                type=event.type.value,
                title=event.title,
                description=event.description,
                timestamp=event.timestamp,
            )
        return event
