"""GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES, Blocker B: card-required
14-day trial with a backend-enforced workspace access boundary.

Owner manual staging acceptance found a verified account could reach
normal GeoCore workspace APIs without ever completing Stripe trial/
subscription activation. Before this file's fix,
AuthService.signup() unconditionally called
app.billing.trial.start_trial_if_eligible() (Sprint 039 Blocker 3),
granting every brand-new, verified tenant an immediate, card-less
"trialing" Subscription and therefore full workspace access — no
Stripe object, no card, ever contacted.

This file proves the new contract end-to-end at the HTTP layer (direct
API calls, not a UI redirect):

- a freshly verified signup has NO Subscription row and is blocked
  (402) from normal workspace routes;
- authentication, account/session management, and billing/plan-
  selection/Checkout-initiation routes remain reachable throughout;
- only an authoritative server-side Subscription — "trialing"/"active",
  or the explicit legacy_grandfathered exemption — unlocks workspace
  access;
- cancelled/past_due/incomplete states never accidentally unlock it;
- the same boundary applies to Owner-role-gated routes (invitations,
  team management), not just plain authenticated ones.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.auth.dependencies import has_active_billing_access
from app.auth.service import auth_service
from app.billing.trial import start_trial_if_eligible
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Communication, EmailVerificationToken, Subscription, Tenant, User
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

RUN_ID = uuid.uuid4().hex[:8]
STRONG_PASSWORD = "Pytest-Gate-Strong-Password-1!"


def _unique_email(label: str) -> str:
    return f"pytest-billing-gate-{RUN_ID}-{label}@example.invalid"


def _cleanup(*, tenant_name: str, emails: list[str]) -> None:
    db = SessionLocal()
    try:
        user_ids = [u.id for u in db.query(User).filter(User.email.in_(emails)).all()]
        if user_ids:
            db.execute(
                delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(user_ids))
            )
        db.execute(delete(User).where(User.email.in_(emails)))
        tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
        if tenant is not None:
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
            db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
        db.execute(delete(Tenant).where(Tenant.name == tenant_name))
        db.commit()
    finally:
        db.close()


def _signup_and_verify(client, *, label: str) -> tuple[dict, uuid.UUID, str]:
    email = _unique_email(label)
    company = f"Pytest Billing Gate {label} Co {RUN_ID}"
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": company,
            "name": "Pytest Owner",
            "email": email,
            "password": STRONG_PASSWORD,
        },
    )
    assert r.status_code == 201
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    tenant_id = uuid.UUID(r.json()["user"]["tenant_id"])

    db = SessionLocal()
    try:
        db.query(User).filter(User.email == email).update(
            {"email_verified_at": datetime.now(timezone.utc)}
        )
        db.commit()
    finally:
        db.close()

    return headers, tenant_id, company


# ---------------------------------------------------------------------
# Unit-level: has_active_billing_access's own truth table.
# ---------------------------------------------------------------------


def test_no_subscription_has_no_access():
    assert has_active_billing_access(None) is False


def test_trialing_subscription_has_access():
    sub = Subscription(tenant_id=uuid.uuid4(), plan="pro", billing_period="monthly", status="trialing")
    assert has_active_billing_access(sub) is True


def test_active_subscription_has_access():
    sub = Subscription(tenant_id=uuid.uuid4(), plan="pro", billing_period="monthly", status="active")
    assert has_active_billing_access(sub) is True


def test_incomplete_subscription_has_no_access():
    sub = Subscription(tenant_id=uuid.uuid4(), plan="pro", billing_period="monthly", status="incomplete")
    assert has_active_billing_access(sub) is False


def test_cancelled_subscription_has_no_access():
    sub = Subscription(tenant_id=uuid.uuid4(), plan="pro", billing_period="monthly", status="cancelled")
    assert has_active_billing_access(sub) is False


def test_past_due_subscription_has_no_access():
    sub = Subscription(tenant_id=uuid.uuid4(), plan="pro", billing_period="monthly", status="past_due")
    assert has_active_billing_access(sub) is False


def test_legacy_grandfathered_has_access_regardless_of_status():
    # The explicit, permanent grace policy (migration b5c6d7e8f9a0) — an
    # existing/legacy tenant must never be locked out, whatever its status.
    sub = Subscription(
        tenant_id=uuid.uuid4(),
        plan="pro",
        billing_period="monthly",
        status="incomplete",
        legacy_grandfathered=True,
    )
    assert has_active_billing_access(sub) is True


# ---------------------------------------------------------------------
# HTTP-level: the real boundary a verified-but-unactivated user hits.
# ---------------------------------------------------------------------


def test_verified_signup_with_no_subscription_is_blocked_from_workspace_apis(client):
    headers, tenant_id, company = _signup_and_verify(client, label="workspace-block")
    try:
        db = SessionLocal()
        try:
            assert crud.get_subscription_by_tenant_id(db, tenant_id) is None
        finally:
            db.close()

        # Direct API calls, not a UI redirect — every one of these is a
        # normal workspace route a real frontend page would call.
        for method, path in [
            ("GET", "/api/v1/customers"),
            ("GET", "/api/v1/quotes"),
            ("GET", "/api/v1/projects"),
            ("GET", "/api/v1/tasks"),
            ("GET", "/api/v1/dashboard/command-centre"),
            ("GET", "/api/v1/tenants/me/onboarding"),
            ("GET", "/api/v1/activity"),
        ]:
            r = client.request(method, path, headers=headers)
            assert r.status_code == 402, f"{method} {path} returned {r.status_code}, expected 402"
    finally:
        _cleanup(tenant_name=company, emails=[_unique_email("workspace-block")])


def test_role_gated_routes_are_also_blocked_not_just_plain_authenticated_ones(client):
    """invitations/users use require_role_and_billing (no router-level
    billing baseline of their own) — a separate code path from the
    router-level require_billing_access swap every other test here
    exercises, and easy to accidentally leave ungated."""
    headers, tenant_id, company = _signup_and_verify(client, label="role-gated-block")
    try:
        assert (
            client.post(
                "/api/v1/invitations", json={"email": "irrelevant@example.invalid"}, headers=headers
            ).status_code
            == 402
        )
        assert client.get("/api/v1/invitations", headers=headers).status_code == 402
        assert client.get("/api/v1/users", headers=headers).status_code == 402
    finally:
        _cleanup(tenant_name=company, emails=[_unique_email("role-gated-block")])


def test_account_session_and_billing_routes_stay_reachable_pre_activation(client):
    headers, tenant_id, company = _signup_and_verify(client, label="allowlist")
    try:
        # Authentication / account-session management.
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
        # Plan selection is public.
        assert client.get("/api/v1/billing/plans").status_code == 200
        # Billing/trial-setup status check.
        subscription_response = client.get("/api/v1/billing/subscription", headers=headers)
        assert subscription_response.status_code == 200
        assert subscription_response.json() is None
    finally:
        _cleanup(tenant_name=company, emails=[_unique_email("allowlist")])


def test_a_real_trialing_subscription_unlocks_workspace_access(client):
    """Simulates what a real Stripe webhook does (see
    app/billing/service.py::_handle_subscription_upsert) without needing
    live Stripe — the access boundary itself is the subject here, not
    webhook parsing (covered separately in tests/test_billing.py and
    tests/test_billing_webhook_resources.py)."""
    headers, tenant_id, company = _signup_and_verify(client, label="trialing-unlock")
    try:
        db = SessionLocal()
        try:
            crud.upsert_subscription(
                db,
                tenant_id=tenant_id,
                plan="pro",
                billing_period="monthly",
                status="trialing",
                stripe_customer_id="cus_test_gate",
                stripe_subscription_id="sub_test_gate",
                trial_start=datetime.now(timezone.utc),
                trial_end=datetime.now(timezone.utc) + timedelta(days=14),
            )
        finally:
            db.close()

        assert client.get("/api/v1/customers", headers=headers).status_code == 200
    finally:
        _cleanup(tenant_name=company, emails=[_unique_email("trialing-unlock")])


def test_a_cancelled_subscription_does_not_unlock_access(client):
    headers, tenant_id, company = _signup_and_verify(client, label="cancelled-block")
    try:
        db = SessionLocal()
        try:
            crud.upsert_subscription(
                db,
                tenant_id=tenant_id,
                plan="pro",
                billing_period="monthly",
                status="cancelled",
                stripe_customer_id="cus_test_gate_cancelled",
                stripe_subscription_id="sub_test_gate_cancelled",
            )
        finally:
            db.close()

        assert client.get("/api/v1/customers", headers=headers).status_code == 402
    finally:
        _cleanup(tenant_name=company, emails=[_unique_email("cancelled-block")])


def test_a_payment_failure_does_not_unlock_access(client):
    headers, tenant_id, company = _signup_and_verify(client, label="past-due-block")
    try:
        db = SessionLocal()
        try:
            crud.upsert_subscription(
                db,
                tenant_id=tenant_id,
                plan="pro",
                billing_period="monthly",
                status="past_due",
                stripe_customer_id="cus_test_gate_pastdue",
                stripe_subscription_id="sub_test_gate_pastdue",
            )
        finally:
            db.close()

        assert client.get("/api/v1/customers", headers=headers).status_code == 402
    finally:
        _cleanup(tenant_name=company, emails=[_unique_email("past-due-block")])


# ---------------------------------------------------------------------
# Existing-tenant grace policy — a directly-created ("already
# established") user, the same construction path every other test
# fixture in this suite uses, must never be caught by this gate.
# ---------------------------------------------------------------------


def test_directly_created_user_is_auto_granted_legacy_billing_access(client):
    email = _unique_email("legacy-grace")
    company = f"Pytest Billing Gate Legacy Co {RUN_ID}"
    try:
        db = SessionLocal()
        try:
            tenant = tenant_service.create(db, TenantCreate(name=company))
            auth_service.create_user(
                db,
                tenant_id=tenant.id,
                name="Pytest Legacy Owner",
                email=email,
                password=STRONG_PASSWORD,
                role="Owner",
            )
        finally:
            db.close()

        login = client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        assert client.get("/api/v1/customers", headers=headers).status_code == 200

        db = SessionLocal()
        try:
            sub = db.query(User).filter(User.email == email).first()
            subscription = crud.get_subscription_by_tenant_id(db, sub.tenant_id)
            assert subscription is not None
            assert subscription.legacy_grandfathered is True
        finally:
            db.close()
    finally:
        _cleanup(tenant_name=company, emails=[email])


def test_signup_explicitly_opts_out_of_the_legacy_grant(client):
    """The one caller of AuthService.create_user() that must NOT get the
    legacy grant — otherwise every brand-new signup would bypass the
    entire card-required contract this file exists to prove."""
    headers, tenant_id, company = _signup_and_verify(client, label="no-legacy-grant")
    try:
        db = SessionLocal()
        try:
            assert crud.get_subscription_by_tenant_id(db, tenant_id) is None
        finally:
            db.close()
    finally:
        _cleanup(tenant_name=company, emails=[_unique_email("no-legacy-grant")])
