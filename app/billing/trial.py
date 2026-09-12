"""14-day free trial — Sprint 039 Production Readiness Defect Gate,
Blocker 3 (docs/SPRINTS/sprint-039.md §14.3).

Deliberately a pure app-side construct: starting a trial creates a
`Subscription` row with `status="trialing"` and NO Stripe customer or
subscription id at all — Stripe is never contacted during the 14 free
days. This is a stronger guarantee than using Stripe's own trial-on-
Checkout mechanism (`subscription_data.trial_period_days`): with no
Stripe object created until a real checkout happens, there is no
possibility of ever charging a tenant who never added a payment method,
and nothing to represent dishonestly in the UI about "a card is on file
but won't be charged yet." A tenant that later completes a real Checkout
(`BillingService.create_checkout_session`) gets a genuine Stripe
subscription at that point, active immediately per Stripe's normal
billing-date rules — the trial and the paid subscription are the same
`Subscription` row, upgraded in place by that checkout's own webhook.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.billing.plans import TRIAL_LENGTH_DAYS, TRIAL_PLAN
from app.database import crud
from app.database.models import Subscription


def start_trial_if_eligible(db: Session, tenant_id: uuid.UUID) -> Subscription | None:
    """Called once, right after a new tenant is created (signup). Never
    raises, never blocks signup: if a subscription row already exists for
    this tenant (should be impossible for a brand-new tenant, but this
    guard makes the call idempotent/safe to retry regardless), this is a
    no-op that returns the existing row unchanged — a tenant never gets a
    second trial by construction (Subscription.tenant_id is unique)."""
    existing = crud.get_subscription_by_tenant_id(db, tenant_id)
    if existing is not None:
        return existing

    now = datetime.now(timezone.utc)
    return crud.upsert_subscription(
        db,
        tenant_id=tenant_id,
        plan=TRIAL_PLAN,
        billing_period="monthly",
        status="trialing",
        trial_start=now,
        trial_end=now + timedelta(days=TRIAL_LENGTH_DAYS),
    )
