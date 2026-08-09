from fastapi import APIRouter

from app.activity.models import ActivityEvent, ActivityEventCreate, ActivityType
from app.activity.service import activity_service

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=list[ActivityEvent])
def list_activity(limit: int = 20, type: ActivityType | None = None):
    return activity_service.list_recent(limit=limit, type=type)


@router.post("", response_model=ActivityEvent)
def create_activity(event: ActivityEventCreate):
    return activity_service.log(event)
