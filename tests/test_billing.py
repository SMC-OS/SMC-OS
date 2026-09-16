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


def test_signup_starts_no_subscription_and_blocks_workspace_access(client):
    """GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES. The owner's decision
    superseded the old no-card 14-day trial this test used to assert
    (see git history for that prior contract): a brand-new signup now
    gets NO Subscription row at all, and a verified-but-not-yet-activated
    user is blocked from normal workspace APIs (402) until a real Stripe
    Checkout completes — see app/auth/dependencies.py::require_billing_access.
    Plan selection and Checkout initiation themselves
    (app/billing/router.py) stay reachable throughout, which is exactly
    why GET /billing/subscription below still returns 200 (null), not 402."""
    _cleanup_trial_signup()
    try:
        r = client.post(
            "/api/v1/auth/signup",
            json={
                "company_name": TRIAL_SIGNUP_COMPANY,
                "name": "Pytest Trial Owner",
                "email": TRIAL_SIGNUP_EMAIL,
                "password": "A-Real-Password-123!",
            },
        )
        assert r.status_code == 201
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # This test's subject is billing/access state, not email
        # verification — mark verified immediately (same reasoning as
        # conftest.py's other_tenant_auth_headers) so a 403 from
        # require_verified_email can never be mistaken for the 402 this
        # test actually asserts.
        db = SessionLocal()
        try:
            db.query(User).filter(User.email == TRIAL_SIGNUP_EMAIL).update(
                {"email_verified_at": datetime.now(timezone.utc)}
            )
            db.commit()
        finally:
            db.close()

        # No Subscription row exists — Stripe was never contacted.
        sub_response = client.get("/api/v1/billing/subscription", headers=headers)
        assert sub_response.status_code == 200
        assert sub_response.json() is None

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == TRIAL_SIGNUP_EMAIL).first()
            assert crud.get_subscription_by_tenant_id(db, user.tenant_id) is None
        finally:
            db.close()

        # The actual access boundary: a normal workspace route is blocked,
        # while account/session management and billing/plan-selection
        # stay reachable throughout (confirmed above and by /auth/me).
        assert client.get("/api/v1/customers", headers=headers).status_code == 402
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
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
