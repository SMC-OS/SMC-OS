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


def test_create_project_defaults_to_enquiry(client, auth_headers):
    _cleanup()
    try:
        r = client.post(
            "/api/v1/projects", json={"name": TEST_NAME}, headers=auth_headers
        )
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == TEST_NAME
        assert body["status"] == "enquiry"
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
        r = client.get("/api/v1/activity?limit=50")
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


def test_update_status_invalid_value_returns_422(client, auth_headers, created_project):
    r = client.patch(
        f"/api/v1/projects/{created_project['id']}/status",
        json={"status": "not-a-real-stage"},
        headers=auth_headers,
    )
    assert r.status_code == 422


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
