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
        # Sprint 012: TenantService.create() now logs a real ActivityLog row
        # against the new tenant's own id (ADR-029) — must be deleted before
        # the Tenant row or the FK constraint (ADR-025) rejects the delete.
        db.execute(delete(ActivityLog).where(ActivityLog.description.in_([TEST_NAME, AUTO_SLUG_NAME])))
        db.execute(delete(Tenant).where(Tenant.name.in_([TEST_NAME, AUTO_SLUG_NAME])))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def created_tenant(client, auth_headers):
    """POST /api/v1/tenants creates a brand-new, unlinked tenant — the
    caller's own tenant_id doesn't change (audited, unchanged behavior,
    see ADR-029). Used below to prove this orphan tenant is invisible via
    GET, even to the user who just created it."""
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
    """Logged under the *new* tenant's own id (ADR-029), not the caller's
    — so it's only visible via the new tenant's own activity feed, which
    nothing in this test suite ever authenticates as. Confirmed directly
    against the table instead."""
    _cleanup()
    try:
        client.post(
            "/api/v1/tenants",
            json={"name": TEST_NAME, "slug": TEST_SLUG},
            headers=auth_headers,
        )
        db = SessionLocal()
        try:
            row = (
                db.query(ActivityLog)
                .filter(ActivityLog.description == TEST_NAME)
                .first()
            )
            assert row is not None
            assert row.tenant_id is not None
        finally:
            db.close()
    finally:
        _cleanup()


def test_get_unknown_tenant_returns_404(client, auth_headers):
    r = client.get(f"/api/v1/tenants/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


def test_tenants_routes_require_auth(client):
    assert client.get("/api/v1/tenants").status_code == 401
    assert client.post("/api/v1/tenants", json={"name": "X"}).status_code == 401
    assert client.get(f"/api/v1/tenants/{uuid.uuid4()}").status_code == 401


# --- Sprint 012 (ADR-029): tenant list/detail must not expose other tenants


def test_list_tenants_returns_only_callers_own_tenant(client, auth_headers):
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()

    r = client.get("/api/v1/tenants", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == me["tenant_id"]


def test_get_own_tenant_by_id(client, auth_headers):
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()

    r = client.get(f"/api/v1/tenants/{me['tenant_id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == me["tenant_id"]


def test_newly_created_tenant_not_visible_to_its_creator(
    client, auth_headers, created_tenant
):
    """POST /api/v1/tenants creates an unlinked tenant — the caller's own
    tenant_id is unchanged, so the new tenant is invisible via GET even to
    the user who just created it. This is the pre-existing leak this
    sprint closes: previously GET /tenants/{id} returned any tenant."""
    r = client.get(f"/api/v1/tenants/{created_tenant['id']}", headers=auth_headers)
    assert r.status_code == 404

    listed = client.get("/api/v1/tenants", headers=auth_headers)
    ids = [t["id"] for t in listed.json()]
    assert created_tenant["id"] not in ids


def test_tenant_detail_cross_tenant_returns_404(
    client, auth_headers, other_tenant_auth_headers
):
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()

    r = client.get(
        f"/api/v1/tenants/{me['tenant_id']}", headers=other_tenant_auth_headers
    )
    assert r.status_code == 404


def test_tenant_list_does_not_include_other_tenant(
    client, auth_headers, other_tenant_auth_headers
):
    mine = client.get("/api/v1/tenants", headers=auth_headers).json()
    theirs = client.get("/api/v1/tenants", headers=other_tenant_auth_headers).json()
    assert mine[0]["id"] != theirs[0]["id"]
