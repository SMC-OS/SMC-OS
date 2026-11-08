"""Billing disclosures must distinguish free grants from Stripe subscriptions."""
from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

import pytest

from app.billing.router import _subscription_out


@pytest.mark.parametrize("grandfathered,stripe_id,complimentary", [
    (True, None, True), (False, None, False),
    (True, "sub_paid", False), (False, "sub_paid", False),
])
def test_complimentary_disclosure_requires_free_grant_without_paid_subscription(
    grandfathered, stripe_id, complimentary,
):
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), plan="pro", billing_period="monthly",
        status="active", legacy_grandfathered=grandfathered,
        stripe_subscription_id=stripe_id, stripe_customer_id=None,
        current_period_end=None, cancel_at_period_end=False,
        trial_start=None, trial_end=None, created_at=now, updated_at=now,
    )
    result = _subscription_out(row)
    assert result.complimentary is complimentary
    assert result.trial_state is None
