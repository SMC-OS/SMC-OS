"""Phase 5 — a Stripe event is recorded as processed only together with its
effect. A handler failure must leave the event unrecorded so Stripe's retry
applies it, instead of the retry being dropped as a duplicate."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.billing.service import BillingService
from app.core.config import settings
from app.database import crud
from app.database.models import ProcessedStripeEvent, Subscription
from tests.test_procurement import _cleanup_tenant, _make_tenant, db  # noqa: F401


def _event(event_id, subscription_id, event_type="invoice.payment_failed"):
    return {
        "id": event_id,
        "type": event_type,
        "data": {"object": {"id": "in_test", "parent": {
            "type": "subscription_details", "subscription_details": {"subscription": subscription_id}}}},
    }


@pytest.fixture()
def subscribed(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test_fake")
    tenant = _make_tenant(db, f"Webhook{uuid.uuid4().hex[:6]}")
    sub_id = f"sub_test_{uuid.uuid4().hex[:10]}"
    db.add(Subscription(id=uuid.uuid4(), tenant_id=tenant.id, plan="pro", billing_period="monthly",
                        status="active", stripe_customer_id="cus_test", stripe_subscription_id=sub_id))
    db.commit()
    event_ids = []
    yield tenant, sub_id, event_ids
    for event_id in event_ids:
        row = db.get(ProcessedStripeEvent, event_id)
        if row is not None:
            db.delete(row)
    db.commit()
    _cleanup_tenant(tenant.id)


def _service(event):
    fake = MagicMock()
    fake.Webhook.construct_event.return_value = event
    return BillingService(stripe_module=fake)


def _status(db, sub_id):  # noqa: F811
    db.expire_all()
    return crud.get_subscription_by_stripe_subscription_id(db, sub_id).status


def test_a_failed_handler_leaves_the_event_unrecorded_and_the_retry_applies_it(db, subscribed, monkeypatch):  # noqa: F811
    _tenant, sub_id, event_ids = subscribed
    event_id = f"evt_test_{uuid.uuid4().hex[:10]}"
    event_ids.append(event_id)
    service = _service(_event(event_id, sub_id))
    real_upsert = crud.upsert_subscription

    def failing_upsert(*_args, **_kwargs):
        raise RuntimeError("injected database failure")

    monkeypatch.setattr(crud, "upsert_subscription", failing_upsert)
    with pytest.raises(RuntimeError):
        service.handle_webhook(db, b"{}", "t=1,v1=fake")
    assert db.get(ProcessedStripeEvent, event_id) is None
    assert _status(db, sub_id) == "active"

    monkeypatch.setattr(crud, "upsert_subscription", real_upsert)
    service.handle_webhook(db, b"{}", "t=1,v1=fake")  # Stripe's retry
    assert db.get(ProcessedStripeEvent, event_id) is not None
    assert _status(db, sub_id) == "past_due"


def test_a_replayed_event_is_applied_once(db, subscribed, monkeypatch):  # noqa: F811
    _tenant, sub_id, event_ids = subscribed
    event_id = f"evt_test_{uuid.uuid4().hex[:10]}"
    event_ids.append(event_id)
    service = _service(_event(event_id, sub_id))
    service.handle_webhook(db, b"{}", "t=1,v1=fake")
    assert _status(db, sub_id) == "past_due"
    calls = MagicMock()
    monkeypatch.setattr(crud, "upsert_subscription", calls)
    service.handle_webhook(db, b"{}", "t=1,v1=fake")
    calls.assert_not_called()


def test_an_unhandled_event_type_is_still_recorded(db, subscribed):  # noqa: F811
    _tenant, sub_id, event_ids = subscribed
    event_id = f"evt_test_{uuid.uuid4().hex[:10]}"
    event_ids.append(event_id)
    _service(_event(event_id, sub_id, event_type="customer.created")).handle_webhook(db, b"{}", "t=1,v1=fake")
    db.expire_all()
    assert db.get(ProcessedStripeEvent, event_id) is not None
    assert _status(db, sub_id) == "active"
