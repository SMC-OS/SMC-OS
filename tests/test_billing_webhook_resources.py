"""Webhook regressions using real Stripe SDK resources and signature verification."""

import hashlib
import hmac
import json
import time
import uuid
from collections import UserDict
from unittest.mock import MagicMock

import pytest
import stripe

from app.billing.service import BillingService
from app.core.config import settings
from app.database import crud
from app.database.models import Subscription


@pytest.mark.parametrize("representation", ["sdk", "dict", "mapping"])
@pytest.mark.parametrize(
    "event_type,object_type,expected_status",
    [
        # GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES: checkout.completed
        # no longer sets `status` itself (a Checkout with trial_period_days
        # set starts "trialing", not "active" — that authoritative value
        # arrives via customer.subscription.created/updated instead). It
        # now preserves whatever status already existed for the tenant —
        # here, the fixture's "past_due" — rather than overwriting it.
        ("checkout.session.completed", "checkout.session", "past_due"),
        ("customer.subscription.updated", "subscription", "active"),
        ("customer.subscription.deleted", "subscription", "cancelled"),
        ("invoice.payment_failed", "invoice", "past_due"),
        ("invoice.paid", "invoice", "active"),
    ],
)
def test_webhook_resource_dispatch(monkeypatch, representation, event_type, object_type, expected_status):
    tenant_id = uuid.uuid4()
    existing = Subscription(
        tenant_id=tenant_id, plan="starter", billing_period="monthly", status="past_due",
        stripe_customer_id="cus_sdk", stripe_subscription_id="sub_sdk",
    )
    obj = {
        "object": object_type,
        "id": "sub_sdk" if object_type == "subscription" else "obj_sdk",
        "customer": "cus_sdk",
        "subscription": "sub_sdk",
        "metadata": {"tenant_id": str(tenant_id), "plan": "pro", "billing_period": "monthly"},
        "status": "active",
        "items": {"object": "list", "data": [{"price": {"object": "price", "id": "price_sdk"}}]},
        "current_period_end": 1893456000,
        "cancel_at_period_end": True,
    }
    event = {"object": "event", "id": "evt_sdk", "type": event_type, "data": {"object": obj}}
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_local_regression")
    monkeypatch.setattr(settings, "stripe_price_pro_monthly", "price_sdk")
    payload = json.dumps(event).encode()
    timestamp = str(int(time.time()))
    digest = hmac.new(
        settings.stripe_webhook_secret.encode(), timestamp.encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    signature = f"t={timestamp},v1={digest}"
    if representation == "sdk":
        sdk_event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
        resource_class = {
            "checkout.session": stripe.checkout.Session,
            "subscription": stripe.Subscription,
            "invoice": stripe.Invoice,
        }[object_type]
        assert isinstance(sdk_event["data"]["object"], resource_class)
        service = BillingService(stripe_module=stripe)
    else:
        if representation == "mapping":
            event["data"]["object"] = UserDict(obj)
        fake_stripe = MagicMock()
        fake_stripe.Webhook.construct_event.return_value = event
        service = BillingService(stripe_module=fake_stripe)

    mark = MagicMock(return_value=True)
    save = MagicMock()
    monkeypatch.setattr(crud, "mark_stripe_event_processed", mark)
    monkeypatch.setattr(crud, "get_subscription_by_stripe_subscription_id", lambda db, sub_id: existing)
    # checkout.session.completed resolves "what status already exists" by
    # tenant_id, not stripe_subscription_id (see
    # BillingService._handle_checkout_completed's docstring) — irrelevant
    # to every other event type here, which never call this.
    monkeypatch.setattr(crud, "get_subscription_by_tenant_id", lambda db, t_id: existing)
    monkeypatch.setattr(crud, "upsert_subscription", save)
    db = MagicMock()
    service.handle_webhook(db, payload, signature)

    mark.assert_called_once_with(db, "evt_sdk", event_type)
    save.assert_called_once()
    values = save.call_args.kwargs
    assert values["tenant_id"] == tenant_id
    assert values["status"] == expected_status
    assert values["stripe_subscription_id"] == "sub_sdk"
    if event_type in {"checkout.session.completed", "customer.subscription.updated"}:
        assert values["plan"] == "pro"
        assert values["billing_period"] == "monthly"
    if event_type == "customer.subscription.updated":
        assert values["stripe_price_id"] == "price_sdk"
        assert values["current_period_end"].timestamp() == 1893456000
        assert values["cancel_at_period_end"] is True

    # A replay must still stop before dispatch.
    mark.return_value = False
    service.handle_webhook(db, payload, signature)
    save.assert_called_once()
