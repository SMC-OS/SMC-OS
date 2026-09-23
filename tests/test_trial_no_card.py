"""Phase B — the 14-day no-card trial: state, Checkout behaviour, the
start-trial endpoint for pre-Phase-B workspaces, eligibility, and the
trial-expiry reminder emails."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.billing.service import billing_service
from app.billing.trial import (
    is_app_trial_expired,
    resolve_trial_plan,
    start_trial_if_eligible,
    trial_status,
)
from app.billing.trial_reminders import TrialReminderService
from app.communications.provider import SendOutcome, SendResult
from app.communications.service import DeliveryService
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Communication, Subscription, Tenant, User
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

RUN = uuid.uuid4().hex[:8]
PASSWORD = "Trial-No-Card-Password-1!"
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _sub(**overrides) -> Subscription:
    base = dict(
        plan="pro",
        billing_period="monthly",
        status="trialing",
        stripe_subscription_id=None,
        trial_start=NOW - timedelta(days=1),
        trial_end=NOW + timedelta(days=13),
        legacy_grandfathered=False,
    )
    base.update(overrides)
    return Subscription(**base)


# --- Pure trial state ---------------------------------------------------------


def test_trial_status_active_ending_soon_and_expired():
    assert trial_status(_sub(), NOW).state == "active"
    assert trial_status(_sub(), NOW).days_remaining == 13
    assert trial_status(_sub(trial_end=NOW + timedelta(days=3)), NOW).state == "ending_soon"
    # A partial day rounds up: never "0 days left" while time remains.
    partial = trial_status(_sub(trial_end=NOW + timedelta(hours=5)), NOW)
    assert (partial.state, partial.days_remaining) == ("ending_soon", 1)
    expired = trial_status(_sub(trial_end=NOW - timedelta(seconds=1)), NOW)
    assert (expired.state, expired.days_remaining) == ("expired", 0)


def test_trial_status_is_none_for_anything_but_an_app_run_trial():
    assert trial_status(None, NOW) is None
    assert trial_status(_sub(status="active"), NOW) is None
    assert trial_status(_sub(stripe_subscription_id="sub_123"), NOW) is None
    assert is_app_trial_expired(_sub(stripe_subscription_id="sub_123", trial_end=NOW - timedelta(days=1)), NOW) is False


def test_resolve_trial_plan_only_accepts_self_service_choices():
    assert resolve_trial_plan("starter", "annual") == ("starter", "annual")
    assert resolve_trial_plan("business", None) == ("business", "monthly")
    assert resolve_trial_plan("enterprise", "annual") == ("pro", "annual")
    assert resolve_trial_plan(None, None) == ("pro", "monthly")


# --- Fixtures -------------------------------------------------------------------


def _cleanup_tenant(tenant_id):
    db = SessionLocal()
    try:
        db.execute(delete(Communication).where(Communication.tenant_id == tenant_id))
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(User).where(User.tenant_id == tenant_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def bare_workspace(client):
    """An Owner (and a Staff user) in a workspace with NO subscription —
    the state of a pre-Phase-B signup that never completed Checkout."""
    db = SessionLocal()
    tenant = tenant_service.create(db, TenantCreate(name=f"Trial NoCard {RUN} {uuid.uuid4().hex[:4]}"))
    owner_email = f"trial-owner-{uuid.uuid4().hex[:8]}@example.invalid"
    staff_email = f"trial-staff-{uuid.uuid4().hex[:8]}@example.invalid"
    for email, role in ((owner_email, "Owner"), (staff_email, "Staff")):
        auth_service.create_user(
            db, tenant_id=tenant.id, name=f"Pytest {role}", email=email, password=PASSWORD, role=role,
            grant_legacy_billing_access=False,
        )
    tenant_id = tenant.id
    db.close()

    def headers(email):
        r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    yield tenant_id, headers(owner_email), headers(staff_email)
    _cleanup_tenant(tenant_id)


# --- POST /billing/trial --------------------------------------------------------


def test_owner_can_start_a_no_card_trial_for_a_workspace_without_one(client, bare_workspace):
    tenant_id, owner, _ = bare_workspace
    assert client.get("/api/v1/customers", headers=owner).status_code == 402

    r = client.post("/api/v1/billing/trial", json={"plan": "starter", "billing_period": "annual"}, headers=owner)
    assert r.status_code == 201, r.text
    assert (r.json()["plan"], r.json()["billing_period"], r.json()["status"]) == ("starter", "annual", "trialing")
    assert r.json()["trial_state"] == "active"
    assert client.get("/api/v1/customers", headers=owner).status_code == 200


def test_staff_cannot_start_the_trial(client, bare_workspace):
    _, _, staff = bare_workspace
    assert client.post("/api/v1/billing/trial", headers=staff).status_code == 403


def test_a_workspace_can_never_start_a_second_trial(client, bare_workspace):
    tenant_id, owner, _ = bare_workspace
    assert client.post("/api/v1/billing/trial", headers=owner).status_code == 201
    db = SessionLocal()
    try:
        sub = crud.get_subscription_by_tenant_id(db, tenant_id)
        sub.trial_end = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    finally:
        db.close()
    second = client.post("/api/v1/billing/trial", headers=owner)
    assert second.status_code == 409
    assert client.get("/api/v1/billing/subscription", headers=owner).json()["trial_state"] == "expired"


@pytest.mark.parametrize(
    "existing",
    [
        dict(status="active", stripe_customer_id="cus_x", stripe_subscription_id="sub_paid"),
        dict(status="cancelled", stripe_customer_id="cus_x", stripe_subscription_id="sub_cancelled"),
        dict(status="active", legacy_grandfathered=True),
        dict(status="past_due", stripe_customer_id="cus_x", stripe_subscription_id="sub_past_due"),
    ],
)
def test_existing_customers_never_receive_a_new_trial_or_lose_entitlements(client, bare_workspace, existing):
    tenant_id, owner, _ = bare_workspace
    existing = dict(existing)
    if "stripe_subscription_id" in existing:
        existing["stripe_subscription_id"] += uuid.uuid4().hex[:6]
    db = SessionLocal()
    try:
        crud.upsert_subscription(db, tenant_id=tenant_id, plan="business", billing_period="annual", **existing)
        before = crud.get_subscription_by_tenant_id(db, tenant_id)
        snapshot = (before.plan, before.billing_period, before.status, before.trial_end, before.legacy_grandfathered)

        assert client.post("/api/v1/billing/trial", headers=owner).status_code == 409
        again = start_trial_if_eligible(db, tenant_id, plan="starter")
        db.refresh(again)
        assert (again.plan, again.billing_period, again.status, again.trial_end, again.legacy_grandfathered) == snapshot
    finally:
        db.close()


# --- Checkout collects payment details and never adds a fresh trial -----------


def _checkout(client, owner, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_price_pro_monthly", "price_fake_pro_monthly")
    fake = MagicMock()
    fake.checkout.Session.create.return_value = MagicMock(url="https://checkout.stripe.com/pay/cs_fake")
    billing_service._stripe = fake
    try:
        r = client.post("/api/v1/billing/checkout", json={"plan": "pro", "billing_period": "monthly"}, headers=owner)
        assert r.status_code == 200, r.text
        return fake.checkout.Session.create.call_args.kwargs
    finally:
        billing_service._stripe = None


def test_checkout_during_a_trial_keeps_the_remaining_trial_days(client, bare_workspace, monkeypatch):
    tenant_id, owner, _ = bare_workspace
    client.post("/api/v1/billing/trial", headers=owner)
    db = SessionLocal()
    try:
        trial_end = crud.get_subscription_by_tenant_id(db, tenant_id).trial_end
    finally:
        db.close()

    kwargs = _checkout(client, owner, monkeypatch)
    assert "trial_period_days" not in kwargs["subscription_data"]
    assert kwargs["subscription_data"]["trial_end"] == int(trial_end.timestamp())
    assert "payment_method_collection" not in kwargs  # Stripe's default: always collect


def test_checkout_near_or_after_trial_end_charges_immediately(client, bare_workspace, monkeypatch):
    tenant_id, owner, _ = bare_workspace
    client.post("/api/v1/billing/trial", headers=owner)
    for remaining in (timedelta(hours=47), timedelta(days=-2)):
        db = SessionLocal()
        try:
            sub = crud.get_subscription_by_tenant_id(db, tenant_id)
            sub.trial_end = datetime.now(timezone.utc) + remaining
            db.commit()
        finally:
            db.close()
        kwargs = _checkout(client, owner, monkeypatch)
        assert "trial_end" not in kwargs["subscription_data"]
        assert "trial_period_days" not in kwargs["subscription_data"]


def test_checkout_for_a_workspace_that_never_trialled_grants_no_trial(client, bare_workspace, monkeypatch):
    _, owner, _ = bare_workspace
    kwargs = _checkout(client, owner, monkeypatch)
    assert "trial_end" not in kwargs["subscription_data"]
    assert "trial_period_days" not in kwargs["subscription_data"]


@pytest.fixture(autouse=True)
def _email_configured(monkeypatch):
    """Reminders only run where email can really be sent (see
    TrialReminderService.run); tests configure it explicitly."""
    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(_settings, "frontend_base_url", "https://app.geocore.test")


# --- Reminder emails --------------------------------------------------------------


class _FakeProvider:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        return SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id=f"msg-{len(self.sent)}")


def _workspace_on_trial(trial_end: datetime, *, owner_verified: bool = True):
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=f"Reminder {RUN} {uuid.uuid4().hex[:4]}"))
        auth_service.create_user(
            db, tenant_id=tenant.id, name="Reminder Owner",
            email=f"reminder-{uuid.uuid4().hex[:8]}@example.invalid", password=PASSWORD, role="Owner",
            email_verified=owner_verified, grant_legacy_billing_access=False,
        )
        crud.upsert_subscription(
            db, tenant_id=tenant.id, plan="pro", billing_period="monthly", status="trialing",
            trial_start=trial_end - timedelta(days=14), trial_end=trial_end,
        )
        return tenant.id
    finally:
        db.close()


def _reminder_types(tenant_id):
    db = SessionLocal()
    try:
        return sorted(c.message_type for c in db.query(Communication).filter(Communication.tenant_id == tenant_id))
    finally:
        db.close()


def test_reminders_send_ending_then_ended_exactly_once_each():
    now = datetime.now(timezone.utc)
    active = _workspace_on_trial(now + timedelta(days=10))
    ending = _workspace_on_trial(now + timedelta(days=2))
    ended = _workspace_on_trial(now - timedelta(hours=1))
    unverified = _workspace_on_trial(now + timedelta(days=1), owner_verified=False)
    provider = _FakeProvider()
    service = TrialReminderService(delivery=DeliveryService(provider=provider))
    try:
        for _ in range(3):  # a daily job re-run never re-sends
            db = SessionLocal()
            try:
                service.run(db, now=now)
            finally:
                db.close()

        assert _reminder_types(active) == []
        assert _reminder_types(ending) == ["trial_ending"]
        assert _reminder_types(ended) == ["trial_ended"]
        assert _reminder_types(unverified) == []
        subjects = sorted(m.subject for m in provider.sent)
        assert subjects == ["Your GeoCore free trial ends in 2 days", "Your GeoCore free trial has ended"]
    finally:
        for tenant_id in (active, ending, ended, unverified):
            _cleanup_tenant(tenant_id)


def test_reminders_never_touch_paid_grandfathered_or_stripe_managed_subscriptions():
    now = datetime.now(timezone.utc)
    ids = []
    for extra in (
        dict(status="active"),
        dict(legacy_grandfathered=True),
        dict(stripe_customer_id="cus_r", stripe_subscription_id=f"sub_r_{uuid.uuid4().hex[:6]}"),
    ):
        tenant_id = _workspace_on_trial(now - timedelta(days=1))
        db = SessionLocal()
        try:
            sub = crud.get_subscription_by_tenant_id(db, tenant_id)
            for key, value in extra.items():
                setattr(sub, key, value)
            db.commit()
        finally:
            db.close()
        ids.append(tenant_id)
    provider = _FakeProvider()
    try:
        db = SessionLocal()
        try:
            TrialReminderService(delivery=DeliveryService(provider=provider)).run(db, now=now)
        finally:
            db.close()
        assert provider.sent == []
    finally:
        for tenant_id in ids:
            _cleanup_tenant(tenant_id)


def test_follow_up_job_also_reports_trial_reminders(capsys):
    from app.jobs import follow_up

    assert follow_up.main([]) == 0
    assert '"trial_reminders"' in capsys.readouterr().out


def test_reminders_record_nothing_where_email_is_not_configured(monkeypatch):
    """A worker without RESEND_API_KEY or a real FRONTEND_BASE_URL must not
    store failed rows under the reminder dedupe keys — those would block
    the real reminder forever once email is configured."""
    from app.core.config import settings

    tenant_id = _workspace_on_trial(datetime.now(timezone.utc) + timedelta(days=1))
    provider = _FakeProvider()
    try:
        for key, value in (("resend_api_key", None), ("frontend_base_url", "http://localhost:3000")):
            monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
            monkeypatch.setattr(settings, "frontend_base_url", "https://app.geocore.test")
            monkeypatch.setattr(settings, key, value)
            db = SessionLocal()
            try:
                result = TrialReminderService(delivery=DeliveryService(provider=provider)).run(db)
            finally:
                db.close()
            assert result.skipped_email_unconfigured is True
        assert _reminder_types(tenant_id) == []
        assert provider.sent == []
    finally:
        _cleanup_tenant(tenant_id)


class _FlakyProvider(_FakeProvider):
    def __init__(self):
        super().__init__()
        self.fail = True

    def send(self, message):
        if self.fail:
            return SendResult(outcome=SendOutcome.TRANSIENT_FAILURE, detail="provider timeout")
        return super().send(message)


def test_a_failed_reminder_is_retried_not_treated_as_sent():
    tenant_id = _workspace_on_trial(datetime.now(timezone.utc) + timedelta(days=2))
    provider = _FlakyProvider()
    service = TrialReminderService(delivery=DeliveryService(provider=provider))
    try:
        db = SessionLocal()
        try:
            service.run(db)
        finally:
            db.close()
        assert provider.sent == []  # first attempt failed
        provider.fail = False
        db = SessionLocal()
        try:
            result = service.run(db)
        finally:
            db.close()
        assert result.retried == 1
        assert [m.subject for m in provider.sent] == ["Your GeoCore free trial ends in 2 days"]
        db = SessionLocal()
        try:
            rows = db.query(Communication).filter(Communication.tenant_id == tenant_id).all()
            assert len(rows) == 1 and rows[0].status != "failed"  # same row, never a second one
        finally:
            db.close()
    finally:
        _cleanup_tenant(tenant_id)
