"""Billing request/response schemas — Sprint 032, Workstream A."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.billing.plans import BILLING_PERIODS, SELF_SERVICE_PLANS


class CheckoutSessionRequest(BaseModel):
    plan: str
    billing_period: str

    @field_validator("plan")
    @classmethod
    def plan_must_be_self_service(cls, value: str) -> str:
        if value not in SELF_SERVICE_PLANS:
            raise ValueError(
                f"'{value}' has no self-service checkout — contact sales for Enterprise."
            )
        return value

    @field_validator("billing_period")
    @classmethod
    def billing_period_must_be_supported(cls, value: str) -> str:
        if value not in BILLING_PERIODS:
            raise ValueError(f"billing_period must be one of {sorted(BILLING_PERIODS)}")
        return value


class CheckoutSessionOut(BaseModel):
    checkout_url: str


class PortalSessionOut(BaseModel):
    portal_url: str


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    plan: str
    billing_period: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    # Sprint 039 Blocker 3 — both None for a subscription that was never
    # a trial (see Subscription.trial_start's own docstring).
    trial_start: datetime | None
    trial_end: datetime | None
    created_at: datetime
    updated_at: datetime
    # Phase B — set only for a no-card trial GeoCore runs itself:
    # "active", "ending_soon" (3 days or fewer left) or "expired".
    # None for paid, grandfathered or Stripe-managed subscriptions.
    trial_state: str | None = None
    trial_days_remaining: int | None = None


class StartTrialRequest(BaseModel):
    """Optional plan choice for POST /billing/trial. Lenient like signup:
    anything unknown falls back to the default trial plan."""

    plan: str | None = None
    billing_period: str | None = None


class PlanEntitlementsOut(BaseModel):
    seats: int | None
    ai_usage_per_month: int | None
    automations: int | None
    integrations: int | None
    advanced_analytics: bool


class PlanOut(BaseModel):
    plan: str
    name: str
    self_service: bool
    monthly_price_gbp: int | None
    annual_price_gbp: int | None
    annual_recommended: bool
    # Sprint 041 — None for Enterprise (contact-sales, no self-service
    # trial); TRIAL_LENGTH_DAYS for every self-service plan. The single
    # source both apps/web/app/pricing and the public marketing site read,
    # so a trial-disclosure component never hard-codes "14" of its own.
    trial_days: int | None
    entitlements: PlanEntitlementsOut
