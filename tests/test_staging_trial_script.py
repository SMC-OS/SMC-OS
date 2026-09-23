"""Phase B — the staging Stripe TEST-mode verification script's own guards
and its database-side logic, exercised locally with a fake Stripe (the
real Stripe run happens on staging only)."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from app.billing.service import billing_service
from app.core.config import settings
from app.database.database import SessionLocal
from app.database.models import Tenant

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "staging" / "verify_trial_billing.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_trial_billing", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refuses_without_the_staging_confirmation(capsys):
    assert _load().main(["setup"]) == 2
    assert "--confirm-staging" in capsys.readouterr().out


@pytest.mark.parametrize("key", [None, "", "sk_live_abc", "rk_live_abc"])
def test_refuses_anything_but_a_stripe_test_key(monkeypatch, key):
    monkeypatch.setattr(settings, "stripe_secret_key", key)
    with pytest.raises(SystemExit) as exc:
        _load().main(["setup", "--confirm-staging"])
    assert "TEST key" in str(exc.value)


def test_setup_and_cleanup_against_a_fake_stripe(monkeypatch, capsys):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_price_business_annual", "price_fake_business_annual")
    fake = MagicMock()
    fake.checkout.Session.create.return_value = MagicMock(url="https://checkout.stripe.com/c/pay/cs_test_x")
    fake.test_helpers.TestClock.create.return_value = MagicMock(id="clock_1")
    fake.Customer.create.return_value = MagicMock(id="cus_test_clock")
    fake.Customer.retrieve.return_value = {"test_clock": "clock_1"}
    billing_service._stripe = fake
    module = _load()
    try:
        assert module.main(["setup", "--confirm-staging"]) == 0, capsys.readouterr().out
        out = capsys.readouterr().out
        assert "FAIL" not in out
        params = fake.checkout.Session.create.call_args.kwargs
        assert params["customer"] == "cus_test_clock"  # the test-clock customer governs billing
        assert "trial_end" in params["subscription_data"]
    finally:
        assert module.main(["cleanup", "--confirm-staging"]) == 0
        billing_service._stripe = None
    fake.test_helpers.TestClock.delete.assert_called_with("clock_1")
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(Tenant.id)).where(Tenant.name.like("PhaseB Verify %"))) == 0
    finally:
        db.close()


def _stripe_obj(cls, values: dict):
    """A real StripeObject (not a dict since stripe-python v13), exactly the
    type the live SDK returns — so `.get()` misuse fails here, not on staging."""
    return cls.construct_from(values, "sk_test_fake")


def test_field_reads_real_stripe_objects_and_plain_dicts():
    import stripe

    field = _load().field
    sub = _stripe_obj(stripe.Subscription, {"id": "sub_1", "default_payment_method": None})
    assert not issubclass(stripe.StripeObject, dict)
    with pytest.raises(AttributeError):
        sub.get("id")  # the SDK behaviour that crashed `verify` on staging
    assert field(sub, "id") == "sub_1"
    assert field(sub, "default_payment_method") is None
    assert field(sub, "missing", "fallback") == "fallback"
    assert field(None, "anything") is None
    assert field({"test_clock": "clock_1"}, "test_clock") == "clock_1"


def test_verify_and_cleanup_against_real_stripe_objects(monkeypatch, capsys):
    import stripe

    from app.billing.plans import PRICING_GBP
    from app.database import crud

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_price_business_annual", "price_fake_business_annual")
    fake = MagicMock()
    fake.checkout.Session.create.return_value = MagicMock(url="https://checkout.stripe.com/c/pay/cs_test_x")
    fake.test_helpers.TestClock.create.return_value = MagicMock(id="clock_1")
    fake.Customer.create.return_value = MagicMock(id="cus_test_clock")
    billing_service._stripe = fake
    module = _load()
    try:
        assert module.main(["setup", "--confirm-staging"]) == 0, capsys.readouterr().out
        capsys.readouterr()

        db = SessionLocal()
        try:
            tenant = module.workspace(db, "TIMELINE")
            row = crud.get_subscription_by_tenant_id(db, tenant.id)
            trial_end = int(row.trial_end.timestamp())
            # What the real checkout.session.completed webhook leaves behind.
            row.stripe_subscription_id = "sub_test_1"
            row.plan, row.billing_period, row.status = "business", "annual", "trialing"
            db.commit()
        finally:
            db.close()

        subscription = _stripe_obj(stripe.Subscription, {
            "id": "sub_test_1", "status": "trialing", "trial_end": trial_end,
            "default_payment_method": None,  # card saved on the customer instead
            "items": {"object": "list", "data": [{"price": {"id": "price_fake_business_annual"}}]},
        })
        fake.Subscription.list.return_value = MagicMock(data=[subscription])
        fake.Customer.retrieve.return_value = _stripe_obj(stripe.Customer, {
            "id": "cus_test_clock", "test_clock": "clock_1",
            "invoice_settings": {"default_payment_method": "pm_card_visa"},
        })
        fake.Invoice.create_preview.return_value = _stripe_obj(stripe.Invoice, {
            "next_payment_attempt": trial_end,
            "amount_due": PRICING_GBP["business"]["annual"] * 100,
        })

        assert module.main(["verify", "--confirm-staging"]) == 0, capsys.readouterr().out
        out = capsys.readouterr().out
        assert "FAIL" not in out
        assert "PASS  Checkout collected a payment method" in out
        assert "PASS  first charge scheduled at trial_end" in out
    finally:
        assert module.main(["cleanup", "--confirm-staging"]) == 0
        billing_service._stripe = None
    fake.test_helpers.TestClock.delete.assert_called_with("clock_1")
