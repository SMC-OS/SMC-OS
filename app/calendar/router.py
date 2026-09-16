"""Calendar API (Sprint 036, Workstream K).

One read-only endpoint aggregating a workspace's dated work. Any
authenticated member may read it: knowing when jobs start is exactly what
a calendar is for, and nothing in the feed is more sensitive than the
records it points at, all of which the same user can already open.

There is deliberately no /calendar/subscribe, no ICS feed and no
"connect Google Calendar" endpoint — GeoCore has no external calendar
integration, and an endpoint implying one would be a claim the product
cannot honour.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access
from app.calendar.models import CalendarResponse
from app.calendar.service import calendar_service
from app.database.database import get_db
from app.database.models import User

router = APIRouter(
    prefix="/calendar", tags=["calendar"], dependencies=[Depends(require_billing_access)]
)


@router.get("", response_model=CalendarResponse)
def get_calendar(
    start: date | None = None,
    end: date | None = None,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    """Dated items in a window. An over-long or reversed window is clamped
    rather than rejected, and the window actually served is echoed back in
    the response so the client renders what it got rather than what it
    asked for."""
    resolved_start, resolved_end = calendar_service.resolve_window(
        start, end, datetime.now(timezone.utc).date()
    )
    return calendar_service.build(
        db, current_user.tenant_id, resolved_start, resolved_end
    )
