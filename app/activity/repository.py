from abc import ABC, abstractmethod

from app.activity.models import ActivityEvent


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
