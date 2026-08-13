import uuid

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Tenant

TEST_NAME = "Pytest Tenant Co"
TEST_SLUG = "pytest-tenant-co"
AUTO_SLUG_NAME = "Pytest Auto Slug & Sons"


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(Tenant).where(Tenant.name.in_([TEST_NAME, AUTO_SLUG_NAME])))
        db.execute(delete(ActivityLog).where(ActivityLog.description.in_([TEST_NAME, AUTO_SLUG_NAME])))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def created_tenant(client, auth_headers):
    _cleanup()
    r = client.post(
        "/api/v1/tenants",
        json={"name": TEST_NAME, "slug": TEST_SLUG},
        headers=auth_headers,
    )
    yield r.json()
    _cleanup()


def test_create_tenant(client, auth_headers):
    _cleanup()
    try:
        r = client.post(
            "/api/v1/tenants",
            json={"name": TEST_NAME, "slug": TEST_SLUG},
            headers=auth_headers,
        )
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == TEST_NAME
        assert body["slug"] == TEST_SLUG
        assert body["status"] == "active"
        assert "id" in body
        assert "created_at" in body
    finally:
        _cleanup()


def test_create_tenant_auto_generates_slug(client, auth_headers):
    _cleanup()
    try:
        r = client.post(
            "/api/v1/tenants", json={"name": AUTO_SLUG_NAME}, headers=auth_headers
        )
        assert r.status_code == 201
        body = r.json()
        assert body["slug"]
        assert body["slug"] == body["slug"].lower()
        assert " " not in body["slug"]
        assert "&" not in body["slug"]
    finally:
        _cleanup()


def test_create_tenant_logs_activity(client, auth_headers):
    _cleanup()
    try:
        client.post(
            "/api/v1/tenants",
            json={"name": TEST_NAME, "slug": TEST_SLUG},
            headers=auth_headers,
        )
        r = client.get("/api/v1/activity?limit=50")
        descriptions = [e["description"] for e in r.json()]
        assert TEST_NAME in descriptions
    finally:
        _cleanup()


def test_list_tenants(client, auth_headers, created_tenant):
    r = client.get("/api/v1/tenants", headers=auth_headers)
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert TEST_NAME in names


def test_get_tenant_by_id(client, auth_headers, created_tenant):
    r = client.get(f"/api/v1/tenants/{created_tenant['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == TEST_NAME


def test_get_unknown_tenant_returns_404(client, auth_headers):
    r = client.get(f"/api/v1/tenants/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


def test_tenants_routes_require_auth(client):
    assert client.get("/api/v1/tenants").status_code == 401
    assert client.post("/api/v1/tenants", json={"name": "X"}).status_code == 401
    assert client.get(f"/api/v1/tenants/{uuid.uuid4()}").status_code == 401
