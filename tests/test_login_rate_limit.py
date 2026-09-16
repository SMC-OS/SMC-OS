"""Sprint 026 Contract B — brute-force throttle on POST /auth/login.

Unit tests exercise app.auth.rate_limit.LoginRateLimiter directly with an
injected fake clock (no real sleeps, deterministic). HTTP tests exercise the
real router wiring with the default Settings (5 attempts / 60s window).
"""

import uuid

import pytest
from sqlalchemy import delete

from app.auth.rate_limit import LoginRateLimiter
from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Subscription, Tenant, User
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

RUN_ID = uuid.uuid4().hex[:8]


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_allows_up_to_max_attempts_then_blocks():
    clock = FakeClock()
    limiter = LoginRateLimiter(clock=clock)

    for _ in range(5):
        limiter.check("someone@example.invalid", max_attempts=5, window_seconds=60.0)
        limiter.record_failure("someone@example.invalid", window_seconds=60.0)

    with pytest.raises(Exception) as exc_info:
        limiter.check("someone@example.invalid", max_attempts=5, window_seconds=60.0)
    assert exc_info.value.status_code == 429


def test_window_expiry_allows_again():
    clock = FakeClock()
    limiter = LoginRateLimiter(clock=clock)

    for _ in range(5):
        limiter.check("someone@example.invalid", max_attempts=5, window_seconds=60.0)
        limiter.record_failure("someone@example.invalid", window_seconds=60.0)

    clock.advance(60.0)

    # Should not raise: the window has rolled over.
    limiter.check("someone@example.invalid", max_attempts=5, window_seconds=60.0)


def test_reset_clears_the_window():
    clock = FakeClock()
    limiter = LoginRateLimiter(clock=clock)

    for _ in range(5):
        limiter.check("someone@example.invalid", max_attempts=5, window_seconds=60.0)
        limiter.record_failure("someone@example.invalid", window_seconds=60.0)

    limiter.reset("someone@example.invalid")

    # Should not raise: the counter was cleared.
    limiter.check("someone@example.invalid", max_attempts=5, window_seconds=60.0)


def test_emails_are_tracked_independently():
    clock = FakeClock()
    limiter = LoginRateLimiter(clock=clock)

    for _ in range(5):
        limiter.check("first@example.invalid", max_attempts=5, window_seconds=60.0)
        limiter.record_failure("first@example.invalid", window_seconds=60.0)

    # A different email must be unaffected.
    limiter.check("second@example.invalid", max_attempts=5, window_seconds=60.0)


def test_email_matching_is_case_and_whitespace_insensitive():
    clock = FakeClock()
    limiter = LoginRateLimiter(clock=clock)

    for _ in range(5):
        limiter.check("Someone@Example.Invalid", max_attempts=5, window_seconds=60.0)
        limiter.record_failure(" someone@example.invalid ", window_seconds=60.0)

    with pytest.raises(Exception) as exc_info:
        limiter.check("SOMEONE@EXAMPLE.INVALID", max_attempts=5, window_seconds=60.0)
    assert exc_info.value.status_code == 429


def _create_tenant_and_user(*, suffix: str):
    db = SessionLocal()
    try:
        tenant = tenant_service.create(
            db, TenantCreate(name=f"Pytest Login Throttle Co {RUN_ID} {suffix}")
        )
        email = f"pytest-login-throttle-{RUN_ID}-{suffix}@example.invalid"
        password = f"pytest-login-throttle-{suffix}-password"
        auth_service.create_user(
            db,
            tenant_id=tenant.id,
            name="Pytest Throttle User",
            email=email,
            password=password,
            role="Owner",
        )
        return tenant.id, email, password
    finally:
        db.close()


def _cleanup_tenant(tenant_id):
    db = SessionLocal()
    try:
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
        db.execute(delete(User).where(User.tenant_id == tenant_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
    finally:
        db.close()


def test_login_blocks_after_max_failed_attempts(client):
    tenant_id, email, password = _create_tenant_and_user(suffix="threshold")
    try:
        for _ in range(5):
            r = client.post(
                "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
            )
            assert r.status_code == 401

        # 6th attempt is blocked even with the CORRECT password.
        r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 429
        assert "Retry-After" in r.headers
    finally:
        _cleanup_tenant(tenant_id)


def test_login_rate_limit_is_per_email(client):
    tenant_a_id, email_a, _ = _create_tenant_and_user(suffix="isolation-a")
    tenant_b_id, email_b, password_b = _create_tenant_and_user(suffix="isolation-b")
    try:
        for _ in range(5):
            r = client.post(
                "/api/v1/auth/login", json={"email": email_a, "password": "wrong-password"}
            )
            assert r.status_code == 401
        blocked = client.post(
            "/api/v1/auth/login", json={"email": email_a, "password": "wrong-password"}
        )
        assert blocked.status_code == 429

        # A different account, in the same window, is unaffected.
        unaffected = client.post(
            "/api/v1/auth/login", json={"email": email_b, "password": password_b}
        )
        assert unaffected.status_code == 200
    finally:
        _cleanup_tenant(tenant_a_id)
        _cleanup_tenant(tenant_b_id)


def test_successful_login_resets_the_failure_counter(client):
    tenant_id, email, password = _create_tenant_and_user(suffix="reset")
    try:
        for _ in range(2):
            r = client.post(
                "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
            )
            assert r.status_code == 401

        ok = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert ok.status_code == 200

        # A single failure right after a success must not be blocked —
        # proves the counter was cleared on success, not just decremented.
        r = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert r.status_code == 401
    finally:
        _cleanup_tenant(tenant_id)
