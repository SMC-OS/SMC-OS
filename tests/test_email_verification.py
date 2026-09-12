"""Sprint 039 Production Readiness Defect Gate, Blocker 1 —
docs/SPRINTS/sprint-039.md. Covers the full lifecycle through the HTTP
layer: signup creates a token, resend/confirm work, tokens are single-use
and expiring, no live email provider is required (Resend is unconfigured
in CI, same as every other communications test — DeliveryService's own
"ships dark" contract), and require_verified_email's legacy-grace logic.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.auth.dependencies import require_verified_email
from app.auth.service import auth_service
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
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

TENANT_NAME = "Pytest Email Verification Tenant"
USER_EMAIL = "pytest-email-verification-user@example.invalid"
SIGNUP_EMAIL = "pytest-email-verification-signup@example.invalid"
SIGNUP_COMPANY = "Pytest Email Verification Signup Co"
INVITEE_EMAIL = "pytest-invitee-blocked@example.invalid"
PASSWORD = "correct-horse-battery-staple"


def _cleanup():
    db = SessionLocal()
    try:
        emails = [USER_EMAIL, SIGNUP_EMAIL]
        user_ids = [u.id for u in db.query(User).filter(User.email.in_(emails)).all()]
        if user_ids:
            db.execute(
                delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(user_ids))
            )
            db.execute(delete(Invitation).where(Invitation.invited_by_user_id.in_(user_ids)))
        db.execute(delete(Invitation).where(Invitation.email == INVITEE_EMAIL))
        db.execute(delete(User).where(User.email.in_(emails)))
        for name in (TENANT_NAME, SIGNUP_COMPANY):
            tenant = db.query(Tenant).filter(Tenant.name == name).first()
            if tenant is not None:
                db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
                # Sprint 038: signup now attempts a verification-email send,
                # which writes a Communication row (tenant_id NOT NULL, no
                # ondelete) — same "delete before the Tenant row"
                # requirement every other test file's cleanup follows.
                db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
                # Sprint 039 Blocker 3 merged after this test was first
                # written — a real signup now also starts a real trial
                # Subscription row (tenant_id FK, no ondelete), same
                # "delete before the Tenant row" requirement.
                db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
        db.execute(delete(Tenant).where(Tenant.name.in_([TENANT_NAME, SIGNUP_COMPANY])))
        db.commit()
    finally:
        db.close()


def _issue_raw_token(user_id: uuid.UUID, *, expires_at: datetime) -> str:
    """Creates a real, persisted token row and returns the matching raw
    token — the same shape EmailVerificationService.send_verification_email
    produces, without needing a live email provider to recover it from."""
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
def user_and_headers(client):
    """A freshly-created (unverified) user, logged in — same
    directly-via-crud shape as tests/test_invitations.py's owner_and_staff,
    so this fixture is deliberately NOT verified (that's what's under
    test)."""
    _cleanup()
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=TENANT_NAME))
        user = auth_service.create_user(
            db,
            tenant_id=tenant.id,
            name="Pytest User",
            email=USER_EMAIL,
            password=PASSWORD,
            role="Owner",
            email_verified=False,
        )
    finally:
        db.close()
    r = client.post("/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    yield user, headers
    _cleanup()


def test_signup_creates_a_verification_token(client):
    _cleanup()
    try:
        r = client.post(
            "/api/v1/auth/signup",
            json={
                "company_name": SIGNUP_COMPANY,
                "name": "Pytest Owner",
                "email": SIGNUP_EMAIL,
                "password": PASSWORD,
            },
        )
        assert r.status_code == 201
        assert r.json()["user"]["email_verified_at"] is None

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == SIGNUP_EMAIL).first()
            token_row = (
                db.query(EmailVerificationToken)
                .filter(EmailVerificationToken.user_id == user.id)
                .first()
            )
            assert token_row is not None
            assert token_row.used_at is None
            assert token_row.expires_at > datetime.now(timezone.utc)
        finally:
            db.close()
    finally:
        _cleanup()


def test_me_reflects_unverified_state(client, user_and_headers):
    _, headers = user_and_headers
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email_verified_at"] is None


def test_confirm_with_valid_token_verifies_the_user(client, user_and_headers):
    user, _ = user_and_headers
    raw_token = _issue_raw_token(user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    r = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
    assert r.status_code == 200

    db = SessionLocal()
    try:
        refreshed = db.query(User).filter(User.id == user.id).first()
        assert refreshed.email_verified_at is not None
    finally:
        db.close()


def test_confirm_with_unknown_token_is_400(client):
    r = client.post("/api/v1/auth/email/verify/confirm", json={"token": "not-a-real-token"})
    assert r.status_code == 400


def test_confirm_is_single_use(client, user_and_headers):
    user, _ = user_and_headers
    raw_token = _issue_raw_token(user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    first = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
    assert second.status_code == 400


def test_expired_token_is_rejected(client, user_and_headers):
    user, _ = user_and_headers
    raw_token = _issue_raw_token(user.id, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))

    r = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
    assert r.status_code == 400


def test_resend_requires_auth(client):
    r = client.post("/api/v1/auth/email/verify/resend")
    assert r.status_code == 401


def test_resend_creates_a_new_token(client, user_and_headers):
    _, headers = user_and_headers
    r = client.post("/api/v1/auth/email/verify/resend", headers=headers)
    assert r.status_code == 200


def test_resend_is_rate_limited(client, user_and_headers):
    _, headers = user_and_headers
    first = client.post("/api/v1/auth/email/verify/resend", headers=headers)
    assert first.status_code == 200
    second = client.post("/api/v1/auth/email/verify/resend", headers=headers)
    assert second.status_code == 429


def test_resend_when_already_verified_is_a_no_op(client, user_and_headers):
    user, headers = user_and_headers
    db = SessionLocal()
    try:
        crud.set_user_email_verified_at(db, user.id, datetime.now(timezone.utc))
    finally:
        db.close()

    r = client.post("/api/v1/auth/email/verify/resend", headers=headers)
    assert r.status_code == 200
    assert "already verified" in r.json()["message"].lower()


def test_require_verified_email_blocks_new_unverified_user(user_and_headers):
    user, _ = user_and_headers
    with pytest.raises(Exception) as exc_info:
        require_verified_email(current_user=user)
    assert getattr(exc_info.value, "status_code", None) == 403


def test_require_verified_email_allows_a_verified_user(user_and_headers):
    user, _ = user_and_headers
    db = SessionLocal()
    try:
        crud.set_user_email_verified_at(db, user.id, datetime.now(timezone.utc))
        refreshed = db.query(User).filter(User.id == user.id).first()
        result = require_verified_email(current_user=refreshed)
        assert result.id == user.id
    finally:
        db.close()


def _backdate_created_at(user_id: uuid.UUID, days_ago: int) -> datetime:
    new_created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db = SessionLocal()
    try:
        db.execute(
            User.__table__.update().where(User.id == user_id).values(created_at=new_created_at)
        )
        db.commit()
    finally:
        db.close()
    return new_created_at


def test_require_verified_email_exempts_legacy_users_within_grace_period(user_and_headers, monkeypatch):
    user, _ = user_and_headers
    # A real legacy user: created well before the cutover, with the
    # grace window (from that fixed cutover instant) still open today.
    _backdate_created_at(user.id, days_ago=60)
    monkeypatch.setattr(
        settings, "identity_security_cutover_at", datetime.now(timezone.utc) - timedelta(days=5)
    )
    monkeypatch.setattr(settings, "legacy_verification_grace_days", 30)

    db = SessionLocal()
    try:
        refreshed = db.query(User).filter(User.id == user.id).first()
        result = require_verified_email(current_user=refreshed)
        assert result.id == user.id
    finally:
        db.close()


def test_require_verified_email_blocks_legacy_users_after_grace_period_ends(user_and_headers, monkeypatch):
    user, _ = user_and_headers
    _backdate_created_at(user.id, days_ago=60)
    monkeypatch.setattr(
        settings, "identity_security_cutover_at", datetime.now(timezone.utc) - timedelta(days=30)
    )
    monkeypatch.setattr(settings, "legacy_verification_grace_days", 30)

    db = SessionLocal()
    try:
        refreshed = db.query(User).filter(User.id == user.id).first()
        with pytest.raises(Exception) as exc_info:
            require_verified_email(current_user=refreshed)
        assert getattr(exc_info.value, "status_code", None) == 403
    finally:
        db.close()


def test_invitation_creation_blocked_for_unverified_owner(client, user_and_headers):
    _, headers = user_and_headers
    r = client.post(
        "/api/v1/invitations",
        json={"email": INVITEE_EMAIL},
        headers=headers,
    )
    assert r.status_code == 403
