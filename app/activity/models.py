import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ActivityType(str, Enum):
    """Kinds of events the dashboard's Recent Activity panel can show.

    Extend this enum as new modules come online (e.g. CONTRACT_SIGNED,
    PAYMENT_RECEIVED) — nothing else needs to change to support a new type.
    """

    QUOTE_CREATED = "quote_created"
    CUSTOMER_ADDED = "customer_added"
    PROJECT_CREATED = "project_created"
    INVOICE_GENERATED = "invoice_generated"
    AI_REQUEST = "ai_request"
    USER_LOGIN = "user_login"
    TENANT_CREATED = "tenant_created"
    PORTAL_LINK_CREATED = "portal_link_created"
    TEAM_MEMBER_DEACTIVATED = "team_member_deactivated"
    CUSTOMER_MESSAGE_RECEIVED = "customer_message_received"
    QUOTE_APPROVED = "quote_approved"
    QUOTE_HANDED_OFF = "quote_handed_off"
    ENQUIRY_CONVERTED = "enquiry_converted"
    SITE_VISIT_SCHEDULED = "site_visit_scheduled"
    SITE_VISIT_COMPLETED = "site_visit_completed"
    SITE_VISIT_CANCELLED = "site_visit_cancelled"


class ActivityEventCreate(BaseModel):
    type: ActivityType
    title: str
    description: str | None = None


class ActivityEvent(ActivityEventCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
