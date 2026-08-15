import uuid

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer

TEST_NAME = "Pytest Customer"
TEST_EMAIL = "pytest-customer-test@example.invalid"


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(Customer).where(Customer.name == TEST_NAME))
        db.execute(delete(ActivityLog).where(ActivityLog.description == TEST_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def created_customer(client, auth_headers):
    _cleanup()
    r = client.post(
        "/api/v1/customers",
        json={"name": TEST_NAME, "email": TEST_EMAIL, "phone": "07123456789"},
        headers=auth_headers,
    )
    yield r.json()
    _cleanup()


def test_create_customer(client, auth_headers):
    _cleanup()
    try:
        r = client.post(
            "/api/v1/customers",
            json={"name": TEST_NAME, "email": TEST_EMAIL, "phone": "07123456789"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == TEST_NAME
        assert body["email"] == TEST_EMAIL
        assert "id" in body
        assert "created_at" in body
    finally:
        _cleanup()


def test_create_customer_logs_activity(client, auth_headers):
    _cleanup()
    try:
        client.post(
            "/api/v1/customers",
            json={"name": TEST_NAME, "email": TEST_EMAIL},
            headers=auth_headers,
        )
        # Sprint 012: /activity now requires auth and is tenant-scoped.
        r = client.get("/api/v1/activity?limit=50", headers=auth_headers)
        descriptions = [e["description"] for e in r.json()]
        assert TEST_NAME in descriptions
    finally:
        _cleanup()


def test_list_customers(client, auth_headers, created_customer):
    r = client.get("/api/v1/customers", headers=auth_headers)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert TEST_NAME in names


def test_list_customers_respects_limit(client, auth_headers, created_customer):
    r = client.get("/api/v1/customers?limit=1", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) <= 1


def test_get_customer_by_id(client, auth_headers, created_customer):
    r = client.get(f"/api/v1/customers/{created_customer['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == TEST_NAME


def test_get_unknown_customer_returns_404(client, auth_headers):
    r = client.get(f"/api/v1/customers/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


def test_customers_routes_require_auth(client):
    assert client.get("/api/v1/customers").status_code == 401
    assert client.post("/api/v1/customers", json={"name": "X"}).status_code == 401
    assert client.get(f"/api/v1/customers/{uuid.uuid4()}").status_code == 401


# --- Sprint 012 (ADR-029): cross-tenant isolation ---------------------------


def test_customer_not_visible_to_other_tenant(
    client, auth_headers, other_tenant_auth_headers, created_customer
):
    r = client.get("/api/v1/customers", headers=other_tenant_auth_headers)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert TEST_NAME not in names


def test_get_customer_cross_tenant_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_customer
):
    r = client.get(
        f"/api/v1/customers/{created_customer['id']}", headers=other_tenant_auth_headers
    )
    assert r.status_code == 404


def test_customers_created_in_own_tenant_only(
    client, auth_headers, other_tenant_auth_headers
):
    _cleanup()
    try:
        created = client.post(
            "/api/v1/customers",
            json={"name": TEST_NAME, "email": TEST_EMAIL},
            headers=auth_headers,
        ).json()

        # Tenant A sees it.
        mine = client.get("/api/v1/customers", headers=auth_headers).json()
        assert any(c["id"] == created["id"] for c in mine)

        # Tenant B does not.
        theirs = client.get("/api/v1/customers", headers=other_tenant_auth_headers).json()
        assert not any(c["id"] == created["id"] for c in theirs)
    finally:
        _cleanup()
