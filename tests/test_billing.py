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

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete

from app.auth.models import SignupRequest
from app.auth.service import auth_service
from app.billing.entitlements import is_trial_expired
from app.billing.service import billing_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailVerificationToken,
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
    "evt_test_trial_conversion_1",
    "evt_test_invoice_legacy_payment_failed",
    "evt_test_invoice_legacy_paid",
    "evt_test_invoice_2026_parent_payment_failed",
    "evt_test_invoice_2026_parent_paid",
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
            # Sprint 038: this file's seat-limit tests create real
            # invitations, each of which now also attempts an email send
            # and writes a Communication row (tenant_id NOT NULL, no
            # ondelete) — same "delete before the Tenant row" requirement
            # as Subscription/ActivityLog above.
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
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
    # Sprint 039 Production Readiness Defect Gate, Blocker 3 — the locked
    # 4-tier catalogue (docs/SPRINTS/sprint-039.md §14.3). Do not restore
    # the old £79/£149 2-tier pricing here.
    r = client.get("/api/v1/billing/plans")
    assert r.status_code == 200
    plans = {p["plan"]: p for p in r.json()}
    assert plans["starter"]["monthly_price_gbp"] == 29
    assert plans["starter"]["annual_price_gbp"] == 290
    assert plans["team"]["monthly_price_gbp"] == 59
    assert plans["team"]["annual_price_gbp"] == 590
    assert plans["pro"]["monthly_price_gbp"] == 99
    assert plans["pro"]["annual_price_gbp"] == 990
    assert plans["business"]["monthly_price_gbp"] == 199
    assert plans["business"]["annual_price_gbp"] == 1990
    for plan in ("starter", "team", "pro", "business"):
        assert plans[plan]["self_service"] is True
        assert plans[plan]["annual_recommended"] is True
    assert plans["starter"]["entitlements"]["seats"] == 1
    assert plans["team"]["entitlements"]["seats"] == 3
    assert plans["pro"]["entitlements"]["seats"] == 10
    assert plans["business"]["entitlements"]["seats"] == 25
    assert plans["enterprise"]["self_service"] is False
    assert plans["enterprise"]["monthly_price_gbp"] is None
    assert plans["enterprise"]["entitlements"]["seats"] is None
    # Sprint 041 — the marketing trial-disclosure component computes "£0
    # due today" / first-billing-date from this, the same TRIAL_LENGTH_DAYS
    # constant Checkout itself uses (app/billing/service.py), never a
    # hard-coded marketing figure of its own.
    for plan in ("starter", "team", "pro", "business"):
        assert plans[plan]["trial_days"] == 14
    assert plans["enterprise"]["trial_days"] is None


def test_annual_pricing_is_exactly_ten_months_of_monthly(client):
    # Locked contract: annual = 10x monthly (2 months free), not merely
    # "cheaper than 12x" — every self-service plan, exactly.
    plans = {p["plan"]: p for p in client.get("/api/v1/billing/plans").json()}
    for plan in ("starter", "team", "pro", "business"):
        assert plans[plan]["annual_price_gbp"] == plans[plan]["monthly_price_gbp"] * 10


# --- Subscription status ---------------------------------------------------


def test_get_subscription_requires_auth(client):
    assert client.get("/api/v1/billing/subscription").status_code == 401


def test_get_subscription_returns_null_when_none_exists(client, owner_headers, owner_and_staff):
    # Sprint 039 final auth + trial gate — auth_service.create_user() now
    # auto-grants every directly-created (test fixture) tenant a
    # legacy_grandfathered Subscription, so this endpoint's true "none at
    # all" case has to be created explicitly rather than relied on as the
    # fixture's default state.
    tenant, _owner, _staff = owner_and_staff
    db = SessionLocal()
    try:
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
        db.commit()
    finally:
        db.close()

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


def test_subscription_updated_converts_a_trial_to_paid_and_preserves_trial_history(
    client, owner_and_staff, monkeypatch
):
    """GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES. Under the card-
    required trial contract, a tenant's trial and its eventual paid
    subscription are the SAME Stripe Subscription object throughout — it
    starts "trialing" (Checkout's trial_period_days) and Stripe itself
    flips it to "active" at trial end once the first invoice succeeds,
    delivered as customer.subscription.updated (not a second checkout).
    This must preserve trial_start/trial_end as historical record, not
    clear them, and BillingService._handle_subscription_upsert is the
    single handler shared by created/updated — see its own docstring."""
    tenant, _, _ = owner_and_staff
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")
    monkeypatch.setattr(settings, "stripe_price_business_annual", "price_business_annual")

    trial_start = datetime.now(timezone.utc) - timedelta(days=14)
    trial_end = datetime.now(timezone.utc) - timedelta(seconds=1)
    db = SessionLocal()
    try:
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="business",
            billing_period="annual",
            status="trialing",
            stripe_customer_id="cus_converted",
            stripe_subscription_id="sub_converted",
            trial_start=trial_start,
            trial_end=trial_end,
        )
    finally:
        db.close()

    event = {
        "id": "evt_test_trial_conversion_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_converted",
                "customer": "cus_converted",
                "status": "active",
                "items": {
                    "data": [{"price": {"id": "price_business_annual"}}],
                },
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

    r = client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    assert r.status_code == 200

    db = SessionLocal()
    try:
        row = crud.get_subscription_by_tenant_id(db, tenant.id)
        assert row.status == "active"
        assert row.plan == "business"
        assert row.stripe_customer_id == "cus_converted"
        # Trial history is preserved, not wiped by the conversion.
        assert row.trial_start is not None
        assert row.trial_end is not None
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


@pytest.mark.parametrize("invoice_shape", ["legacy", "2026_parent"])
def test_invoice_payment_lifecycle_reconciles_legacy_and_current_stripe_events(
    client, owner_and_staff, monkeypatch, invoice_shape
):
    """Real Stripe 2026-08-26.dahlia invoice events use parent.subscription_details.

    A failed payment must revoke paid status, a subsequent paid invoice must
    recover it, and redelivery of the same event must be idempotent.
    """
    tenant, _, _ = owner_and_staff
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")
    fake_stripe = MagicMock()
    billing_service._stripe = fake_stripe
    subscription_id = f"sub_invoice_{invoice_shape}"
    db = SessionLocal()
    try:
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="starter",
            billing_period="monthly",
            status="active",
            stripe_customer_id=f"cus_invoice_{invoice_shape}",
            stripe_subscription_id=subscription_id,
        )
    finally:
        db.close()

    subscription_reference = (
        {"subscription": subscription_id}
        if invoice_shape == "legacy"
        else {
            "parent": {
                "type": "subscription_details",
                "subscription_details": {"subscription": subscription_id},
            }
        }
    )

    for event_type, expected_status in (
        ("invoice.payment_failed", "past_due"),
        ("invoice.paid", "active"),
    ):
        event_id = f"evt_test_invoice_{invoice_shape}_{event_type.split('.')[-1]}"
        fake_stripe.Webhook.construct_event.return_value = {
            "id": event_id,
            "type": event_type,
            "data": {"object": {"id": f"in_{invoice_shape}", **subscription_reference}},
        }
        response = client.post(
            "/api/v1/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "signed-test-event"},
        )
        assert response.status_code == 200
        db = SessionLocal()
        try:
            row = crud.get_subscription_by_tenant_id(db, tenant.id)
            assert row.status == expected_status
            assert row.stripe_subscription_id == subscription_id
        finally:
            db.close()

    # Even if a newer event has changed the subscription, Stripe's retry of
    # the already-processed paid invoice must not re-activate it.
    db = SessionLocal()
    try:
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="starter",
            billing_period="monthly",
            status="past_due",
            stripe_customer_id=f"cus_invoice_{invoice_shape}",
            stripe_subscription_id=subscription_id,
        )
    finally:
        db.close()
    assert client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "signed-test-event"},
    ).status_code == 200
    db = SessionLocal()
    try:
        assert crud.get_subscription_by_tenant_id(db, tenant.id).status == "past_due"
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
        # Team plan = 3 seats (Sprint 039 Blocker 3's locked entitlements).
        # Tenant already has 2 users (owner + staff); one more pending
        # invitation reaches the limit exactly.
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="team",
            billing_period="monthly",
            status="active",
        )
    finally:
        db.close()

    emails = [f"pytest-billing-seat-{i}@example.invalid" for i in range(1)]
    try:
        for email in emails:
            r = client.post("/api/v1/invitations", json={"email": email}, headers=owner_headers)
            assert r.status_code == 201

        # 3rd seat (2 users + 1 invite) already reached -> the 4th is blocked.
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


# --- Trial (Sprint 039 Production Readiness Defect Gate, Blocker 3) --------

TRIAL_SIGNUP_EMAIL = "pytest-billing-trial-signup@example.invalid"
TRIAL_SIGNUP_COMPANY = "Pytest Billing Trial Signup Co"


def _cleanup_trial_signup():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == TRIAL_SIGNUP_EMAIL).first()
        if user is not None:
            db.execute(delete(Subscription).where(Subscription.tenant_id == user.tenant_id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == user.tenant_id))
            db.execute(delete(Communication).where(Communication.tenant_id == user.tenant_id))
            # Sprint 039 Blocker 1 merged after this test was first written —
            # a real signup now also creates an EmailVerificationToken
            # (user_id FK, no ondelete), same "children before parents"
            # ordering as everything else here.
            db.execute(
                delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
            )
        db.execute(delete(User).where(User.email == TRIAL_SIGNUP_EMAIL))
        db.execute(delete(Tenant).where(Tenant.name == TRIAL_SIGNUP_COMPANY))
        db.commit()
    finally:
        db.close()


def test_signup_starts_a_no_card_trial_on_the_selected_plan(client):
    """Phase B — a brand-new signup starts a 14-day trial immediately, with
    no Stripe object and no card, on the plan chosen on the pricing page
    (carried through signup so it is never chosen twice)."""
    _cleanup_trial_signup()
    try:
        r = client.post(
            "/api/v1/auth/signup",
            json={
                "company_name": TRIAL_SIGNUP_COMPANY,
                "name": "Pytest Trial Owner",
                "email": TRIAL_SIGNUP_EMAIL,
                "password": "A-Real-Password-123!",
                "plan": "team",
                "billing_period": "annual",
            },
        )
        assert r.status_code == 201
        # Still gated on email verification before billing access matters.
        assert r.json()["user"]["verification_required"] is True
        assert r.json()["user"]["billing_access_required"] is False

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == TRIAL_SIGNUP_EMAIL).first()
            sub = crud.get_subscription_by_tenant_id(db, user.tenant_id)
            assert sub.plan == "team"
            assert sub.billing_period == "annual"
            assert sub.status == "trialing"
            assert sub.stripe_customer_id is None and sub.stripe_subscription_id is None
            assert sub.legacy_grandfathered is False
            assert sub.trial_end - sub.trial_start == timedelta(days=14)
        finally:
            db.close()
    finally:
        _cleanup_trial_signup()


def test_signup_without_a_plan_or_with_a_non_self_service_plan_trials_pro(client):
    for plan in (None, "enterprise", "no-such-plan"):
        _cleanup_trial_signup()
        try:
            body = {
                "company_name": TRIAL_SIGNUP_COMPANY,
                "name": "Pytest Trial Owner",
                "email": TRIAL_SIGNUP_EMAIL,
                "password": "A-Real-Password-123!",
                "billing_period": "weekly",
            }
            if plan is not None:
                body["plan"] = plan
            assert client.post("/api/v1/auth/signup", json=body).status_code == 201
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.email == TRIAL_SIGNUP_EMAIL).first()
                sub = crud.get_subscription_by_tenant_id(db, user.tenant_id)
                assert (sub.plan, sub.billing_period) == ("pro", "monthly")
            finally:
                db.close()
        finally:
            _cleanup_trial_signup()


def test_a_tenant_never_gets_a_second_trial():
    """app/billing/trial.py's start_trial_if_eligible() is no longer
    called from signup (see the test above), but stays real, callable
    machinery — this proves its own idempotency directly: a tenant
    calling it twice never gets its trial window reset or extended."""
    from app.billing.trial import start_trial_if_eligible

    _cleanup_trial_signup()
    try:
        db = SessionLocal()
        try:
            tenant = tenant_service.create(db, TenantCreate(name=TRIAL_SIGNUP_COMPANY))
            tenant_id = tenant.id
            first = start_trial_if_eligible(db, tenant_id)
            assert first is not None
            first_trial_end = first.trial_end
        finally:
            db.close()

        db = SessionLocal()
        try:
            second = start_trial_if_eligible(db, tenant_id)
            second_trial_end = second.trial_end
        finally:
            db.close()
        assert second_trial_end == first_trial_end
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
            db.commit()
        finally:
            db.close()
        _cleanup_trial_signup()


def test_is_trial_expired_helper():
    active_trial = Subscription(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        plan="pro",
        billing_period="monthly",
        status="trialing",
        trial_start=datetime.now(timezone.utc) - timedelta(days=1),
        trial_end=datetime.now(timezone.utc) + timedelta(days=13),
    )
    assert is_trial_expired(active_trial) is False

    expired_trial = Subscription(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        plan="pro",
        billing_period="monthly",
        status="trialing",
        trial_start=datetime.now(timezone.utc) - timedelta(days=20),
        trial_end=datetime.now(timezone.utc) - timedelta(days=6),
    )
    assert is_trial_expired(expired_trial) is True

    paid = Subscription(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        plan="pro",
        billing_period="monthly",
        status="active",
        trial_start=datetime.now(timezone.utc) - timedelta(days=20),
        trial_end=datetime.now(timezone.utc) - timedelta(days=6),
    )
    assert is_trial_expired(paid) is False  # converted to paid — no longer "trialing"


def test_expired_trial_blocks_new_seats_without_disabling_existing_users(
    client, owner_headers, owner_and_staff
):
    tenant, owner, staff = owner_and_staff

    db = SessionLocal()
    try:
        crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan="pro",
            billing_period="monthly",
            status="trialing",
            trial_start=datetime.now(timezone.utc) - timedelta(days=20),
            trial_end=datetime.now(timezone.utc) - timedelta(days=6),
        )
    finally:
        db.close()

    r = client.post(
        "/api/v1/invitations",
        json={"email": "pytest-billing-expired-trial-invitee@example.invalid"},
        headers=owner_headers,
    )
    assert r.status_code == 402

    # Existing users are untouched — never disabled/deleted by an expired trial.
    db = SessionLocal()
    try:
        assert db.get(User, owner.id).is_active is True
        assert db.get(User, staff.id).is_active is True
    finally:
        db.close()


# --- Checkout cannot be tampered with (server-side price authority) --------


def test_checkout_ignores_a_client_supplied_price_or_amount(client, owner_headers, monkeypatch):
    """The request schema has no price/amount field at all — only plan +
    billing_period, both validated server-side against the authoritative
    catalogue (app/billing/plans.py). Extra client-supplied fields
    (a spoofed price_id/amount) are silently ignored by Pydantic, not
    trusted, matching the brief's 'never trust a price/amount supplied
    directly by the browser' requirement."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_price_starter_monthly", "price_real_starter_monthly")

    fake_stripe = MagicMock()
    fake_stripe.checkout.Session.create.return_value = MagicMock(
        url="https://checkout.stripe.com/pay/cs_test_fake"
    )
    billing_service._stripe = fake_stripe

    r = client.post(
        "/api/v1/billing/checkout",
        json={
            "plan": "starter",
            "billing_period": "monthly",
            "price_id": "price_attacker_supplied",
            "amount": 1,
        },
        headers=owner_headers,
    )
    assert r.status_code == 200

    call_kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
    assert call_kwargs["line_items"][0]["price"] == "price_real_starter_monthly"


def test_checkout_rejects_an_unknown_plan_string(client, owner_headers):
    r = client.post(
        "/api/v1/billing/checkout",
        json={"plan": "not-a-real-plan", "billing_period": "monthly"},
        headers=owner_headers,
    )
    assert r.status_code == 422


# ---- out-of-order delivery: Stripe does not guarantee event order, so an older event must never undo a newer one
def _post_event(client, event, monkeypatch, canonical=None):
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")
    fake_stripe = MagicMock()
    fake_stripe.Webhook.construct_event.return_value = event
    if canonical is not None:
        fake_stripe.Subscription.retrieve.side_effect = (
            canonical if callable(canonical) else lambda _sub_id: dict(canonical)
        )
    billing_service._stripe = fake_stripe
    db = SessionLocal()
    try:
        db.query(ProcessedStripeEvent).filter(ProcessedStripeEvent.id == event["id"]).delete()
        db.commit()
    finally:
        db.close()
    return client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})


def _sub_event(event_id, created, status, tenant, sub_id="sub_ooo"):
    return {"id": event_id, "type": "customer.subscription.updated", "created": created,
            "data": {"object": {"id": sub_id, "customer": "cus_ooo", "status": status, "cancel_at_period_end": False,
                                "metadata": {"tenant_id": str(tenant.id), "plan": "pro", "billing_period": "monthly"}}}}


def _status(tenant):
    db = SessionLocal()
    try:
        return crud.get_subscription_by_tenant_id(db, tenant.id).status
    finally:
        db.close()


def _canonical(tenant, sub_id, status, *, created=100, cancel=False):
    return {"id": sub_id, "customer": "cus_ooo", "status": status, "created": created,
            "cancel_at_period_end": cancel,
            "metadata": {"tenant_id": str(tenant.id), "plan": "pro", "billing_period": "monthly"}}


def test_an_older_subscription_event_does_not_undo_a_newer_one(client, owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    current = _canonical(tenant, "sub_ooo", "active")
    assert _post_event(client, _sub_event("evt_ooo_new", 2000, "active", tenant), monkeypatch, current).status_code == 200
    assert _status(tenant) == "active"
    assert _post_event(client, _sub_event("evt_ooo_old", 1000, "trialing", tenant), monkeypatch, current).status_code == 200
    assert _status(tenant) == "active"


def test_a_late_payment_failed_does_not_undo_a_later_recovery(client, owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    current = _canonical(tenant, "sub_rec", "active")
    assert _post_event(client, _sub_event("evt_rec_active", 3000, "active", tenant, "sub_rec"), monkeypatch, current).status_code == 200
    late_failure = {"id": "evt_rec_failed", "type": "invoice.payment_failed", "created": 2500,
                    "data": {"object": {"subscription": "sub_rec"}}}
    assert _post_event(client, late_failure, monkeypatch, current).status_code == 200
    assert _status(tenant) == "active"


def test_newer_events_still_apply_in_order(client, owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    _post_event(client, _sub_event("evt_ord_1", 100, "trialing", tenant, "sub_ord"), monkeypatch,
                _canonical(tenant, "sub_ord", "trialing"))
    _post_event(client, _sub_event("evt_ord_2", 200, "active", tenant, "sub_ord"), monkeypatch,
                _canonical(tenant, "sub_ord", "active"))
    failed = {"id": "evt_ord_3", "type": "invoice.payment_failed", "created": 300, "data": {"object": {"subscription": "sub_ord"}}}
    _post_event(client, failed, monkeypatch, _canonical(tenant, "sub_ord", "past_due"))
    assert _status(tenant) == "past_due"
    paid = {"id": "evt_ord_4", "type": "invoice.paid", "created": 400, "data": {"object": {"subscription": "sub_ord"}}}
    _post_event(client, paid, monkeypatch, _canonical(tenant, "sub_ord", "active"))
    assert _status(tenant) == "active"


def test_same_second_conflicting_events_use_authoritative_state(client, owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    current = _canonical(tenant, "sub_equal", "active")
    for event_id, snapshot in [("evt_equal_new", "active"), ("evt_equal_late", "trialing")]:
        assert _post_event(client, _sub_event(event_id, 500, snapshot, tenant, "sub_equal"),
                           monkeypatch, current).status_code == 200
    assert _status(tenant) == "active"


def test_invoice_before_linkage_and_noop_watermark_cannot_mask_state(client, owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    paid = {"id": "evt_first_invoice", "type": "invoice.paid", "created": 900,
            "data": {"object": {"parent": {"type": "subscription_details",
                                         "subscription_details": {"subscription": "sub_first"}}}}}
    assert _post_event(client, paid, monkeypatch, _canonical(tenant, "sub_first", "active")).status_code == 200
    assert _status(tenant) == "active"
    # A newer no-op invoice cannot mask a current plan/status change whose
    # notification carries an older event timestamp.
    assert _post_event(client, _sub_event("evt_first_older", 800, "past_due", tenant, "sub_first"),
                       monkeypatch, _canonical(tenant, "sub_first", "past_due")).status_code == 200
    assert _status(tenant) == "past_due"


def test_retired_subscription_event_cannot_replace_new_contract(client, owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    old = _canonical(tenant, "sub_retired", "canceled", created=100)
    new = _canonical(tenant, "sub_replacement", "active", created=200)
    assert _post_event(client, _sub_event("evt_retired", 300, "canceled", tenant, "sub_retired"),
                       monkeypatch, old).status_code == 200
    resources = {"sub_retired": old, "sub_replacement": new}
    assert _post_event(client, _sub_event("evt_replacement", 400, "active", tenant, "sub_replacement"),
                       monkeypatch, lambda sub_id: dict(resources[sub_id])).status_code == 200
    assert _post_event(client, _sub_event("evt_retired_late", 500, "active", tenant, "sub_retired"),
                       monkeypatch, old).status_code == 200
    db = SessionLocal()
    try:
        row = crud.get_subscription_by_tenant_id(db, tenant.id)
        assert row.stripe_subscription_id == "sub_replacement"
        assert row.status == "active"
    finally:
        db.close()


def test_reconciliation_failure_rolls_back_marker_and_state(owner_and_staff, monkeypatch):
    tenant, _, _ = owner_and_staff
    from app.core.config import settings
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")
    stripe = MagicMock()
    event = _sub_event("evt_atomic_" + uuid.uuid4().hex, 600, "past_due", tenant, "sub_atomic")
    stripe.Webhook.construct_event.return_value = event
    stripe.Subscription.retrieve.return_value = _canonical(tenant, "sub_atomic", "past_due")
    billing_service._stripe = stripe
    original = crud.upsert_subscription
    def fail_after_flush(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("forced failure after flush")
    monkeypatch.setattr(crud, "upsert_subscription", fail_after_flush)
    db = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="forced failure"):
            billing_service.handle_webhook(db, b"{}", "sig")
        assert db.get(ProcessedStripeEvent, event["id"]) is None
        assert crud.get_subscription_by_tenant_id(db, tenant.id).status == "active"
    finally:
        db.close()


def test_concurrent_distinct_events_serialize_on_tenant(owner_and_staff, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.core.config import settings
    from app.billing.service import BillingService
    tenant, _, _ = owner_and_staff
    tenant_id = tenant.id
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")
    first_entered, release_first, second_started, second_entered = Event(), Event(), Event(), Event()
    ids = ["evt_parallel_" + uuid.uuid4().hex for _ in range(2)]
    events = [_sub_event(ids[0], 700, "trialing", tenant, "sub_parallel"),
              _sub_event(ids[1], 700, "active", tenant, "sub_parallel")]
    snapshots = [_canonical(tenant, "sub_parallel", "trialing"),
                 _canonical(tenant, "sub_parallel", "active")]

    def deliver(index):
        stripe = MagicMock()
        stripe.Webhook.construct_event.return_value = events[index]
        def retrieve(_sub_id):
            if index == 0:
                first_entered.set()
                if not release_first.wait(10):
                    raise RuntimeError("test synchronization timed out")
            else:
                second_entered.set()
            return dict(snapshots[index])
        stripe.Subscription.retrieve.side_effect = retrieve
        db = SessionLocal()
        try:
            if index == 1:
                second_started.set()
            BillingService(stripe).handle_webhook(db, b"{}", "sig")
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(deliver, 0)
        try:
            assert first_entered.wait(10)
            second = pool.submit(deliver, 1)
            assert second_started.wait(10)
            # While the first read holds the tenant lock, the second
            # must not enter its own authoritative read.
            assert not second_entered.wait(0.5)
        finally:
            release_first.set()
        first.result(timeout=15)
        second.result(timeout=15)
    assert second_entered.is_set()
    db = SessionLocal()
    try:
        assert crud.get_subscription_by_tenant_id(db, tenant_id).status == "active"
        assert all(db.get(ProcessedStripeEvent, event_id) is not None for event_id in ids)
    finally:
        db.close()
