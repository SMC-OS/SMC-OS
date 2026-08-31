"""Sprint 024 — Notifications / Follow-up Automation (stale enquiry
follow-up). See docs/SPRINTS/sprint-024.md for the locked contract this
test implements the first RED cycle of. Unlike prior sprints' first RED
(an HTTP route), this is a pure domain-service test — the locked contract
has no HTTP boundary for automation (docs/SPRINTS/sprint-024.md §7/§9) —
so this deliberately imports app.notifications.follow_up_service, which
does not exist yet, and calls it directly against a plain DB session.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import NotificationRecord, Project, User

TEST_PREFIX = "Pytest Sprint 024"
TEST_PROJECT_NAME = f"{TEST_PREFIX} Project"
STAFF_EMAIL = "pytest-sprint024-staff@example.invalid"
STAFF_PASSWORD = "pytest-sprint024-staff-password"

STALE_NOW = lambda created_at: created_at + timedelta(days=8)  # noqa: E731


def _cleanup() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(NotificationRecord).where(NotificationRecord.title.like(f"{TEST_PREFIX}%")))
        db.execute(delete(Project).where(Project.name == TEST_PROJECT_NAME))
        db.execute(delete(User).where(User.email == STAFF_EMAIL))
        db.commit()
    finally:
        db.close()


def test_run_creates_exactly_one_notification_for_a_stale_enquiry_with_assigned_staff(
    client, auth_headers
):
    """First Sprint 024 contract: a stale (status=="enquiry", created more
    than the locked threshold ago) Project with an assigned Staff member
    produces exactly one NotificationRecord targeted at that Staff member.
    Idempotency, not-due/wrong-state exclusions, cross-tenant isolation,
    Owner fallback, and failure safety are later RED/GREEN cycles, not
    this one — see docs/SPRINTS/sprint-024.md's locked TDD sequence."""
    _cleanup()
    try:
        project_res = client.post(
            "/api/v1/projects", json={"name": TEST_PROJECT_NAME}, headers=auth_headers
        )
        assert project_res.status_code == 201
        project_id = uuid.UUID(project_res.json()["id"])

        with SessionLocal() as db:
            tenant_id = db.get(Project, project_id).tenant_id
            staff = auth_service.create_user(
                db,
                tenant_id=tenant_id,
                name="Pytest Sprint 024 Staff",
                email=STAFF_EMAIL,
                password=STAFF_PASSWORD,
                role="Staff",
            )
            staff_id = staff.id

        assign_res = client.patch(
            f"/api/v1/projects/{project_id}/assign",
            json={"assigned_user_id": str(staff_id)},
            headers=auth_headers,
        )
        assert assign_res.status_code == 200

        with SessionLocal() as db:
            project = db.get(Project, project_id)
            assert project.status == "enquiry"
            created_at = project.created_at

        from app.notifications.follow_up_service import follow_up_service

        with SessionLocal() as db:
            result = follow_up_service.run(db, now=STALE_NOW(created_at))

        assert result.created == 1

        with SessionLocal() as db:
            notifications = (
                db.query(NotificationRecord)
                .filter(NotificationRecord.source_id == project_id)
                .all()
            )
        assert len(notifications) == 1
        notification = notifications[0]
        assert notification.tenant_id == tenant_id
        assert notification.recipient_user_id == staff_id
        assert notification.source_type == "project"
        assert notification.source_id == project_id
        assert notification.type == "warning"
        assert notification.read is False
        assert notification.dedupe_key == f"stale_enquiry_follow_up:{project_id}"
    finally:
        _cleanup()
