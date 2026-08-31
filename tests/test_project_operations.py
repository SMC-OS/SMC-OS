"""Sprint 023 — Project Operations (staff assignment + validated status
transitions). See docs/SPRINTS/sprint-023.md for the locked contract this
test implements the first RED cycle of. Structural twin of
tests/test_appointments.py's first RED (Sprint 022) — the `assigned_user_id`
column/route do not exist yet, so this test deliberately imports nothing
assignment-specific; every assertion is made against the real HTTP response
body and the pre-existing `Project`/`User` rows.
"""

import uuid

from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Project, User

TEST_PREFIX = "Pytest Sprint 023"
TEST_PROJECT_NAME = f"{TEST_PREFIX} Project"
STAFF_EMAIL = "pytest-sprint023-staff@example.invalid"
STAFF_PASSWORD = "pytest-sprint023-staff-password"


def _cleanup() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Project).where(Project.name == TEST_PROJECT_NAME))
        db.execute(delete(ActivityLog).where(ActivityLog.title.like(f"{TEST_PREFIX}%")))
        db.execute(delete(User).where(User.email == STAFF_EMAIL))
        db.commit()
    finally:
        db.close()


def _create_booked_project(client, headers: dict[str, str]) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": TEST_PROJECT_NAME}, headers=headers
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    quoted = client.patch(
        f"/api/v1/projects/{project_id}/status", json={"status": "quoted"}, headers=headers
    )
    assert quoted.status_code == 200

    booked = client.patch(
        f"/api/v1/projects/{project_id}/status", json={"status": "booked"}, headers=headers
    )
    assert booked.status_code == 200
    return booked.json()


def test_owner_can_assign_a_same_tenant_staff_member_to_a_booked_project(client, auth_headers):
    """First Sprint 023 contract: an OWNER caller assigns a same-tenant
    Staff member to their own booked Project. Cross-tenant, RBAC negatives,
    unassignment, activity, and atomicity are later RED/GREEN cycles, not
    this one — see docs/SPRINTS/sprint-023.md's locked TDD sequence."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id

        from app.auth.service import auth_service

        with SessionLocal() as db:
            staff = auth_service.create_user(
                db,
                tenant_id=tenant_id,
                name="Pytest Sprint 023 Staff",
                email=STAFF_EMAIL,
                password=STAFF_PASSWORD,
                role="Staff",
            )
            staff_id = str(staff.id)

        response = client.patch(
            f"/api/v1/projects/{project['id']}/assign",
            json={"assigned_user_id": staff_id},
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == project["id"]
        assert body["assigned_user_id"] == staff_id

        with SessionLocal() as db:
            persisted = db.get(Project, uuid.UUID(project["id"]))
            assert str(persisted.assigned_user_id) == staff_id
    finally:
        _cleanup()
