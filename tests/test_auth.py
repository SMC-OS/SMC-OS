from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.core.config import settings
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailVerificationToken,
    Subscription,
    Tenant,
    User,
)
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

TEST_EMAIL = "pytest-auth-test@example.invalid"
TEST_PASSWORD = "correct-horse-battery-staple"
TEST_TENANT_NAME = "Pytest Auth Tenant"

SIGNUP_EMAIL = "pytest-signup-test@example.invalid"
SIGNUP_COMPANY = "Pytest Signup Co"


def _delete_tenant_and_its_activity(db, *, name: str) -> None:
    # Sprint 012: TenantService.create() now logs a real ActivityLog row
    # against the new tenant's own id (ADR-029) — must be deleted before
    # the Tenant row or the FK constraint (ADR-025) rejects the delete.
    tenant = db.query(Tenant).filter(Tenant.name == name).first()
    if tenant is not None:
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
        # Sprint 039 Production Readiness Defect Gate, Blocker 1 — signup
        # now also attempts a verification-email send, which writes a
        # Communication row (tenant_id NOT NULL, no ondelete) — same
        # "delete before the Tenant row" requirement Sprint 038 already
        # established for every other test file's tenant cleanup.
        db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
        # Sprint 039 Production Readiness Defect Gate, Blocker 3 — signup
        # now also starts a real trial Subscription row (tenant_id FK, no
        # ondelete) — same "delete before the Tenant row" requirement.
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
        db.execute(delete(Tenant).where(Tenant.id == tenant.id))


def _cleanup_signup():
    db = SessionLocal()
    try:
        user_ids = [u.id for u in db.query(User).filter(User.email == SIGNUP_EMAIL).all()]
        if user_ids:
            db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(user_ids)))
        db.execute(delete(User).where(User.email == SIGNUP_EMAIL))
        _delete_tenant_and_its_activity(db, name=SIGNUP_COMPANY)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def test_user():
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == TEST_EMAIL))
        _delete_tenant_and_its_activity(db, name=TEST_TENANT_NAME)
        db.commit()
        tenant = tenant_service.create(db, TenantCreate(name=TEST_TENANT_NAME))
        user = auth_service.create_user(
            db,
            tenant_id=tenant.id,
            name="Pytest User",
            email=TEST_EMAIL,
            password=TEST_PASSWORD,
            role="Staff",
        )
        yield user
    finally:
        db.execute(delete(User).where(User.email == TEST_EMAIL))
        _delete_tenant_and_its_activity(db, name=TEST_TENANT_NAME)
        db.commit()
        db.close()


def test_login_success(client, test_user):
    r = client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == TEST_EMAIL
    assert body["access_token"]
    # Sprint 009 — every login now round-trips tenant info.
    assert body["user"]["tenant_id"] == str(test_user.tenant_id)
    assert body["user"]["tenant_name"] == TEST_TENANT_NAME


def test_login_wrong_password(client, test_user):
    r = client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": "wrong"}
    )
    assert r.status_code == 401


def test_login_unknown_email(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.invalid", "password": "x"},
    )
    assert r.status_code == 401


def test_me_with_valid_token(client, test_user):
    login = client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    token = login.json()["access_token"]

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == TEST_EMAIL


def test_me_returns_tenant_info(client, test_user):
    login = client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    token = login.json()["access_token"]

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == str(test_user.tenant_id)
    assert body["tenant_name"] == TEST_TENANT_NAME


def test_me_without_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_with_garbage_token(client):
    r = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert r.status_code == 401


def test_token_missing_tenant_id_is_rejected(client, test_user):
    # Sprint 009 — simulates a token issued before this sprint (sub + exp
    # only, no tenant_id claim). Must be rejected cleanly (401), not
    # silently treated as tenant-less. See app/auth/security.py's docstring.
    payload = {
        "sub": str(test_user.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    old_shape_token = jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    r = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_shape_token}"}
    )
    assert r.status_code == 401


def test_signup_creates_tenant_and_user(client):
    _cleanup_signup()
    try:
        r = client.post(
            "/api/v1/auth/signup",
            json={
                "company_name": SIGNUP_COMPANY,
                "name": "Pytest Owner",
                "email": SIGNUP_EMAIL,
                "password": "Another-Strong-Password-1!",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["user"]["email"] == SIGNUP_EMAIL
        assert body["user"]["role"] == "Owner"
        assert body["user"]["tenant_name"] == SIGNUP_COMPANY
        assert body["user"]["tenant_id"]

        # The new token is immediately usable and reflects the new tenant.
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["tenant_name"] == SIGNUP_COMPANY
    finally:
        _cleanup_signup()


def test_signup_duplicate_email_returns_409(client, test_user):
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Another Co",
            "name": "Dupe",
            "email": TEST_EMAIL,
            "password": "Whatever-Password-123!",
        },
    )
    assert r.status_code == 409
