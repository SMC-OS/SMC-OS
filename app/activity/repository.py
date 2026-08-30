import uuid
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.activity.models import ActivityEvent, ActivityType
from app.database import crud
from app.database.database import SessionLocal


class ActivityRepository(ABC):
    """Storage interface for activity events.

    Swap `InMemoryActivityRepository` for a PostgreSQL-backed implementation
    once the database lands (Sprint 002) — `ActivityService`, the router, and
    the frontend do not need to change, because they only depend on this
    interface, not the storage mechanism behind it.

    Sprint 012 (ADR-029) — `list()` now requires `tenant_id`: every caller is
    an authenticated route reading its own tenant's feed. `add()` keeps
    `tenant_id` optional (`None` default) — seed rows and events logged from
    an anonymous /quote or /estimate call have no tenant.

    Sprint 021 — `add()` also takes an optional `db`: when a caller (e.g.
    ProjectService.convert_to_customer) passes its own request-scoped
    session, the event is written into that session without opening a new
    one or committing, so it can be folded into the caller's own
    transaction. `db=None` (the default) is the original, unchanged
    behavior every existing caller keeps getting.
    """

    @abstractmethod
    def list(self, tenant_id: uuid.UUID, limit: int = 20) -> list[ActivityEvent]: ...

    @abstractmethod
    def add(
        self,
        event: ActivityEvent,
        tenant_id: uuid.UUID | None = None,
        db: Session | None = None,
    ) -> ActivityEvent: ...


class InMemoryActivityRepository(ActivityRepository):
    """Temporary process-memory store. Resets on server restart.

    Not used by default (see service.py) and has no tenant_id field on the
    stored ActivityEvent — tenant_id is accepted for interface parity but
    has nothing to filter/tag against. `db` is likewise accepted for
    interface parity and ignored — there is no session to share.
    """

    def __init__(self) -> None:
        self._events: list[ActivityEvent] = []

    def list(self, tenant_id: uuid.UUID, limit: int = 20) -> list[ActivityEvent]:
        return sorted(self._events, key=lambda e: e.timestamp, reverse=True)[:limit]

    def add(
        self,
        event: ActivityEvent,
        tenant_id: uuid.UUID | None = None,
        db: Session | None = None,
    ) -> ActivityEvent:
        self._events.append(event)
        return event


class PostgresActivityRepository(ActivityRepository):
    """Sprint 002: real persistence, behind the same interface as above.

    Opens/closes its own session per call rather than taking one via FastAPI
    dependency injection — ActivityService is constructed as a module-level
    singleton (see service.py), not per-request, so there's no request-scoped
    session to receive. See app/database/database.py's `get_db` for the
    dependency-injected version future route work can use instead.

    Sprint 021 — unless a caller passes its own `db` (see `add()` below), in
    which case that per-call session-opening is skipped entirely in favor of
    writing into the caller's session, uncommitted.
    """

    def list(self, tenant_id: uuid.UUID, limit: int = 20) -> list[ActivityEvent]:
        with SessionLocal() as db:
            rows = crud.list_activity_log(db, tenant_id, limit=limit)
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

    def add(
        self,
        event: ActivityEvent,
        tenant_id: uuid.UUID | None = None,
        db: Session | None = None,
    ) -> ActivityEvent:
        if db is not None:
            crud.create_activity_log(
                db,
                id=uuid.UUID(event.id),
                tenant_id=tenant_id,
                type=event.type.value,
                title=event.title,
                description=event.description,
                timestamp=event.timestamp,
                commit=False,
            )
            return event

        with SessionLocal() as db:
            crud.create_activity_log(
                db,
                id=uuid.UUID(event.id),
                tenant_id=tenant_id,
                type=event.type.value,
                title=event.title,
                description=event.description,
                timestamp=event.timestamp,
            )
        return event
