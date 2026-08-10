"""Sample activity so the dashboard isn't empty on a fresh install.

Safe to delete once real events are being logged by the modules that
produce them (quotes, customers, projects, invoices, the AI router, auth).
"""

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service

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
    # — it only seeds a genuinely empty activity_log table.
    if activity_service.list_recent(limit=1):
        return  # already seeded
    for event in _SEED_EVENTS:
        activity_service.log(event)
