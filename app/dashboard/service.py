import uuid

from sqlalchemy.orm import Session

from app.dashboard.models import (
    CommandCentreResponse,
    FollowUpAttention,
    PipelineCounts,
    QuoteFunnel,
    QuotedValue,
    SiteVisitCounts,
)
from app.database import crud
from app.projects.models import ProjectStatus
from app.appointments.models import AppointmentStatus


def build_command_centre(db: Session, tenant_id: uuid.UUID) -> CommandCentreResponse:
    """Six aggregate SQL queries total (docs/SPRINTS/sprint-025.md §3) —
    every count/sum below is one grouped or scalar query, never a per-row
    Python loop, so this stays O(1) queries regardless of how many
    Projects/Quotes/Appointments the tenant has."""
    project_counts = crud.count_projects_by_status(db, tenant_id)
    quote_counts = crud.count_quotes_by_status(db, tenant_id)
    appointment_counts = crud.count_appointments_by_status(db, tenant_id)

    return CommandCentreResponse(
        customers=crud.count_customers(db, tenant_id),
        pipeline=PipelineCounts(
            **{status.value: project_counts.get(status.value, 0) for status in ProjectStatus}
        ),
        quotes=QuoteFunnel(
            draft=quote_counts.get("draft", 0),
            approved=quote_counts.get("approved", 0),
            handed_off=crud.count_handed_off_projects(db, tenant_id),
        ),
        value=QuotedValue(
            quoted_value=crud.sum_quotes_revenue(db, tenant_id),
            approved_quoted_value=crud.sum_approved_quotes_value(db, tenant_id),
        ),
        site_visits=SiteVisitCounts(
            **{
                status.value: appointment_counts.get(status.value, 0)
                for status in AppointmentStatus
            }
        ),
        follow_up=FollowUpAttention(
            unread_follow_ups=crud.count_unread_follow_up_notifications(db, tenant_id)
        ),
    )
