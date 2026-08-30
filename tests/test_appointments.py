"""Sprint 022 — Appointment / Site Visit Scheduling.

See docs/SPRINTS/sprint-022.md for the locked contract this test implements
the first RED cycle of. Structural twin of
tests/test_enquiry_conversion.py's first RED (Sprint 021) — the
`appointments` table/model do not exist yet, so this test deliberately
imports nothing Appointment-specific; every assertion is made against the
real HTTP response body and the pre-existing `Project` row.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Project

TEST_PREFIX = "Pytest Sprint 022"
TEST_PROJECT_NAME = f"{TEST_PREFIX} Project"
TEST_NOTES = f"{TEST_PREFIX} Site Visit Notes"


def _cleanup() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Project).where(Project.name == TEST_PROJECT_NAME))
        db.execute(delete(ActivityLog).where(ActivityLog.title.like(f"{TEST_PREFIX}%")))
        db.commit()
    finally:
        db.close()


def test_staff_can_create_a_scheduled_appointment_against_a_same_tenant_project(
    client, auth_headers
):
    """First Sprint 022 contract: an OWNER/STAFF caller schedules a site
    visit against their own tenant's Project. Tenant isolation, RBAC
    negatives, list/read, completion, cancellation, activity, and
    atomicity are later RED/GREEN cycles, not this one — see
    docs/SPRINTS/sprint-022.md's locked TDD sequence."""
    _cleanup()
    try:
        project = client.post(
            "/api/v1/projects",
            json={"name": TEST_PROJECT_NAME},
            headers=auth_headers,
        )
        assert project.status_code == 201
        project_id = project.json()["id"]

        with SessionLocal() as db:
            expected_tenant_id = db.get(Project, uuid.UUID(project_id)).tenant_id

        scheduled_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

        response = client.post(
            f"/api/v1/projects/{project_id}/appointments",
            json={"scheduled_at": scheduled_at, "notes": TEST_NOTES},
            headers=auth_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert "id" in body
        assert uuid.UUID(body["tenant_id"]) == expected_tenant_id
        assert body["project_id"] == project_id
        assert body["status"] == "scheduled"
        assert datetime.fromisoformat(body["scheduled_at"]) == datetime.fromisoformat(
            scheduled_at
        )
        assert body["notes"] == TEST_NOTES
    finally:
        _cleanup()
