"""Sample activity so the dashboard isn't empty on a fresh install.

Safe to delete once real events are being logged by the modules that
produce them (quotes, customers, projects, invoices, the AI router, auth).

Sprint 012 (ADR-029) — seeded rows have no tenant (tenant_id=None), so
they're invisible to every real tenant's authenticated GET /activity, same
as an anonymous /quote's logged event. The "already seeded" guard below
can no longer use activity_service.list_recent() (now requires a real
tenant_id) — it checks the table directly instead, same convention
app/notifications/seed.py now follows.
"""

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.database import crud
from app.database.database import SessionLocal

_SEED_EVENTS = [
    ActivityEventCreate(
        type=ActivityType.QUOTE_CREATED,
        title="New quote created",
        description="Sarah Whitfield — Calacatta Gold worktop, £3,240",
    ),
    ActivityEventCreate(
        type=ActivityType.CUSTOMER_ADDED,
        title="New customer added",
        description="James Okafor",
    ),
    ActivityEventCreate(
        type=ActivityType.PROJECT_CREATED,
        title="Project started",
        description="Riverside Kitchen Renovation",
    ),
    ActivityEventCreate(
        type=ActivityType.INVOICE_GENERATED,
        title="Invoice generated",
        description="INV-1042 for the Chen family",
    ),
    ActivityEventCreate(
        type=ActivityType.AI_REQUEST,
        title="AI Estimator request processed",
        description="Kitchen worktop estimate, 4.2m run",
    ),
    ActivityEventCreate(
        type=ActivityType.USER_LOGIN,
        title="User signed in",
        description="Simo",
    ),
]


def seed_activity() -> None:
    # Sprint 002: activity_service is now backed by Postgres, so this guard
    # is what prevents every app restart from inserting duplicate seed rows
    # — it only seeds a genuinely empty activity_log table. Sprint 012:
    # checked directly against the table (unfiltered) since there's no
    # tenant yet at startup to scope activity_service.list_recent() by.
    db = SessionLocal()
    try:
        if crud.count_activity_log(db) > 0:
            return  # already seeded
    finally:
        db.close()
    for event in _SEED_EVENTS:
        activity_service.log(event)
