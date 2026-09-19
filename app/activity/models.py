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
    TENANT_IDENTITY_UPDATED = "tenant_identity_updated"
    PORTAL_LINK_CREATED = "portal_link_created"
    TEAM_MEMBER_DEACTIVATED = "team_member_deactivated"
    CUSTOMER_MESSAGE_RECEIVED = "customer_message_received"
    QUOTE_APPROVED = "quote_approved"
    QUOTE_HANDED_OFF = "quote_handed_off"
    ENQUIRY_CONVERTED = "enquiry_converted"
    SITE_VISIT_SCHEDULED = "site_visit_scheduled"
    SITE_VISIT_COMPLETED = "site_visit_completed"
    SITE_VISIT_CANCELLED = "site_visit_cancelled"
    PROJECT_ASSIGNED = "project_assigned"
    PROJECT_STATUS_CHANGED = "project_status_changed"
    # Sprint 036
    AUTOMATION_CREATED = "automation_created"
    TASK_COMPLETED = "task_completed"
    # Sprint 039 Production Readiness Defect Gate, Blocker 1
    EMAIL_VERIFICATION_REQUESTED = "email_verification_requested"
    EMAIL_VERIFIED = "email_verified"
    # Sprint 039 Production Readiness Defect Gate, Blocker 2
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_CHANGED = "password_changed"
    # GeoCore Premium OS Plan 04 (Sprint 043) — job financials + variations.
    # Internal only: app/activity/router.py is gated by require_billing_access
    # and nothing in app/portal/ ever reads ActivityLog, so recording real
    # cost figures/descriptions here never reaches a customer.
    PROJECT_COST_ADDED = "project_cost_added"
    PROJECT_COST_EDITED = "project_cost_edited"
    PROJECT_COST_DELETED = "project_cost_deleted"
    VARIATION_CREATED = "variation_created"
    VARIATION_SENT = "variation_sent"
    VARIATION_APPROVED = "variation_approved"
    VARIATION_REJECTED = "variation_rejected"
    VARIATION_VOIDED = "variation_voided"
    # GeoCore Premium OS Plan 05 (Sprint 044) — procurement + materials
    # operations. Same internal-only guarantee as the financials block
    # above: supplier/cost detail here is never customer-visible.
    MATERIAL_REQUIREMENT_CREATED = "material_requirement_created"
    MATERIAL_REQUIREMENT_EDITED = "material_requirement_edited"
    MATERIAL_REQUIREMENT_CANCELLED = "material_requirement_cancelled"
    PURCHASE_ORDER_CREATED = "purchase_order_created"
    PURCHASE_ORDER_APPROVED = "purchase_order_approved"
    PURCHASE_ORDER_ORDERED = "purchase_order_ordered"
    PURCHASE_ORDER_CANCELLED = "purchase_order_cancelled"
    PURCHASE_ORDER_RECEIPT_RECORDED = "purchase_order_receipt_recorded"
    MATERIAL_ALLOCATED = "material_allocated"


class ActivityEventCreate(BaseModel):
    type: ActivityType
    title: str
    description: str | None = None


class ActivityEvent(ActivityEventCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
