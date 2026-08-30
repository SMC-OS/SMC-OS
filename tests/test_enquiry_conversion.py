"""Sprint 021 — Enquiry (Project.status == "enquiry") to Customer conversion.

See docs/SPRINTS/sprint-021.md for the locked contract this test implements
the first RED cycle of. Same route-level-client test pattern as
tests/test_quote_handoff.py (Sprint 020's Quote->Project handoff, the direct
template for this Project->Customer conversion).
"""

import uuid

from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Project

TEST_PREFIX = "Pytest Sprint 021"
TEST_PROJECT_NAME = f"{TEST_PREFIX} Project"
TEST_CUSTOMER_NAME = f"{TEST_PREFIX} Customer"
TEST_CUSTOMER_EMAIL = "pytest-sprint021-customer@example.invalid"
TEST_CUSTOMER_PHONE = "+44 7000 000021"


def _cleanup() -> None:
    db = SessionLocal()
    try:
        # Projects must go before their Customer — Project.customer_id has
        # no ON DELETE CASCADE (same ordering as tests/test_quote_handoff.py).
        db.execute(delete(Project).where(Project.name == TEST_PROJECT_NAME))
        db.execute(delete(ActivityLog).where(ActivityLog.title.like(f"{TEST_PREFIX}%")))
        db.execute(delete(Customer).where(Customer.name == TEST_CUSTOMER_NAME))
        db.commit()
    finally:
        db.close()


def _create_unlinked_enquiry_project(client, headers: dict[str, str]) -> dict:
    project = client.post(
        "/api/v1/projects",
        json={"name": TEST_PROJECT_NAME},
        headers=headers,
    )
    assert project.status_code == 201
    body = project.json()
    assert body["status"] == "enquiry"
    assert body["customer_id"] is None
    return body


def test_staff_can_convert_an_unlinked_enquiry_project_into_a_customer(client, auth_headers):
    """First Sprint 021 conversion contract: an unlinked, status="enquiry"
    Project gets a real Customer created and linked through it, returning
    that Customer. Repeat-conversion idempotency, non-enquiry 409,
    cross-tenant 404, RBAC 403, activity, and frontend are later RED/GREEN
    cycles, not this one (docs/SPRINTS/sprint-021.md §5)."""
    _cleanup()
    try:
        project = _create_unlinked_enquiry_project(client, auth_headers)

        with SessionLocal() as db:
            customers_before = db.query(Customer).filter_by(name=TEST_CUSTOMER_NAME).count()

        response = client.post(
            f"/api/v1/projects/{project['id']}/convert-to-customer",
            json={
                "name": TEST_CUSTOMER_NAME,
                "email": TEST_CUSTOMER_EMAIL,
                "phone": TEST_CUSTOMER_PHONE,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        customer = response.json()
        assert customer["name"] == TEST_CUSTOMER_NAME
        assert customer["email"] == TEST_CUSTOMER_EMAIL
        assert customer["phone"] == TEST_CUSTOMER_PHONE
        assert "id" in customer

        with SessionLocal() as db:
            persisted_project = db.get(Project, uuid.UUID(project["id"]))
            assert str(persisted_project.customer_id) == customer["id"]
            assert persisted_project.status == "enquiry"

            customers_after = db.query(Customer).filter_by(name=TEST_CUSTOMER_NAME).count()
            assert customers_after == customers_before + 1
    finally:
        _cleanup()
