"""Sprint 039 Production Readiness Defect Gate, Blocker 2 —
docs/SPRINTS/sprint-039.md. Covers the full lifecycle through the HTTP
layer: forgot-password is a real no-enumeration endpoint (identical
response whether or not the account exists), a real token gets created
for a known email, reset works and is single-use and expiring, and a
reset genuinely revokes existing sessions (old JWTs stop working, a
fresh login still works). No live email provider is required (Resend is
unconfigured in CI, same as every other communications test).

Every HTTP-level test uses a freshly-generated, per-test-unique email
(via the `user_and_headers` fixture and `_unique_email()`) rather than a
shared literal — app.auth.rate_limit.password_reset_request_limiter is a
real module-level singleton with a 60s cooldown (same "in-memory,
per-process" shape as LoginRateLimiter, see that class's own docstring),
so two tests sharing one email would collide on each other's cooldown
window. CooldownLimiter's own timing behavior is unit-tested separately
below with an injected fake clock (deterministic, no real sleeps), same
convention as tests/test_login_rate_limit.py's LoginRateLimiter tests.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.auth.rate_limit import CooldownLimiter
from app.auth.service import auth_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Communication, PasswordResetToken, Tenant, User
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

RUN_ID = uuid.uuid4().hex[:8]
PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "a-brand-new-password-123"


def _unique_email(label: str) -> str:
    return f"pytest-password-reset-{RUN_ID}-{label}-{uuid.uuid4().hex[:6]}@example.invalid"


def _cleanup(email: str, tenant_name: str) -> None:
    db = SessionLocal()
    try:
        user_ids = [u.id for u in db.query(User).filter(User.email == email).all()]
        if user_ids:
            db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id.in_(user_ids)))
        db.execute(delete(User).where(User.email == email))
        tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
        if tenant is not None:
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
        db.execute(delete(Tenant).where(Tenant.name == tenant_name))
        db.commit()
    finally:
        db.close()


def _issue_raw_token(user_id: uuid.UUID, *, expires_at: datetime) -> str:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db = SessionLocal()
    try:
        crud.create_password_reset_token(
            db, id=uuid.uuid4(), user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
    finally:
        db.close()
    return raw_token


@pytest.fixture()
def user_and_headers(client):
    email = _unique_email("owner")
    tenant_name = f"Pytest Password Reset Tenant {uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=tenant_name))
        user = auth_service.create_user(
            db, tenant_id=tenant.id, name="Pytest User", email=email, password=PASSWORD, role="Owner"
        )
    finally:
        db.close()
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    yield user, email, headers
    _cleanup(email, tenant_name)


def test_forgot_password_for_a_real_email_returns_the_generic_message(client, user_and_headers):
    _, email, _ = user_and_headers
    r = client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert r.status_code == 200
    assert "if an account exists" in r.json()["message"].lower()


def test_forgot_password_for_an_unknown_email_returns_the_identical_message(client):
    r = client.post(
        "/api/v1/auth/password/forgot", json={"email": _unique_email("nobody")}
    )
    assert r.status_code == 200
    assert "if an account exists" in r.json()["message"].lower()


def test_forgot_password_creates_a_real_token_for_a_known_email(client, user_and_headers):
    user, email, _ = user_and_headers
    r = client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert r.status_code == 200

    db = SessionLocal()
    try:
        row = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.user_id == user.id)
            .first()
        )
        assert row is not None
        assert row.used_at is None
        assert row.expires_at > datetime.now(timezone.utc)
    finally:
        db.close()


def test_forgot_password_creates_no_token_for_an_unknown_email(client):
    # Delta, not an absolute count: other tests in this same run create
    # real tokens for real users, so an absolute "== 0" would be fragile
    # against test ordering/pollution within the same session — the same
    # lesson Sprint 039's Blocker 1 gate already learned once (see
    # tests/test_communications.py's TestRetryPending).
    db = SessionLocal()
    try:
        before = db.query(PasswordResetToken).count()
    finally:
        db.close()

    r = client.post(
        "/api/v1/auth/password/forgot", json={"email": _unique_email("nobody")}
    )
    assert r.status_code == 200

    db = SessionLocal()
    try:
        after = db.query(PasswordResetToken).count()
    finally:
        db.close()
    assert after == before


def test_forgot_password_is_rate_limited(client, user_and_headers):
    _, email, _ = user_and_headers
    first = client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert second.status_code == 429


def test_reset_with_valid_token_changes_the_password(client, user_and_headers):
    user, email, _ = user_and_headers
    raw_token = _issue_raw_token(user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    r = client.post(
        "/api/v1/auth/password/reset", json={"token": raw_token, "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 200

    old_login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200


def test_reset_revokes_an_existing_session(client, user_and_headers):
    user, email, headers = user_and_headers
    pre_reset_me = client.get("/api/v1/auth/me", headers=headers)
    assert pre_reset_me.status_code == 200

    raw_token = _issue_raw_token(user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    reset = client.post(
        "/api/v1/auth/password/reset", json={"token": raw_token, "new_password": NEW_PASSWORD}
    )
    assert reset.status_code == 200

    post_reset_me = client.get("/api/v1/auth/me", headers=headers)
    assert post_reset_me.status_code == 401

    fresh_login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": NEW_PASSWORD}
    )
    assert fresh_login.status_code == 200
    fresh_headers = {"Authorization": f"Bearer {fresh_login.json()['access_token']}"}
    fresh_me = client.get("/api/v1/auth/me", headers=fresh_headers)
    assert fresh_me.status_code == 200


def test_reset_with_unknown_token_is_400(client):
    r = client.post(
        "/api/v1/auth/password/reset", json={"token": "not-a-real-token", "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 400


def test_reset_is_single_use(client, user_and_headers):
    user, _, _ = user_and_headers
    raw_token = _issue_raw_token(user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    first = client.post(
        "/api/v1/auth/password/reset", json={"token": raw_token, "new_password": NEW_PASSWORD}
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/auth/password/reset",
        json={"token": raw_token, "new_password": "yet-another-password-456"},
    )
    assert second.status_code == 400


def test_expired_reset_token_is_rejected(client, user_and_headers):
    user, _, _ = user_and_headers
    raw_token = _issue_raw_token(user.id, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))

    r = client.post(
        "/api/v1/auth/password/reset", json={"token": raw_token, "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 400


def test_reset_enforces_a_minimum_password_length(client, user_and_headers):
    user, _, _ = user_and_headers
    raw_token = _issue_raw_token(user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    r = client.post(
        "/api/v1/auth/password/reset", json={"token": raw_token, "new_password": "short"}
    )
    assert r.status_code == 422


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_cooldown_limiter_blocks_a_second_call_within_the_window():
    clock = FakeClock()
    limiter = CooldownLimiter(clock=clock)

    limiter.check_and_record("someone@example.invalid", cooldown_seconds=60.0)
    with pytest.raises(Exception) as exc_info:
        limiter.check_and_record("someone@example.invalid", cooldown_seconds=60.0)
    assert exc_info.value.status_code == 429


def test_cooldown_limiter_allows_again_once_the_window_elapses():
    clock = FakeClock()
    limiter = CooldownLimiter(clock=clock)

    limiter.check_and_record("someone@example.invalid", cooldown_seconds=60.0)
    clock.advance(60.0)
    # Should not raise: the cooldown window has elapsed.
    limiter.check_and_record("someone@example.invalid", cooldown_seconds=60.0)


def test_cooldown_limiter_keys_are_case_and_whitespace_insensitive():
    clock = FakeClock()
    limiter = CooldownLimiter(clock=clock)

    limiter.check_and_record("Someone@Example.Invalid", cooldown_seconds=60.0)
    with pytest.raises(Exception):
        limiter.check_and_record(" someone@example.invalid ", cooldown_seconds=60.0)
