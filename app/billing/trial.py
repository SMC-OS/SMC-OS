"""14-day free trial — no card required (Phase B).

History: Sprint 039 built this as a pure app-side trial; the "GEOCORE V1
final auth + trial gate" then replaced it with a card-required Stripe
Checkout trial. The owner has since approved going back to a no-card
trial, so this module is again the one place a trial starts.

A trial is a `Subscription` row with `status="trialing"`, a trial window,
and NO Stripe customer or subscription id — Stripe is never contacted to
start one, so a tenant who never enters payment details can never be
charged. Payment details are collected only when the tenant subscribes
(BillingService.create_checkout_session), which upgrades this same row in
place via the Checkout webhooks.

Eligibility is deliberately strict: a tenant gets a trial only if it has
never had a Subscription row of any kind. Subscription.tenant_id is
unique and rows are never deleted, so an existing paying, cancelled,
grandfathered or previously-trialled tenant can never receive a new
trial through this module.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.billing.plans import BILLING_PERIODS, SELF_SERVICE_PLANS, TRIAL_LENGTH_DAYS, TRIAL_PLAN
from app.database import crud
from app.database.models import Subscription

# A trial with this many days or fewer left is "ending soon": the app
# shows a stronger prompt and the reminder job emails the owner.
TRIAL_ENDING_SOON_DAYS = 3


def resolve_trial_plan(plan: str | None, billing_period: str | None) -> tuple[str, str]:
    """The plan and billing period a new trial uses. The plan a visitor
    picked on the pricing page carries through signup, so they never
    choose the same plan twice. Anything missing, unknown or not
    self-service (Enterprise) falls back to the default trial plan."""
    resolved_plan = plan if plan in SELF_SERVICE_PLANS else TRIAL_PLAN
    resolved_period = billing_period if billing_period in BILLING_PERIODS else "monthly"
    return resolved_plan, resolved_period


def is_app_trial(subscription: Subscription | None) -> bool:
    """True for a trial GeoCore runs itself (no Stripe subscription yet).
    A Stripe-managed trial is excluded: Stripe moves its status on at
    trial end by webhook, so GeoCore must not second-guess it."""
    return (
        subscription is not None
        and subscription.status == "trialing"
        and subscription.stripe_subscription_id is None
        and subscription.trial_end is not None
    )


def is_app_trial_expired(subscription: Subscription | None, now: datetime | None = None) -> bool:
    if not is_app_trial(subscription):
        return False
    now = now or datetime.now(timezone.utc)
    return subscription.trial_end <= now


@dataclass(frozen=True)
class TrialStatus:
    state: str  # "active" | "ending_soon" | "expired"
    days_remaining: int
    trial_end: datetime


def trial_status(subscription: Subscription | None, now: datetime | None = None) -> TrialStatus | None:
    """The trial's current state for display and reminders, or None when
    the tenant is not on an app-run trial (paid, grandfathered, Stripe
    trial, or no subscription at all)."""
    if not is_app_trial(subscription):
        return None
    now = now or datetime.now(timezone.utc)
    remaining = subscription.trial_end - now
    if remaining <= timedelta(0):
        return TrialStatus(state="expired", days_remaining=0, trial_end=subscription.trial_end)
    # Round partial days up: 2 days 1 hour left is "3 days left", never 0.
    days = remaining.days + (1 if remaining.seconds or remaining.microseconds else 0)
    state = "ending_soon" if days <= TRIAL_ENDING_SOON_DAYS else "active"
    return TrialStatus(state=state, days_remaining=days, trial_end=subscription.trial_end)


def is_eligible_for_trial(db: Session, tenant_id: uuid.UUID) -> bool:
    return crud.get_subscription_by_tenant_id(db, tenant_id) is None


def start_trial_if_eligible(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    plan: str | None = None,
    billing_period: str | None = None,
    now: datetime | None = None,
) -> Subscription | None:
    """Starts a 14-day no-card trial for a tenant that has never had a
    subscription, and returns it. For any tenant that already has one,
    returns the existing row unchanged — never a second or extended
    trial, and never a change to a paying tenant's entitlements."""
    existing = crud.get_subscription_by_tenant_id(db, tenant_id)
    if existing is not None:
        return existing

    resolved_plan, resolved_period = resolve_trial_plan(plan, billing_period)
    now = now or datetime.now(timezone.utc)
    return crud.upsert_subscription(
        db,
        tenant_id=tenant_id,
        plan=resolved_plan,
        billing_period=resolved_period,
        status="trialing",
        trial_start=now,
        trial_end=now + timedelta(days=TRIAL_LENGTH_DAYS),
    )
