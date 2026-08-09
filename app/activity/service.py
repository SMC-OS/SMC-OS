from app.activity.models import ActivityEvent, ActivityEventCreate, ActivityType
from app.activity.repository import ActivityRepository, InMemoryActivityRepository


class ActivityService:
    def __init__(self, repository: ActivityRepository | None = None) -> None:
        self.repository = repository or InMemoryActivityRepository()

    def list_recent(
        self, limit: int = 20, type: ActivityType | None = None
    ) -> list[ActivityEvent]:
        events = self.repository.list(limit=limit if type is None else 1000)
        if type is not None:
            events = [e for e in events if e.type == type]
        return events[:limit]

    def log(self, event: ActivityEventCreate) -> ActivityEvent:
        return self.repository.add(ActivityEvent(**event.model_dump()))


# Singleton used by the router. Once a real database repository exists,
# construct this with `ActivityService(PostgresActivityRepository(...))`
# instead — nothing else in the app needs to know.
activity_service = ActivityService()
