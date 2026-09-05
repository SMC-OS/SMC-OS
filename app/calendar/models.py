import uuid
from datetime import date, datetime

from pydantic import BaseModel

# What a calendar item can be. Plain strings, same no-native-enum
# convention as everything else. Each maps to a real row this workspace
# already owns — there is no synthetic or predicted item in this feed.
CALENDAR_ITEM_TYPES = (
    "project_start",
    "project_target_completion",
    "site_visit",
    "task_due",
    "quote_expiry",
)


class CalendarItem(BaseModel):
    """One dated thing in a workspace's operational calendar.

    `at` is the moment it happens, `all_day` says whether the time part is
    meaningful. Project dates and quote expiries are DATE columns and are
    genuinely all-day; site visits and task due dates carry a real time.
    Rendering an all-day item at 00:00 (or worse, at 01:00 after a
    timezone conversion) is the classic calendar bug this flag exists to
    prevent.

    `source_type`/`source_id` let the UI link straight through to the
    record — a calendar you cannot click out of is a picture, not a tool.
    """

    id: str
    type: str
    title: str
    subtitle: str | None = None
    at: datetime | date
    all_day: bool
    source_type: str
    source_id: uuid.UUID
    status: str | None = None


class CalendarResponse(BaseModel):
    """The window actually served is echoed back, because the endpoint
    clamps an over-long request rather than refusing it — a client asking
    for five years gets a year and is told so, instead of an error it has
    to handle."""

    start: date
    end: date
    items: list[CalendarItem]
