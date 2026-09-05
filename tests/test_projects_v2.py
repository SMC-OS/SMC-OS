"""Projects V2 — Sprint 036, Workstream F."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import Project

RUN_ID = uuid.uuid4().hex[:8]
TEST_PREFIX = f"Pytest Projects V2 {RUN_ID}"


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(Project).where(Project.name.like(f"{TEST_PREFIX}%")))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


def _create(client, auth_headers, **overrides):
    payload = {"name": f"{TEST_PREFIX} job"}
    payload.update(overrides)
    r = client.post("/api/v1/projects", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_the_original_body_still_works(client, auth_headers):
    project = _create(client, auth_headers, notes="Just a note")

    assert project["notes"] == "Just a note"
    assert project["status"] == "enquiry"
    assert project["project_type"] is None
    assert project["start_date"] is None


def test_creates_a_full_construction_project_record(client, auth_headers):
    start = date.today() + timedelta(days=14)
    finish = start + timedelta(days=21)

    project = _create(
        client,
        auth_headers,
        project_type="roofing",
        description="Full re-roof including new felt and battens.",
        site_address_line1="9 Church Street",
        site_city="Sheffield",
        site_postcode="S1 2AB",
        start_date=start.isoformat(),
        target_completion_date=finish.isoformat(),
        estimated_value=18500,
    )

    assert project["project_type"] == "roofing"
    assert project["site_city"] == "Sheffield"
    assert project["start_date"] == start.isoformat()
    assert project["target_completion_date"] == finish.isoformat()
    assert project["estimated_value"] == 18500


def test_rejects_an_unknown_project_type(client, auth_headers):
    r = client.post(
        "/api/v1/projects",
        json={"name": f"{TEST_PREFIX} bad", "project_type": "spaceship_assembly"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_patch_updates_details_without_touching_status(client, auth_headers):
    project = _create(client, auth_headers)

    r = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"site_city": "Bradford", "estimated_value": 9000},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()

    assert updated["site_city"] == "Bradford"
    assert updated["estimated_value"] == 9000
    # Status has its own endpoint with its own linear-transition rules,
    # and a general PATCH must not be able to route around them.
    assert updated["status"] == "enquiry"


def test_patch_cannot_set_status(client, auth_headers):
    project = _create(client, auth_headers)
    r = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"status": "complete"},
        headers=auth_headers,
    )
    # Unknown field is ignored by the model rather than rejected; what
    # matters is that it cannot take effect.
    assert r.status_code == 200
    assert r.json()["status"] == "enquiry"


def test_patch_rejects_another_tenants_customer(
    client, auth_headers, other_tenant_auth_headers
):
    project = _create(client, auth_headers)
    other_customer = client.post(
        "/api/v1/customers",
        json={"name": f"{TEST_PREFIX} other tenant customer"},
        headers=other_tenant_auth_headers,
    ).json()

    r = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"customer_id": other_customer["id"]},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_patch_is_404_across_tenants(client, auth_headers, other_tenant_auth_headers):
    project = _create(client, auth_headers)
    r = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"site_city": "Nope"},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404
