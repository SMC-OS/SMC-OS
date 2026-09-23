"""Phase B verification — trial/payment lifecycle, Stripe contract
simulation and server-side security.

Stripe itself cannot be reached from CI, so these tests replay the exact
event sequences Stripe sends (checkout.session.completed and
customer.subscription.created/updated, in and out of order, late, or not
at all) through the real, signature-verified webhook endpoint, and assert
the exact Checkout parameters GeoCore sends. What Stripe then does with
those parameters (collecting a card, starting its own trial that ends at
`trial_end`, charging at that moment) is Stripe's documented behaviour and
is verified on staging by scripts/staging/verify_trial_billing.py.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, update

from app.auth.dependencies import has_active_billing_access
from app.auth.service import auth_service
from app.billing.service import billing_service
from app.billing.trial import trial_status
from app.billing.trial_reminders import TrialReminderService
from app.communications.provider import SendOutcome, SendResult
from app.communications.service import DeliveryService
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailVerificationToken,
    Invitation,
    Subscription,
    Tenant,
    User,
)

RUN = uuid.uuid4().hex[:8]
PASSWORD = "Trial-Lifecycle-Password-1!"
PRICES = {
    "stripe_price_starter_monthly": "price_t_starter_m",
    "stripe_price_starter_annual": "price_t_starter_a",
    "stripe_price_business_monthly": "price_t_business_m",
    "stripe_price_business_annual": "price_t_business_a",
}


# --- Harness ------------------------------------------------------------------------


@pytest.fixture()
def stripe(monkeypatch):
    """A fake Stripe module: records Checkout calls and lets a test
    deliver any webhook event through the real endpoint."""
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_fake")
    for name, value in PRICES.items():
        monkeypatch.setattr(settings, name, value)
    fake = MagicMock()
    fake.checkout.Session.create.return_value = MagicMock(url="https://checkout.stripe.com/c/pay/cs_test")
    billing_service._stripe = fake
    yield fake
    billing_service._stripe = None


def deliver(client, stripe, event_type: str, obj: dict) -> None:
    event = {"id": f"evt_{uuid.uuid4().hex}", "type": event_type, "data": {"object": obj}}
    stripe.Webhook.construct_event.return_value = event
    r = client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    assert r.status_code == 200, r.text


def checkout(client, stripe, headers, plan: str, period: str) -> dict:
    r = client.post("/api/v1/billing/checkout", json={"plan": plan, "billing_period": period}, headers=headers)
    assert r.status_code == 200, r.text
    return stripe.checkout.Session.create.call_args.kwargs


def sub_obj(tenant_id, *, sub_id, status, price, trial_start=None, trial_end=None, plan="business", period="annual"):
    return {
        "id": sub_id,
        "customer": f"cus_{sub_id}",
        "status": status,
        "items": {"data": [{"price": {"id": price}}]},
        "current_period_end": int((trial_end or datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
        "trial_start": int(trial_start.timestamp()) if trial_start else None,
        "trial_end": int(trial_end.timestamp()) if trial_end else None,
        "metadata": {"tenant_id": str(tenant_id), "plan": plan, "billing_period": period},
    }


def session_obj(tenant_id, *, sub_id, plan="business", period="annual"):
    return {
        "customer": f"cus_{sub_id}",
        "subscription": sub_id,
        "client_reference_id": str(tenant_id),
        "metadata": {"tenant_id": str(tenant_id), "plan": plan, "billing_period": period},
    }


class Workspace:
    def __init__(self, client, label, plan="starter", period="monthly"):
        self.client = client
        self.email = f"lifecycle-{RUN}-{label}-{uuid.uuid4().hex[:6]}@example.invalid"
        self.company = f"Lifecycle {RUN} {label} {uuid.uuid4().hex[:4]}"
        r = client.post(
            "/api/v1/auth/signup",
            json={
                "company_name": self.company,
                "name": "Lifecycle Owner",
                "email": self.email,
                "password": PASSWORD,
                "plan": plan,
                "billing_period": period,
            },
        )
        assert r.status_code == 201, r.text
        self.tenant_id = uuid.UUID(r.json()["user"]["tenant_id"])
        db = SessionLocal()
        try:
            db.execute(update(User).where(User.email == self.email).values(email_verified_at=datetime.now(timezone.utc)))
            db.commit()
        finally:
            db.close()
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    def sub(self) -> Subscription:
        db = SessionLocal()
        try:
            row = crud.get_subscription_by_tenant_id(db, self.tenant_id)
            db.expunge(row)
            return row
        finally:
            db.close()

    def shift_trial(self, *, days_elapsed: float):
        """Moves the trial window so `days_elapsed` days have passed."""
        now = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            row = crud.get_subscription_by_tenant_id(db, self.tenant_id)
            row.trial_start = now - timedelta(days=days_elapsed)
            row.trial_end = row.trial_start + timedelta(days=14)
            db.commit()
        finally:
            db.close()

    def can_use_app(self) -> bool:
        return self.client.get("/api/v1/customers", headers=self.headers).status_code == 200

    def cleanup(self):
        db = SessionLocal()
        try:
            ids = [u.id for u in db.query(User).filter(User.tenant_id == self.tenant_id)]
            if ids:
                db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(ids)))
            for model in (Invitation, Communication, Subscription, ActivityLog, User):
                db.execute(delete(model).where(model.tenant_id == self.tenant_id))
            db.execute(delete(Tenant).where(Tenant.id == self.tenant_id))
            db.commit()
        finally:
            db.close()


@pytest.fixture()
def workspaces(client):
    made: list[Workspace] = []

    def make(label, **kwargs):
        ws = Workspace(client, label, **kwargs)
        made.append(ws)
        return ws

    yield make
    for ws in made:
        ws.cleanup()


# --- A. The full timeline, simulated end to end --------------------------------------


def test_timeline_signup_trial_subscribe_mid_trial_then_first_charge(client, stripe, workspaces):
    ws = workspaces("timeline", plan="starter", period="monthly")

    # Day 0: signup starts the trial with no Stripe call at all.
    stripe.checkout.Session.create.assert_not_called()
    sub = ws.sub()
    assert (sub.status, sub.plan, sub.stripe_customer_id, sub.stripe_subscription_id) == (
        "trialing", "starter", None, None,
    )
    original_start, original_end = sub.trial_start, sub.trial_end
    assert original_end - original_start == timedelta(days=14)

    # Day 1: straight into the app.
    ws.shift_trial(days_elapsed=1)
    assert ws.can_use_app()
    sub = ws.sub()
    original_start, original_end = sub.trial_start, sub.trial_end

    # Day 5: chooses Business annual. Checkout collects a card (Stripe's
    # default in subscription mode) and gets the REMAINING trial only.
    ws.shift_trial(days_elapsed=5)
    sub = ws.sub()
    original_start, original_end = sub.trial_start, sub.trial_end
    params = checkout(client, stripe, ws.headers, "business", "annual")
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": "price_t_business_a", "quantity": 1}]
    assert "payment_method_collection" not in params  # default "always": the card is collected here
    assert "trial_period_days" not in params["subscription_data"]  # never a second 14-day trial
    assert "trial_from_plan" not in params["subscription_data"]  # never a price-level trial either
    assert params["subscription_data"]["trial_end"] == int(original_end.timestamp())

    # Stripe completes Checkout: its subscription trials until that same trial_end.
    stripe_sub = sub_obj(
        ws.tenant_id, sub_id=f"sub_tl_{RUN}", status="trialing", price="price_t_business_a",
        trial_start=datetime.now(timezone.utc), trial_end=original_end,
    )
    deliver(client, stripe, "checkout.session.completed", session_obj(ws.tenant_id, sub_id=f"sub_tl_{RUN}"))
    deliver(client, stripe, "customer.subscription.created", stripe_sub)

    sub = ws.sub()
    assert (sub.plan, sub.billing_period, sub.status) == ("business", "annual", "trialing")
    assert sub.stripe_subscription_id == f"sub_tl_{RUN}"
    assert int(sub.trial_end.timestamp()) == int(original_end.timestamp())  # remaining days preserved
    assert sub.trial_start == original_start  # when the free trial really began
    assert ws.can_use_app()
    # Now Stripe-managed: GeoCore neither expires nor reminds it.
    assert trial_status(sub) is None

    # Trial end: Stripe takes the first payment and moves it to active.
    deliver(client, stripe, "customer.subscription.updated", {**stripe_sub, "status": "active"})
    assert ws.sub().status == "active"
    assert ws.can_use_app()
    # A paying customer can never start another trial.
    assert client.post("/api/v1/billing/trial", headers=ws.headers).status_code == 409


def test_webhooks_out_of_order_reach_the_same_final_state(client, stripe, workspaces):
    ws = workspaces("out-of-order")
    original_end = ws.sub().trial_end
    checkout(client, stripe, ws.headers, "starter", "monthly")
    stripe_sub = sub_obj(
        ws.tenant_id, sub_id=f"sub_ooo_{RUN}", status="trialing", price="price_t_starter_m",
        trial_start=datetime.now(timezone.utc), trial_end=original_end, plan="starter", period="monthly",
    )
    # subscription.created arrives BEFORE checkout.session.completed.
    deliver(client, stripe, "customer.subscription.created", stripe_sub)
    deliver(client, stripe, "checkout.session.completed", session_obj(
        ws.tenant_id, sub_id=f"sub_ooo_{RUN}", plan="starter", period="monthly"
    ))
    sub = ws.sub()
    assert (sub.status, sub.plan, sub.stripe_subscription_id) == ("trialing", "starter", f"sub_ooo_{RUN}")
    assert int(sub.trial_end.timestamp()) == int(original_end.timestamp())
    assert ws.can_use_app()


def test_replayed_webhooks_are_ignored(client, stripe, workspaces):
    ws = workspaces("replay")
    stripe_sub = sub_obj(ws.tenant_id, sub_id=f"sub_rep_{RUN}", status="active", price="price_t_starter_m",
                         plan="starter", period="monthly")
    event = {"id": f"evt_replay_{RUN}", "type": "customer.subscription.created", "data": {"object": stripe_sub}}
    stripe.Webhook.construct_event.return_value = event
    for _ in range(2):
        assert client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "s"}).status_code == 200
    # A later, stale replay of the same event id cannot roll status back.
    deliver(client, stripe, "customer.subscription.updated", {**stripe_sub, "status": "past_due"})
    stripe.Webhook.construct_event.return_value = event
    client.post("/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "s"})
    assert ws.sub().status == "past_due"


def test_abandoned_checkout_changes_nothing_and_can_be_retried(client, stripe, workspaces):
    ws = workspaces("abandoned")
    before = ws.sub()
    first = checkout(client, stripe, ws.headers, "starter", "monthly")
    # No webhook ever arrives.
    after = ws.sub()
    assert (after.status, after.stripe_subscription_id, after.trial_end) == ("trialing", None, before.trial_end)
    assert ws.can_use_app()
    retry = checkout(client, stripe, ws.headers, "starter", "annual")
    assert retry["subscription_data"]["trial_end"] == first["subscription_data"]["trial_end"]
    # Expiry is still enforced for an abandoned checkout.
    ws.shift_trial(days_elapsed=15)
    assert not ws.can_use_app()


def test_checkout_completed_after_trial_expiry_charges_immediately_and_restores_access(client, stripe, workspaces):
    ws = workspaces("after-expiry")
    ws.shift_trial(days_elapsed=16)
    expired = ws.sub()
    assert not ws.can_use_app()

    params = checkout(client, stripe, ws.headers, "business", "monthly")
    assert "trial_end" not in params["subscription_data"]
    assert "trial_period_days" not in params["subscription_data"]

    deliver(client, stripe, "checkout.session.completed", session_obj(
        ws.tenant_id, sub_id=f"sub_ae_{RUN}", plan="business", period="monthly"
    ))
    deliver(client, stripe, "customer.subscription.created", sub_obj(
        ws.tenant_id, sub_id=f"sub_ae_{RUN}", status="active", price="price_t_business_m",
        plan="business", period="monthly",
    ))
    sub = ws.sub()
    assert (sub.status, sub.plan) == ("active", "business")
    assert sub.trial_start == expired.trial_start and sub.trial_end == expired.trial_end  # history kept
    assert ws.can_use_app()


def test_a_late_webhook_never_locks_out_a_workspace_that_already_paid(client, stripe, workspaces):
    """Checkout completes just before the trial ends, but Stripe's
    subscription event is delayed past trial_end: once
    checkout.session.completed has linked the Stripe subscription, GeoCore
    stops treating it as an app-run trial, so access continues."""
    ws = workspaces("late-webhook")
    checkout(client, stripe, ws.headers, "starter", "monthly")
    deliver(client, stripe, "checkout.session.completed", session_obj(
        ws.tenant_id, sub_id=f"sub_late_{RUN}", plan="starter", period="monthly"
    ))
    ws.shift_trial(days_elapsed=14.5)  # trial_end passes before the subscription event arrives
    assert ws.can_use_app()


def test_payment_failure_after_trial_blocks_access_and_never_restarts_a_trial(client, stripe, workspaces):
    ws = workspaces("past-due")
    stripe_sub = sub_obj(ws.tenant_id, sub_id=f"sub_pd_{RUN}", status="trialing", price="price_t_starter_m",
                         trial_end=ws.sub().trial_end, plan="starter", period="monthly")
    deliver(client, stripe, "customer.subscription.created", stripe_sub)
    deliver(client, stripe, "invoice.payment_failed", {"subscription": f"sub_pd_{RUN}"})
    assert ws.sub().status == "past_due"
    assert not ws.can_use_app()
    assert client.post("/api/v1/billing/trial", headers=ws.headers).status_code == 409
    deliver(client, stripe, "customer.subscription.deleted", {"id": f"sub_pd_{RUN}"})
    assert ws.sub().status == "cancelled"
    assert client.post("/api/v1/billing/trial", headers=ws.headers).status_code == 409
    assert not ws.can_use_app()


@pytest.fixture(autouse=True)
def _email_configured(monkeypatch):
    """Reminders only run where email can really be sent (see
    TrialReminderService.run); tests configure it explicitly."""
    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(_settings, "frontend_base_url", "https://app.geocore.test")


# --- E. Boundaries and edge cases ---------------------------------------------------------


def test_exact_trial_end_boundary_and_timezones():
    end = datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)  # the night UK clocks go back
    sub = Subscription(plan="pro", billing_period="monthly", status="trialing", stripe_subscription_id=None,
                       trial_start=end - timedelta(days=14), trial_end=end, legacy_grandfathered=False)
    assert trial_status(sub, end - timedelta(microseconds=1)).state == "ending_soon"
    assert trial_status(sub, end).state == "expired"  # expires AT trial_end, not a moment later
    # The same instant expressed in UK local time gives the same answer.
    london = end.astimezone(ZoneInfo("Europe/London"))
    assert trial_status(sub, london).state == "expired"
    assert trial_status(sub, london - timedelta(seconds=1)).state == "ending_soon"


def test_http_access_flips_exactly_at_trial_end(client, workspaces):
    ws = workspaces("boundary")
    db = SessionLocal()
    try:
        row = crud.get_subscription_by_tenant_id(db, ws.tenant_id)
        row.trial_end = datetime.now(timezone.utc) + timedelta(seconds=30)
        db.commit()
    finally:
        db.close()
    assert ws.can_use_app()
    db = SessionLocal()
    try:
        row = crud.get_subscription_by_tenant_id(db, ws.tenant_id)
        row.trial_end = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        assert has_active_billing_access(row) is False
    finally:
        db.close()
    assert not ws.can_use_app()


class _Provider:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        return SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id=f"m{len(self.sent)}")


def test_multiple_owners_get_one_reminder_each_never_duplicates(workspaces):
    ws = workspaces("two-owners")
    db = SessionLocal()
    try:
        second = auth_service.create_user(db, tenant_id=ws.tenant_id, name="Second Owner",
                                          email=f"second-{uuid.uuid4().hex[:8]}@example.invalid",
                                          password=PASSWORD, role="Owner", grant_legacy_billing_access=False)
        auth_service.create_user(db, tenant_id=ws.tenant_id, name="A Staff",
                                 email=f"staff-{uuid.uuid4().hex[:8]}@example.invalid",
                                 password=PASSWORD, role="Staff", grant_legacy_billing_access=False)
        second_email = second.email
    finally:
        db.close()
    ws.shift_trial(days_elapsed=12)
    provider = _Provider()
    service = TrialReminderService(delivery=DeliveryService(provider=provider))
    for _ in range(3):
        db = SessionLocal()
        try:
            service.run(db)
        finally:
            db.close()
    recipients = sorted(m.recipient for m in provider.sent)
    assert recipients == sorted([ws.email.lower(), second_email.lower()])  # one each, Staff excluded


def test_trial_plan_limits_are_enforced_server_side(client, workspaces):
    """plan=starter chosen at signup means Starter entitlements (1 seat)
    for the trial, enforced by the API regardless of what the UI shows."""
    ws = workspaces("seat-limit", plan="starter")
    r = client.post("/api/v1/invitations", json={"email": f"x-{RUN}@example.invalid"}, headers=ws.headers)
    assert r.status_code == 402
    assert "Seat limit (1)" in r.json()["detail"]


def test_deleting_and_recreating_users_never_restarts_the_trial(client, workspaces):
    ws = workspaces("recreate")
    ws.shift_trial(days_elapsed=13)
    original_end = ws.sub().trial_end
    db = SessionLocal()
    try:
        ids = [u.id for u in db.query(User).filter(User.tenant_id == ws.tenant_id)]
        db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(ids)))
        db.execute(delete(User).where(User.tenant_id == ws.tenant_id))
        db.commit()
        new_email = f"recreated-{uuid.uuid4().hex[:8]}@example.invalid"
        auth_service.create_user(db, tenant_id=ws.tenant_id, name="Recreated Owner", email=new_email,
                                 password=PASSWORD, role="Owner", grant_legacy_billing_access=False)
    finally:
        db.close()
    login = client.post("/api/v1/auth/login", json={"email": new_email, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post("/api/v1/billing/trial", headers=headers).status_code == 409
    assert ws.sub().trial_end == original_end


def test_ownership_transfer_never_restarts_the_trial(client, workspaces):
    ws = workspaces("transfer")
    ws.shift_trial(days_elapsed=10)
    original = ws.sub()
    db = SessionLocal()
    try:
        heir_email = f"heir-{uuid.uuid4().hex[:8]}@example.invalid"
        auth_service.create_user(db, tenant_id=ws.tenant_id, name="Heir", email=heir_email,
                                 password=PASSWORD, role="Staff", grant_legacy_billing_access=False)
        db.execute(update(User).where(User.email == ws.email).values(role="Staff"))
        db.execute(update(User).where(User.email == heir_email).values(role="Owner"))
        db.commit()
    finally:
        db.close()
    login = client.post("/api/v1/auth/login", json={"email": heir_email, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post("/api/v1/billing/trial", headers=headers).status_code == 409
    after = ws.sub()
    assert (after.trial_start, after.trial_end, after.plan) == (original.trial_start, original.trial_end, original.plan)


# --- D. Security: the plan choice is a preference; the API is authoritative -------------


@pytest.mark.parametrize("plan", ["enterprise", "platinum", "", None])
def test_signup_cannot_obtain_a_non_self_service_plan(client, workspaces, plan):
    ws = workspaces(f"tamper-{plan}", plan=plan)
    assert ws.sub().plan == "pro"


def test_checkout_cannot_select_enterprise_or_a_client_price(client, stripe, workspaces):
    ws = workspaces("tamper-checkout")
    r = client.post("/api/v1/billing/checkout", json={"plan": "enterprise", "billing_period": "monthly"},
                    headers=ws.headers)
    assert r.status_code == 422
    params = checkout(client, stripe, ws.headers, "starter", "monthly")
    assert params["line_items"][0]["price"] == "price_t_starter_m"  # from server config, never the client


def test_entitlements_follow_the_price_actually_paid(client, stripe, workspaces):
    """Even if a Checkout's metadata claimed Business, a subscription on
    the Starter price resolves to Starter: the price id is authoritative."""
    ws = workspaces("paid-price", plan="business")
    deliver(client, stripe, "customer.subscription.created", sub_obj(
        ws.tenant_id, sub_id=f"sub_pp_{RUN}", status="active", price="price_t_starter_m",
        plan="business", period="annual",
    ))
    assert (ws.sub().plan, ws.sub().billing_period) == ("starter", "monthly")


def test_a_trial_workspace_cannot_switch_its_trial_plan_via_the_trial_endpoint(client, workspaces):
    ws = workspaces("switch", plan="starter")
    r = client.post("/api/v1/billing/trial", json={"plan": "business"}, headers=ws.headers)
    assert r.status_code == 409
    assert ws.sub().plan == "starter"


def test_an_unverified_trial_workspace_gets_no_access(client):
    email = f"unverified-{RUN}@example.invalid"
    company = f"Lifecycle unverified {RUN}"
    r = client.post("/api/v1/auth/signup", json={"company_name": company, "name": "U", "email": email,
                                                 "password": PASSWORD, "plan": "business"})
    try:
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert client.get("/api/v1/customers", headers=headers).status_code == 403
    finally:
        tenant_id = uuid.UUID(r.json()["user"]["tenant_id"])
        db = SessionLocal()
        try:
            ids = [u.id for u in db.query(User).filter(User.tenant_id == tenant_id)]
            db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(ids)))
            for model in (Communication, Subscription, ActivityLog, User):
                db.execute(delete(model).where(model.tenant_id == tenant_id))
            db.execute(delete(Tenant).where(Tenant.id == tenant_id))
            db.commit()
        finally:
            db.close()
