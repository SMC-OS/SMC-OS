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
