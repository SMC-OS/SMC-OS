import uuid

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Project, Quote, Tenant, User

TEST_CUSTOMER_NAME = "Pytest Dashboard Customer"
TEST_PROJECT_NAME = "Pytest Dashboard Project"
TEST_QUOTE_POSTCODE = "PYTESTDASH1"

RUN_ID = uuid.uuid4().hex[:8]
RBAC_COMPANY = f"Pytest Dashboard RBAC Co {RUN_ID}"


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(Quote).where(Quote.postcode == TEST_QUOTE_POSTCODE))
        db.execute(delete(Project).where(Project.name == TEST_PROJECT_NAME))
        db.execute(delete(Customer).where(Customer.name == TEST_CUSTOMER_NAME))
        db.execute(
            delete(ActivityLog).where(
                ActivityLog.description.in_([TEST_CUSTOMER_NAME, TEST_PROJECT_NAME])
                | ActivityLog.description.like("Pytest Dashboard Quote%")
            )
        )
        db.commit()
    finally:
        db.close()


def test_dashboard_requires_auth(client):
    # Sprint 012 (ADR-029): /dashboard had no auth at all before this sprint.
    assert client.get("/api/v1/dashboard").status_code == 401


def test_dashboard_reflects_real_data(client, auth_headers):
    _cleanup()
    try:
        before = client.get("/api/v1/dashboard", headers=auth_headers).json()

        client.post(
            "/api/v1/customers", json={"name": TEST_CUSTOMER_NAME}, headers=auth_headers
        )
        client.post(
            "/api/v1/projects", json={"name": TEST_PROJECT_NAME}, headers=auth_headers
        )
        quote = client.post(
            "/api/v1/quote",
            json={
                "customer": "Pytest Dashboard Quote",
                "material": "calacatta gold",
                "thickness": "20mm",
                "kitchen_length": 2.0,
                "postcode": TEST_QUOTE_POSTCODE,
            },
            headers=auth_headers,
        ).json()

        after = client.get("/api/v1/dashboard", headers=auth_headers).json()

        assert after["customers"] == before["customers"] + 1
        assert after["projects"] == before["projects"] + 1
        assert after["quotes_today"] == before["quotes_today"] + 1
        assert after["revenue"] == pytest.approx(before["revenue"] + quote["total"])
    finally:
        _cleanup()


def test_dashboard_counts_are_tenant_scoped(
    client, auth_headers, other_tenant_auth_headers
):
    _cleanup()
    try:
        before_other = client.get(
            "/api/v1/dashboard", headers=other_tenant_auth_headers
        ).json()

        client.post(
            "/api/v1/customers", json={"name": TEST_CUSTOMER_NAME}, headers=auth_headers
        )
        client.post(
            "/api/v1/projects", json={"name": TEST_PROJECT_NAME}, headers=auth_headers
        )
        client.post(
            "/api/v1/quote",
            json={
                "customer": "Pytest Dashboard Quote",
                "material": "calacatta gold",
                "thickness": "20mm",
                "kitchen_length": 2.0,
                "postcode": TEST_QUOTE_POSTCODE,
            },
            headers=auth_headers,
        )

        # None of Tenant A's newly created records move Tenant B's counts.
        after_other = client.get(
            "/api/v1/dashboard", headers=other_tenant_auth_headers
        ).json()
        assert after_other == before_other
    finally:
        _cleanup()


def _create_tenant_and_user(*, suffix: str, role: str | None):
    """Sprint 026 — build a tenant + user with an explicit role (or no role
    at all) directly via the service layer, the same pattern
    tests/test_command_centre.py uses to lock in its require_role gate."""
    from app.tenants.models import TenantCreate
    from app.tenants.service import tenant_service

    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=f"{RBAC_COMPANY} {suffix}"))
        email = f"pytest-dashboard-rbac-{RUN_ID}-{suffix}@example.invalid"
        password = f"pytest-dashboard-rbac-{suffix}-password"
        auth_service.create_user(
            db,
            tenant_id=tenant.id,
            name="Pytest RBAC User",
            email=email,
            password=password,
            role=role,
        )
        return tenant.id, email, password
    finally:
        db.close()


def _cleanup_rbac_tenant(tenant_id):
    db = SessionLocal()
    try:
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(User).where(User.tenant_id == tenant_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
    finally:
        db.close()


def test_dashboard_role_none_is_forbidden(client):
    """Sprint 026 — the legacy GET /api/v1/dashboard must gate on role the
    same way its Sprint 025 replacement (/dashboard/command-centre) does:
    a role=None account is authenticated but not authorized."""
    tenant_id, email, password = _create_tenant_and_user(suffix="none", role=None)
    try:
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = client.get("/api/v1/dashboard", headers=headers)
        assert response.status_code == 403
    finally:
        _cleanup_rbac_tenant(tenant_id)


def test_dashboard_staff_can_access(client):
    """A Staff user (the other real role besides Owner) must keep working
    once the require_role gate is added — this isn't Owner-only."""
    tenant_id, email, password = _create_tenant_and_user(suffix="staff", role="Staff")
    try:
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = client.get("/api/v1/dashboard", headers=headers)
        assert response.status_code == 200
    finally:
        _cleanup_rbac_tenant(tenant_id)
