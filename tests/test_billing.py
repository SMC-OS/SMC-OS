"""Sprint 032 (Workstream A) — subscriptions/billing.

Every Stripe interaction is fully mocked (billing_service._stripe injected
directly with a MagicMock, same pattern as tests/test_ai_draft.py's
OpenAI mock) — zero real Stripe calls or credentials required, matching
the sprint's own "complete everything that doesn't need real credentials"
instruction. Webhook tests fabricate a Stripe-shaped event dict returned
by a mocked stripe.Webhook.construct_event, so signature *verification*
itself is exercised via its failure path (a bad signature really is
rejected) without needing a real signing secret to construct a valid one.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.billing.service import billing_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Invitation,
    ProcessedStripeEvent,
    Subscription,
    Tenant,
    User,
)
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

TENANT_NAME = "Pytest Billing Tenant"
OWNER_EMAIL = "pytest-billing-owner@example.invalid"
STAFF_EMAIL = "pytest-billing-staff@example.invalid"
PASSWORD = "correct-horse-battery-staple"


_TEST_STRIPE_EVENT_IDS = [
    "evt_test_checkout_1",
    "evt_test_replay_1",
    "evt_test_updated_1",
]


def _cleanup():
    db = SessionLocal()
    try:
        emails = [OWNER_EMAIL, STAFF_EMAIL]
        db.execute(delete(Invitation).where(Invitation.email.in_(emails)))
        db.execute(delete(User).where(User.email.in_(emails)))
        # This file's webhook tests use fixed Stripe event ids to exercise
        # idempotency deliberately — clean their ProcessedStripeEvent rows
        # every run so a *second* run of the suite (same dev DB) doesn't
        # see them as "already processed" from a prior run and skip the
        # handler this run actually means to exercise.
        db.execute(
            delete(ProcessedStripeEvent).where(ProcessedStripeEvent.id.in_(_TEST_STRIPE_EVENT_IDS))
        )
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
        db.execute(delete(Tenant).where(Tenant.name == TENANT_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def owner_and_staff():
    _cleanup()
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=TENANT_NAME))
        owner = auth_service.create_user(
            db, tenant_id=tenant.id, name="Pytest Owner", email=OWNER_EMAIL, password=PASSWORD, role="Owner"
        )
        staff = auth_service.create_user(
            db, tenant_id=tenant.id, name="Pytest Staff", email=STAFF_EMAIL, password=PASSWORD, role="Staff"
        )
        yield tenant, owner, staff
    finally:
        db.close()
        _cleanup()


@pytest.fixture()
def owner_headers(client, owner_and_staff):
    r = client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def staff_headers(client, owner_and_staff):
    r = client.post("/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _reset_stripe_mock():
    billing_service._stripe = None
    yield
    billing_service._stripe = None


# --- Pricing page (public) ------------------------------------------------


def test_list_plans_is_public(client):
    r = client.get("/api/v1/billing/plans")
    assert r.status_code == 200
    plans = {p["plan"]: p for p in r.json()}
    assert plans["pro"]["monthly_price_gbp"] == 79
    assert plans["pro"]["annual_price_gbp"] == 790
    assert plans["business"]["monthly_price_gbp"] == 149
    assert plans["business"]["annual_price_gbp"] == 1490
    assert plans["pro"]["annual_recommended"] is True
    assert plans["business"]["annual_recommended"] is True
    assert plans["pro"]["self_service"] is True
    assert plans["business"]["self_service"] is True
    assert plans["enterprise"]["self_service"] is False
    assert plans["enterprise"]["monthly_price_gbp"] is None


def test_annual_pricing_is_cheaper_than_twelve_months_of_monthly(client):
    plans = {p["plan"]: p for p in client.get("/api/v1/billing/plans").json()}
    for plan in ("pro", "business"):
        monthly_total = plans[plan]["monthly_price_gbp"] * 12
        assert plans[plan]["annual_price_gbp"] < monthly_total


# --- Subscription status ---------------------------------------------------


def test_get_subscription_requires_auth(client):
    assert client.get("/api/v1/billing/subscription").status_code == 401


def test_get_subscription_returns_null_when_none_exists(client, owner_headers):
    r = client.get("/api/v1/billing/subscription", headers=owner_headers)
    assert r.status_code == 200
    assert r.json() is None


# --- Checkout (Owner-only, RBAC) -------------------------------------------


def test_checkout_requires_auth(client):
    r = client.post("/api/v1/billing/checkout", json={"plan": "pro", "billing_period": "monthly"})
    assert r.status_code == 401


def test_checkout_requires_owner_role(client, staff_headers):
    r = client.post(
        "/api/v1/billing/checkout",
        json={"plan": "pro", "billing_period": "monthly"},
        headers=staff_headers,
    )
    assert r.status_code == 403


def test_checkout_rejects_enterprise_self_service(client, owner_headers):
    r = client.post(
        "/api/v1/billing/checkout",
        json={"plan": "enterprise", "billing_period": "monthly"},
        headers=owner_headers,
    )
    assert r.status_code == 422


def test_checkout_returns_503_when_stripe_not_configured(client, owner_headers):
    r = client.post(
        "/api/v1/billing/checkout",
        json={"plan": "pro", "billing_period": "monthly"},
        headers=owner_headers,
    )
    assert r.status_code == 503


def test_checkout_returns_hosted_url_when_stripe_configured(client, owner_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_price_pro_monthly", "price_fake_pro_monthly")

    fake_stripe = MagicMock()
    fake_stripe.checkout.Session.create.return_value = MagicMock(
        url="https://checkout.stripe.com/pay/cs_test_fake"
    )
    billing_service._stripe = fake_stripe

    r = client.post(
        "/api/v1/billing/checkout",
        json={"plan": "pro", "billing_period": "monthly"},
        headers=owner_headers,
    )
    assert r.status_code == 200
    assert r.json()["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_fake"

    call_kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
    assert call_kwargs["line_items"][0]["price"] == "price_fake_pro_monthly"
    assert call_kwargs["metadata"]["plan"] == "pro"


def test_checkout_returns_400_when_price_id_not_configured(client, owner_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_price_pro_monthly", None)
    billing_service._stripe = MagicMock()

    r = client.post(
        "/api/v1/billing/checkout",
        json={"plan": "pro", "billing_period": "monthly"},
        headers=owner_headers,
    )
    assert r.status_code == 400


# --- Customer Portal --------------------------------------------------------


def test_portal_requires_existing_customer(client, owner_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    billing_service._stripe = MagicMock()

    r = client.post("/api/v1/billing/portal", headers=owner_headers)
    assert r.status_code == 400


def test_portal_returns_url_once_subscribed(client, owner_headers, owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")

    db = SessionLocal()
    try:
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="pro",
            billing_period="monthly",
            status="active",
            stripe_customer_id="cus_fake",
            stripe_subscription_id="sub_fake",
        )
    finally:
        db.close()

    fake_stripe = MagicMock()
    fake_stripe.billing_portal.Session.create.return_value = MagicMock(
        url="https://billing.stripe.com/session/fake"
    )
    billing_service._stripe = fake_stripe

    r = client.post("/api/v1/billing/portal", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["portal_url"] == "https://billing.stripe.com/session/fake"


# --- Cancellation / resume ---------------------------------------------------


def test_cancel_at_period_end(client, owner_headers, owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")

    db = SessionLocal()
    try:
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="business",
            billing_period="annual",
            status="active",
            stripe_customer_id="cus_fake",
            stripe_subscription_id="sub_fake",
        )
    finally:
        db.close()

    billing_service._stripe = MagicMock()

    r = client.post("/api/v1/billing/cancel", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["cancel_at_period_end"] is True
    assert r.json()["status"] == "active"  # still active until period end

    r = client.post("/api/v1/billing/resume", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["cancel_at_period_end"] is False


def test_cancel_requires_owner_role(client, staff_headers):
    r = client.post("/api/v1/billing/cancel", headers=staff_headers)
    assert r.status_code == 403


# --- Webhooks: signature verification + idempotency -------------------------


def test_webhook_rejects_bad_signature(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")

    fake_stripe = MagicMock()
    fake_stripe.Webhook.construct_event.side_effect = ValueError("bad signature")
    billing_service._stripe = fake_stripe

    r = client.post(
        "/api/v1/billing/webhook",
        content=b'{"fake": "payload"}',
        headers={"stripe-signature": "bad"},
    )
    assert r.status_code == 400


def test_webhook_returns_503_when_not_configured(client):
    r = client.post("/api/v1/billing/webhook", content=b"{}")
    assert r.status_code == 503


def test_webhook_checkout_completed_creates_active_subscription(
    client, owner_and_staff, monkeypatch
):
    tenant, _, _ = owner_and_staff
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")

    event = {
        "id": "evt_test_checkout_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_new",
                "subscription": "sub_new",
                "client_reference_id": str(tenant.id),
                "metadata": {"tenant_id": str(tenant.id), "plan": "pro", "billing_period": "monthly"},
            }
        },
    }
    fake_stripe = MagicMock()
    fake_stripe.Webhook.construct_event.return_value = event
    billing_service._stripe = fake_stripe

    db = SessionLocal()
    try:
        db.query(ProcessedStripeEvent).filter(ProcessedStripeEvent.id == event["id"]).delete()
        db.commit()
    finally:
        db.close()

    r = client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    assert r.status_code == 200

    db = SessionLocal()
    try:
        row = crud.get_subscription_by_tenant_id(db, tenant.id)
        assert row is not None
        assert row.plan == "pro"
        assert row.status == "active"
        assert row.stripe_subscription_id == "sub_new"
    finally:
        db.close()


def test_webhook_is_idempotent_on_replayed_event(client, owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")

    event = {
        "id": "evt_test_replay_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_replay",
                "subscription": "sub_replay",
                "client_reference_id": str(tenant.id),
                "metadata": {"tenant_id": str(tenant.id), "plan": "business", "billing_period": "annual"},
            }
        },
    }
    fake_stripe = MagicMock()
    fake_stripe.Webhook.construct_event.return_value = event
    billing_service._stripe = fake_stripe

    db = SessionLocal()
    try:
        db.query(ProcessedStripeEvent).filter(ProcessedStripeEvent.id == event["id"]).delete()
        db.commit()
    finally:
        db.close()

    r1 = client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    assert r1.status_code == 200

    # Simulate a mutation between deliveries that a second (buggy)
    # apply would clobber — idempotency must mean the second delivery is
    # a pure no-op, not just "doesn't crash".
    db = SessionLocal()
    try:
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="business",
            billing_period="annual",
            status="past_due",  # e.g. changed by a later, already-processed event
            stripe_customer_id="cus_replay",
            stripe_subscription_id="sub_replay",
            cancel_at_period_end=False,
        )
    finally:
        db.close()

    r2 = client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    assert r2.status_code == 200

    db = SessionLocal()
    try:
        row = crud.get_subscription_by_tenant_id(db, tenant.id)
        # Still past_due — the replayed event did NOT re-apply "active".
        assert row.status == "past_due"
    finally:
        db.close()


def test_webhook_subscription_updated_syncs_status_and_period_end(
    client, owner_and_staff, monkeypatch
):
    tenant, _, _ = owner_and_staff
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")
    monkeypatch.setattr(settings, "stripe_price_business_annual", "price_business_annual_fake")

    db = SessionLocal()
    try:
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="pro",
            billing_period="monthly",
            status="active",
            stripe_customer_id="cus_upd",
            stripe_subscription_id="sub_upd",
        )
    finally:
        db.close()

    event = {
        "id": "evt_test_updated_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_upd",
                "customer": "cus_upd",
                "status": "past_due",
                "cancel_at_period_end": True,
                "current_period_end": 1893456000,  # 2030-01-01
                "items": {"data": [{"price": {"id": "price_business_annual_fake"}}]},
            }
        },
    }
    fake_stripe = MagicMock()
    fake_stripe.Webhook.construct_event.return_value = event
    billing_service._stripe = fake_stripe

    r = client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    assert r.status_code == 200

    db = SessionLocal()
    try:
        row = crud.get_subscription_by_tenant_id(db, tenant.id)
        assert row.status == "past_due"
        assert row.cancel_at_period_end is True
        assert row.plan == "business"
        assert row.billing_period == "annual"
    finally:
        db.close()


# --- Entitlement enforcement (seats) -----------------------------------------


def test_no_subscription_is_unmetered(client, owner_headers):
    # No Subscription row at all -> legacy/unmetered, invitations succeed
    # freely (this sprint must never lock out an existing tenant that
    # hasn't chosen a plan yet).
    r = client.post(
        "/api/v1/invitations",
        json={"email": "pytest-billing-unmetered-invitee@example.invalid"},
        headers=owner_headers,
    )
    assert r.status_code == 201
    db = SessionLocal()
    try:
        db.execute(
            delete(Invitation).where(
                Invitation.email == "pytest-billing-unmetered-invitee@example.invalid"
            )
        )
        db.commit()
    finally:
        db.close()


def test_seat_limit_enforced_once_subscribed(client, owner_headers, owner_and_staff):
    tenant, _owner, _staff = owner_and_staff

    db = SessionLocal()
    try:
        # Pro plan = 5 seats. Tenant already has 2 users (owner + staff);
        # 3 more pending invitations reach the limit exactly.
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="pro",
            billing_period="monthly",
            status="active",
        )
    finally:
        db.close()

    emails = [f"pytest-billing-seat-{i}@example.invalid" for i in range(3)]
    try:
        for email in emails:
            r = client.post("/api/v1/invitations", json={"email": email}, headers=owner_headers)
            assert r.status_code == 201

        # 5th seat (2 users + 3 invites) already reached -> the 6th is blocked.
        r = client.post(
            "/api/v1/invitations",
            json={"email": "pytest-billing-seat-over-limit@example.invalid"},
            headers=owner_headers,
        )
        assert r.status_code == 402
    finally:
        db = SessionLocal()
        try:
            db.execute(
                delete(Invitation).where(
                    Invitation.email.in_(emails + ["pytest-billing-seat-over-limit@example.invalid"])
                )
            )
            db.commit()
        finally:
            db.close()
