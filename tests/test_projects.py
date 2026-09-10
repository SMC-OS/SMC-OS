import uuid

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Project

TEST_NAME = "Pytest Project"
TEST_CUSTOMER_NAME = "Pytest Project Customer"


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(Project).where(Project.name == TEST_NAME))
        db.execute(
            delete(ActivityLog).where(
                ActivityLog.description.in_([TEST_NAME, TEST_CUSTOMER_NAME])
            )
        )
        db.execute(delete(Customer).where(Customer.name == TEST_CUSTOMER_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def created_project(client, auth_headers):
    _cleanup()
    r = client.post(
        "/api/v1/projects", json={"name": TEST_NAME}, headers=auth_headers
    )
    yield r.json()
    _cleanup()


def test_create_project_starts_at_the_first_stage_of_the_pipeline(client, auth_headers):
    """Sprint 039: asserted on the trade-neutral *role*, not on a stage
    key. Which key a new job starts on depends on this workspace's own
    pipeline ("lead" on the standard one, "enquiry" for a stone tenant);
    that it starts at the beginning does not."""
    _cleanup()
    try:
        r = client.post(
            "/api/v1/projects", json={"name": TEST_NAME}, headers=auth_headers
        )
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == TEST_NAME
        assert body["status_role"] == "lead"
        assert "id" in body
        assert "created_at" in body
    finally:
        _cleanup()


def test_create_project_logs_activity(client, auth_headers):
    _cleanup()
    try:
        client.post(
            "/api/v1/projects", json={"name": TEST_NAME}, headers=auth_headers
        )
        # Sprint 012: /activity now requires auth and is tenant-scoped.
        r = client.get("/api/v1/activity?limit=50", headers=auth_headers)
        descriptions = [e["description"] for e in r.json()]
        assert TEST_NAME in descriptions
    finally:
        _cleanup()


def test_create_project_with_customer_id_round_trips(client, auth_headers):
    _cleanup()
    try:
        customer = client.post(
            "/api/v1/customers",
            json={"name": TEST_CUSTOMER_NAME},
            headers=auth_headers,
        ).json()

        r = client.post(
            "/api/v1/projects",
            json={"name": TEST_NAME, "customer_id": customer["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 201
        assert r.json()["customer_id"] == customer["id"]
    finally:
        _cleanup()


def test_list_projects(client, auth_headers, created_project):
    r = client.get("/api/v1/projects", headers=auth_headers)
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert TEST_NAME in names


def test_get_project_by_id(client, auth_headers, created_project):
    r = client.get(f"/api/v1/projects/{created_project['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == TEST_NAME


def test_get_unknown_project_returns_404(client, auth_headers):
    r = client.get(f"/api/v1/projects/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


def test_advance_project_status(client, auth_headers, created_project):
    r = client.patch(
        f"/api/v1/projects/{created_project['id']}/status",
        json={"status": "quoted"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "quoted"

    # Reflected on a subsequent GET.
    r2 = client.get(f"/api/v1/projects/{created_project['id']}", headers=auth_headers)
    assert r2.json()["status"] == "quoted"


def test_update_status_unknown_stage_is_refused(client, auth_headers, created_project):
    """Sprint 039: a stage key is no longer validated against a shared
    enum at the Pydantic boundary — which stages exist is per-tenant
    configuration, so the check moved into the service and the refusal is
    a 409 (this pipeline does not allow that move) rather than a 422."""
    r = client.patch(
        f"/api/v1/projects/{created_project['id']}/status",
        json={"status": "not-a-real-stage"},
        headers=auth_headers,
    )
    assert r.status_code == 409


def test_update_status_unknown_project_returns_404(client, auth_headers):
    r = client.patch(
        f"/api/v1/projects/{uuid.uuid4()}/status",
        json={"status": "quoted"},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_projects_routes_require_auth(client):
    assert client.get("/api/v1/projects").status_code == 401
    assert client.post("/api/v1/projects", json={"name": "X"}).status_code == 401
    assert client.get(f"/api/v1/projects/{uuid.uuid4()}").status_code == 401
    assert (
        client.patch(
            f"/api/v1/projects/{uuid.uuid4()}/status", json={"status": "quoted"}
        ).status_code
        == 401
    )


# --- Sprint 012 (ADR-029): cross-tenant isolation ---------------------------


def test_project_not_visible_to_other_tenant(
    client, auth_headers, other_tenant_auth_headers, created_project
):
    r = client.get("/api/v1/projects", headers=other_tenant_auth_headers)
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert TEST_NAME not in names


def test_get_project_cross_tenant_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_project
):
    r = client.get(
        f"/api/v1/projects/{created_project['id']}", headers=other_tenant_auth_headers
    )
    assert r.status_code == 404


def test_update_status_cross_tenant_returns_404_and_does_not_mutate(
    client, auth_headers, other_tenant_auth_headers, created_project
):
    # The write-path check: Tenant B must not be able to advance Tenant A's
    # project by guessing/knowing its id.
    r = client.patch(
        f"/api/v1/projects/{created_project['id']}/status",
        json={"status": "quoted"},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404

    # Confirm it genuinely wasn't mutated — still at its opening stage for
    # its actual owner.
    r2 = client.get(f"/api/v1/projects/{created_project['id']}", headers=auth_headers)
    assert r2.json()["status_role"] == "lead"


def test_create_project_with_other_tenants_customer_id_returns_404(
    client, auth_headers, other_tenant_auth_headers
):
    """Relationship-bypass check (ADR-029): linking a project to a
    customer_id belonging to a different tenant must be rejected, not
    silently allowed — otherwise a project record could reference another
    tenant's customer despite every id-based lookup being tenant-scoped."""
    _cleanup()
    try:
        their_customer = client.post(
            "/api/v1/customers",
            json={"name": TEST_CUSTOMER_NAME},
            headers=other_tenant_auth_headers,
        ).json()

        r = client.post(
            "/api/v1/projects",
            json={"name": TEST_NAME, "customer_id": their_customer["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 404

        # And no project was created at all as a side effect.
        mine = client.get("/api/v1/projects", headers=auth_headers).json()
        assert not any(p["name"] == TEST_NAME for p in mine)
    finally:
        _cleanup()
