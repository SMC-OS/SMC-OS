import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import settings
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Tenant, User
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    """A plain DB session for tests that call service-layer code directly
    (not through the HTTP client) — reusable by any module's tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def auth_headers(client):
    """Bearer header for the seeded owner — reusable by any module's tests
    that need to call an authenticated route (customers, and beyond)."""
    r = client.post(
        "/api/v1/auth/login",
        json={"email": settings.seed_admin_email, "password": settings.seed_admin_password},
    )
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# Sprint 012 (ADR-029) — cross-tenant isolation tests need two genuinely
# separate tenants, not just two users. `other_tenant_auth_headers` signs
# up a brand-new company/owner distinct from the seeded owner `auth_headers`
# uses, so a test can assert Tenant A's records are invisible/unreachable
# from Tenant B and vice versa.
OTHER_TENANT_EMAIL = "pytest-other-tenant-owner@example.com"
OTHER_TENANT_COMPANY = "Pytest Other Tenant Co"
OTHER_TENANT_PASSWORD = "pytest-other-tenant-password-1"


def _cleanup_other_tenant():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == OTHER_TENANT_EMAIL).first()
        if user is not None:
            # Sprint 012: TenantService.create() now logs a real ActivityLog
            # row against the new tenant's own id (ADR-029), so it must be
            # deleted before the Tenant row or the FK constraint added in
            # Sprint 008 (ADR-025) rejects the delete.
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == user.tenant_id))
            db.execute(delete(User).where(User.email == OTHER_TENANT_EMAIL))
            db.execute(delete(Tenant).where(Tenant.id == user.tenant_id))
            db.commit()
    finally:
        db.close()


@pytest.fixture()
def other_tenant_auth_headers(client):
    """Bearer header for a second, fully separate tenant + Owner — signs up
    fresh each test run and is torn down after, same shape as the
    created_tenant/created_customer fixtures elsewhere in this suite."""
    _cleanup_other_tenant()
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": OTHER_TENANT_COMPANY,
            "name": "Other Tenant Owner",
            "email": OTHER_TENANT_EMAIL,
            "password": OTHER_TENANT_PASSWORD,
        },
    )
    token = r.json()["access_token"]
    yield {"Authorization": f"Bearer {token}"}
    _cleanup_other_tenant()
