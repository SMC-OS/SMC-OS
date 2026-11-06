"""Issue #67 P0 — server-side admission/checkout gate. With admission closed
no new workspace, trial or first-time paid checkout can start through the
API, while existing users and existing paying subscriptions keep working.
With it open (the default) nothing changes."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.billing.service import billing_service
from app.core.config import settings
from app.database.models import Subscription
from tests.test_procurement import (
    STRONG_PASSWORD,
    _cleanup_tenant,
    _make_owner_headers,
    _make_tenant,
    db,  # noqa: F401 - pytest fixture
)


@pytest.fixture()
def closed(monkeypatch):
    monkeypatch.setattr(settings, "new_account_admission", "closed")


@pytest.fixture()
def workspace(client, db):  # noqa: F811
    tenant = _make_tenant(db, f"Admission{uuid.uuid4().hex[:6]}")
    headers, user = _make_owner_headers(client, db, tenant, "admission")
    yield tenant, headers, user
    _cleanup_tenant(tenant.id)


def _signup_body():
    return {
        "company_name": f"Pytest Admission Co {uuid.uuid4().hex[:6]}",
        "name": "Pytest Admission Owner",
        "email": f"pytest-admission-{uuid.uuid4().hex[:10]}@example.invalid",
        "password": STRONG_PASSWORD,
    }


def _stripe_configured(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_price_pro_monthly", "price_fake_pro_monthly")
    fake = MagicMock()
    fake.checkout.Session.create.return_value = MagicMock(url="https://checkout.stripe.com/pay/cs_test_fake")
    monkeypatch.setattr(billing_service, "_stripe", fake)
    return fake


def test_admission_is_open_by_default(client):
    assert settings.new_account_admission == "open"
    assert client.get("/api/v1/auth/admission").json() == {"signups_open": True}


def test_closed_admission_refuses_signup_and_creates_nothing(client, db, closed):  # noqa: F811
    from app.database import crud

    body = _signup_body()
    response = client.post("/api/v1/auth/signup", json=body)
    assert response.status_code == 403, response.text
    assert "not accepting new accounts" in response.json()["detail"]
    assert crud.get_user_by_email(db, body["email"]) is None
    assert client.get("/api/v1/auth/admission").json() == {"signups_open": False}


def test_closed_admission_refuses_a_new_trial(client, workspace, closed):
    _tenant, headers, _user = workspace
    response = client.post("/api/v1/billing/trial", json={}, headers=headers)
    assert response.status_code == 403, response.text


def test_closed_admission_refuses_first_time_checkout_without_calling_stripe(client, workspace, closed, monkeypatch):
    _tenant, headers, _user = workspace
    fake = _stripe_configured(monkeypatch)
    response = client.post(
        "/api/v1/billing/checkout", json={"plan": "pro", "billing_period": "monthly"}, headers=headers
    )
    assert response.status_code == 403, response.text
    fake.checkout.Session.create.assert_not_called()


def test_closed_admission_still_lets_an_existing_subscriber_use_checkout(client, db, workspace, closed, monkeypatch):  # noqa: F811
    tenant, headers, _user = workspace
    subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).one_or_none()
    if subscription is None:
        subscription = Subscription(id=uuid.uuid4(), tenant_id=tenant.id, plan="pro", billing_period="monthly")
        db.add(subscription)
    subscription.status = "active"
    subscription.stripe_customer_id = "cus_test_existing"
    subscription.stripe_subscription_id = f"sub_test_{uuid.uuid4().hex[:8]}"
    db.commit()
    fake = _stripe_configured(monkeypatch)
    response = client.post(
        "/api/v1/billing/checkout", json={"plan": "pro", "billing_period": "monthly"}, headers=headers
    )
    assert response.status_code == 200, response.text
    fake.checkout.Session.create.assert_called_once()


def test_closed_admission_does_not_lock_out_existing_users(client, workspace, closed):
    _tenant, headers, user = workspace
    assert client.post("/api/v1/auth/login", json={"email": user.email, "password": STRONG_PASSWORD}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200


def test_reopening_admission_restores_signup(client, db, monkeypatch):  # noqa: F811
    from app.database import crud

    monkeypatch.setattr(settings, "new_account_admission", "closed")
    assert client.post("/api/v1/auth/signup", json=_signup_body()).status_code == 403
    monkeypatch.setattr(settings, "new_account_admission", "open")
    body = _signup_body()
    response = client.post("/api/v1/auth/signup", json=body)
    assert response.status_code == 201, response.text
    user = crud.get_user_by_email(db, body["email"])
    _cleanup_signed_up_tenant(user.tenant_id)


def _cleanup_signed_up_tenant(tenant_id):
    """A real signup also writes a verification token and an outbound
    email record, which reference the user and must go first."""
    from sqlalchemy import delete

    from app.database.database import SessionLocal
    from app.database.models import Communication, EmailVerificationToken, User

    session = SessionLocal()
    try:
        user_ids = [row[0] for row in session.query(User.id).filter(User.tenant_id == tenant_id).all()]
        session.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(user_ids)))
        session.execute(delete(Communication).where(Communication.tenant_id == tenant_id))
        session.commit()
    finally:
        session.close()
    _cleanup_tenant(tenant_id)
