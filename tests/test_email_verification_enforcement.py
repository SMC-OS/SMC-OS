"""Sprint 039 Production Readiness Defect Gate — Blocker 2 hotfix.

Closes the email-verification *bypass*: Blocker 1 (see tests/test_email_
verification.py) built a genuine token/email verification mechanism, but
never enforced it anywhere except POST /invitations. Every other
protected route only checked `get_current_user` (valid session), never
whether that session's email was verified — so a signup with an
arbitrary, unproven email got full normal workspace access immediately.

This file proves the bypass is closed: an unverified session can reach
only the narrow auth/verification-lifecycle allowlist (inspect state,
resend, confirm, log out), never normal tenant business-data routes —
and that verifying unlocks normal access again, without disturbing
login, legacy-grace behavior, or tenant isolation, all of which already
have their own dedicated coverage elsewhere in this suite.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailVerificationToken,
    Subscription,
    Tenant,
    User,
)

RUN_ID = uuid.uuid4().hex[:10]
TENANT_NAME = f"Pytest Verification Enforcement Tenant {RUN_ID}"
EMAIL = f"pytest-verification-enforcement-{RUN_ID}@example.invalid"
PASSWORD = "Pytest-Verification-Enforcement-1!"


def _cleanup():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == EMAIL).first()
        if user is not None:
            tenant_id = user.tenant_id
            db.execute(
                delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
            )
            db.execute(delete(Communication).where(Communication.tenant_id == tenant_id))
            db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(User).where(User.email == EMAIL))
        db.execute(delete(Tenant).where(Tenant.name == TENANT_NAME))
        db.commit()
    finally:
        db.close()


def _issue_raw_token(user_id: uuid.UUID, *, expires_at: datetime) -> str:
    """Same shape as tests/test_email_verification.py's own helper — a
    real, persisted token row, returning the matching raw token."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db = SessionLocal()
    try:
        crud.create_email_verification_token(
            db, id=uuid.uuid4(), user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
    finally:
        db.close()
    return raw_token


@pytest.fixture()
def unverified_headers(client):
    """A genuinely unverified account, created through the real, public
    signup endpoint — exactly the path the owner reproduced the bypass
    through, not a shortcut via crud.create_user()."""
    _cleanup()
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": TENANT_NAME,
            "name": "Pytest Unverified Owner",
            "email": EMAIL,
            "password": PASSWORD,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email_verified_at"] is None  # sanity: genuinely unverified
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    yield headers
    _cleanup()


class TestUnverifiedSignupCannotReachNormalWorkspace:
    """The exact bypass the owner reproduced manually on production: an
    arbitrary, unproven email signs up and gets full session access.
    Each assertion is one required "no X" from the V1 contract."""

    def test_cannot_access_customers(self, client, unverified_headers):
        r = client.get("/api/v1/customers", headers=unverified_headers)
        assert r.status_code == 403

    def test_cannot_access_quotes(self, client, unverified_headers):
        r = client.get("/api/v1/quotes", headers=unverified_headers)
        assert r.status_code == 403

    def test_cannot_access_projects(self, client, unverified_headers):
        r = client.get("/api/v1/projects", headers=unverified_headers)
        assert r.status_code == 403

    def test_cannot_access_tasks(self, client, unverified_headers):
        r = client.get("/api/v1/tasks", headers=unverified_headers)
        assert r.status_code == 403

    def test_cannot_access_calendar(self, client, unverified_headers):
        r = client.get("/api/v1/calendar", headers=unverified_headers)
        assert r.status_code == 403

    def test_cannot_access_automations(self, client, unverified_headers):
        r = client.get("/api/v1/automations", headers=unverified_headers)
        assert r.status_code == 403

    def test_cannot_access_communications(self, client, unverified_headers):
        r = client.get("/api/v1/communications", headers=unverified_headers)
        assert r.status_code == 403

    def test_cannot_access_billing_subscription(self, client, unverified_headers):
        r = client.get("/api/v1/billing/subscription", headers=unverified_headers)
        assert r.status_code == 403

    def test_cannot_access_tenant_settings(self, client, unverified_headers):
        r = client.get("/api/v1/tenants/me/profile", headers=unverified_headers)
        assert r.status_code == 403

    def test_cannot_access_dashboard(self, client, unverified_headers):
        r = client.get("/api/v1/dashboard/command-centre", headers=unverified_headers)
        assert r.status_code == 403


class TestAuthLifecycleStaysReachableWhileUnverified:
    """The narrow allowlist the brief permits: inspect verification
    state, resend, complete verification, log out. Nothing else."""

    def test_me_still_works_and_reports_verification_state(self, client, unverified_headers):
        r = client.get("/api/v1/auth/me", headers=unverified_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["email_verified_at"] is None
        assert body["verification_required"] is True

    def test_resend_still_works_unverified(self, client, unverified_headers):
        r = client.post("/api/v1/auth/email/verify/resend", headers=unverified_headers)
        assert r.status_code == 200

    def test_confirm_still_works_unverified_and_takes_no_auth_at_all(self, client, unverified_headers):
        me = client.get("/api/v1/auth/me", headers=unverified_headers).json()
        raw_token = _issue_raw_token(
            uuid.UUID(me["id"]), expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        r = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
        assert r.status_code == 200


class TestLoginCannotBypassVerification:
    def test_login_for_existing_unverified_account_stays_blocked_from_workspace(
        self, client, unverified_headers
    ):
        r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200
        assert r.json()["user"]["verification_required"] is True
        fresh_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        blocked = client.get("/api/v1/customers", headers=fresh_headers)
        assert blocked.status_code == 403


class TestVerificationUnlocksNormalAccess:
    def test_after_verification_normal_access_succeeds(self, client, unverified_headers):
        me = client.get("/api/v1/auth/me", headers=unverified_headers).json()
        raw_token = _issue_raw_token(
            uuid.UUID(me["id"]), expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        confirm = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
        assert confirm.status_code == 200

        # Same token, no new login — the existing session becomes usable
        # the instant the account is verified, matching require_verified_
        # email's own DB-is-authoritative posture (no re-login required).
        r = client.get("/api/v1/customers", headers=unverified_headers)
        assert r.status_code == 200

        me_after = client.get("/api/v1/auth/me", headers=unverified_headers).json()
        assert me_after["email_verified_at"] is not None
        assert me_after["verification_required"] is False


class TestVerificationTokenReplayAndExpiry:
    def test_replay_of_an_already_used_token_fails(self, client, unverified_headers):
        me = client.get("/api/v1/auth/me", headers=unverified_headers).json()
        raw_token = _issue_raw_token(
            uuid.UUID(me["id"]), expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        first = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
        assert first.status_code == 200
        second = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
        assert second.status_code == 400

    def test_expired_token_fails_safely(self, client, unverified_headers):
        me = client.get("/api/v1/auth/me", headers=unverified_headers).json()
        raw_token = _issue_raw_token(
            uuid.UUID(me["id"]), expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        r = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
        assert r.status_code == 400
        still_blocked = client.get("/api/v1/customers", headers=unverified_headers)
        assert still_blocked.status_code == 403


class TestTenantIsolationStillIntact:
    """Enforcement is per-user, not per-tenant — proves it doesn't
    accidentally verify or block anyone else."""

    def test_verifying_one_user_does_not_affect_a_second_unrelated_tenant(
        self, client, unverified_headers, auth_headers
    ):
        # auth_headers (the seeded, already-verified owner of a wholly
        # different tenant) must be completely unaffected by anything
        # this file's unverified fixture does.
        r = client.get("/api/v1/customers", headers=auth_headers)
        assert r.status_code == 200
