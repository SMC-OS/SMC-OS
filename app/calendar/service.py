"""CalendarService — one aggregated feed of a workspace's dated work
(Sprint 036, Workstream K).

Every item in this feed is a real row the workspace already owns: a
project's start date, a project's target completion date, a scheduled site
visit, a task's due date, a quote's expiry. Nothing here is predicted,
inferred or synthesised.

**There is no external calendar integration.** GeoCore does not sync with
Google Calendar or Microsoft 365, and this module does not pretend
otherwise — no ICS feed, no OAuth, no "connect your calendar" affordance.
Building the aggregation and the UI first is the correct order: an export
or sync added later has one well-defined thing to export.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.calendar.models import CalendarItem, CalendarResponse
from app.database import crud

# A calendar request is a window, and an unbounded one is an unbounded
# query. A year is far more than any month or agenda view needs, so
# clamping to it costs nothing real and removes the failure mode.
MAX_WINDOW_DAYS = 366
DEFAULT_WINDOW_DAYS = 42


def _window_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Convert an inclusive date window into the timestamp range the
    timestamp-valued sources (appointments, task due dates) need. The end
    is the last instant of `end`, not its midnight, so an appointment at
    16:00 on the final day is inside the window rather than just outside
    it."""
    return (
        datetime.combine(start, time.min, tzinfo=timezone.utc),
        datetime.combine(end, time.max, tzinfo=timezone.utc),
    )


class CalendarService:
    def resolve_window(
        self, start: date | None, end: date | None, today: date
    ) -> tuple[date, date]:
        resolved_start = start or today - timedelta(days=7)
        resolved_end = end or resolved_start + timedelta(days=DEFAULT_WINDOW_DAYS)
        if resolved_end < resolved_start:
            resolved_end = resolved_start
        if (resolved_end - resolved_start).days > MAX_WINDOW_DAYS:
            resolved_end = resolved_start + timedelta(days=MAX_WINDOW_DAYS)
        return resolved_start, resolved_end

    def build(
        self, db: Session, tenant_id: uuid.UUID, start: date, end: date
    ) -> CalendarResponse:
        items: list[CalendarItem] = []
        ts_start, ts_end = _window_bounds(start, end)

        # Customer names are resolved once per customer rather than per
        # item: a month with thirty projects for the same builder would
        # otherwise issue thirty identical lookups.
        customer_names: dict[uuid.UUID, str] = {}

        def customer_name(customer_id) -> str | None:
            if customer_id is None:
                return None
            if customer_id not in customer_names:
                customer = crud.get_customer_by_id(db, customer_id, tenant_id)
                customer_names[customer_id] = customer.name if customer else ""
            return customer_names[customer_id] or None

        for project in crud.list_projects_in_date_window(db, tenant_id, start, end):
            if project.start_date and start <= project.start_date <= end:
                items.append(
                    CalendarItem(
                        # The id embeds the type as well as the row id: one
                        # project legitimately produces two items (a start
                        # and a completion), and a bare row id would make
                        # them collide as React keys.
                        id=f"project_start:{project.id}",
                        type="project_start",
                        title=f"Starts: {project.name}",
                        subtitle=customer_name(project.customer_id),
                        at=project.start_date,
                        all_day=True,
                        source_type="project",
                        source_id=project.id,
                        status=project.status,
                    )
                )
            if (
                project.target_completion_date
                and start <= project.target_completion_date <= end
            ):
                items.append(
                    CalendarItem(
                        id=f"project_target:{project.id}",
                        type="project_target_completion",
                        title=f"Due: {project.name}",
                        subtitle=customer_name(project.customer_id),
                        at=project.target_completion_date,
                        all_day=True,
                        source_type="project",
                        source_id=project.id,
                        status=project.status,
                    )
                )

        for appointment in crud.list_appointments_in_window(db, tenant_id, ts_start, ts_end):
            project = crud.get_project_by_id(db, appointment.project_id, tenant_id)
            items.append(
                CalendarItem(
                    id=f"site_visit:{appointment.id}",
                    type="site_visit",
                    title=f"Site visit: {project.name}" if project else "Site visit",
                    subtitle=customer_name(project.customer_id) if project else None,
                    at=appointment.scheduled_at,
                    all_day=False,
                    source_type="project",
                    source_id=appointment.project_id,
                    status=appointment.status,
                )
            )

        for task in crud.list_tasks_in_window(db, tenant_id, ts_start, ts_end):
            items.append(
                CalendarItem(
                    id=f"task:{task.id}",
                    type="task_due",
                    title=task.title,
                    subtitle="Task",
                    at=task.due_at,
                    all_day=False,
                    source_type="task",
                    source_id=task.id,
                    status=task.status,
                )
            )

        for quote in crud.list_quotes_expiring_in_window(db, tenant_id, start, end):
            # An approved quote's validity date is no longer meaningful —
            # it has been accepted. Showing it would fill the calendar with
            # deadlines that have already been met.
            if quote.status == "approved":
                continue
            items.append(
                CalendarItem(
                    id=f"quote_expiry:{quote.id}",
                    type="quote_expiry",
                    title=f"Quote expires: {quote.title or 'Quote'}",
                    subtitle=customer_name(quote.customer_id),
                    at=quote.valid_until,
                    all_day=True,
                    source_type="quote",
                    source_id=quote.id,
                    status=quote.status,
                )
            )

        items.sort(key=self._sort_key)
        return CalendarResponse(start=start, end=end, items=items)

    @staticmethod
    def _sort_key(item: CalendarItem):
        """Sort by the day something happens, then by whether it has a
        time. An all-day item sorts to the top of its day rather than
        being placed at an arbitrary hour, which is the same reason
        `all_day` exists on the model at all."""
        if isinstance(item.at, datetime):
            return (item.at.date(), 1, item.at.hour, item.at.minute)
        return (item.at, 0, 0, 0)


calendar_service = CalendarService()
