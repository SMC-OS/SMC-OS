"""Sprint 022 — Appointment / Site Visit Scheduling.

See docs/SPRINTS/sprint-022.md for the locked contract. Structural twin of
tests/test_enquiry_conversion.py's full TDD sequence (Sprint 021) — create,
list/read, status transitions, tenant isolation, RBAC, activity, and
transaction atomicity, in that order.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.activity.service import activity_service
from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Appointment, Project, User

TEST_PREFIX = "Pytest Sprint 022"
TEST_PROJECT_NAME = f"{TEST_PREFIX} Project"
TEST_NOTES = f"{TEST_PREFIX} Site Visit Notes"

TEST_LIST_PROJECT_NAME = f"{TEST_PREFIX} List Project"

TEST_TRANSITION_PROJECT_NAME = f"{TEST_PREFIX} Transition Project"

TEST_CROSS_TENANT_PROJECT_NAME = f"{TEST_PREFIX} Cross-Tenant Project"

TEST_RBAC_PROJECT_NAME = f"{TEST_PREFIX} RBAC Project"
NO_ROLE_EMAIL = "pytest-sprint022-no-role@example.invalid"
NO_ROLE_PASSWORD = "pytest-sprint022-no-role-password"

TEST_ACTIVITY_PROJECT_NAME = f"{TEST_PREFIX} Activity Project"

TEST_ATOMICITY_PROJECT_NAME = f"{TEST_PREFIX} Atomicity Project"

TEST_ATOMICITY_TRANSITION_PROJECT_NAME = f"{TEST_PREFIX} Atomicity Transition Project"

ALL_TEST_PROJECT_NAMES = [
    TEST_PROJECT_NAME,
    TEST_LIST_PROJECT_NAME,
    TEST_TRANSITION_PROJECT_NAME,
    TEST_CROSS_TENANT_PROJECT_NAME,
    TEST_RBAC_PROJECT_NAME,
    TEST_ACTIVITY_PROJECT_NAME,
    TEST_ATOMICITY_PROJECT_NAME,
    TEST_ATOMICITY_TRANSITION_PROJECT_NAME,
]


def _cleanup() -> None:
    db = SessionLocal()
    try:
        project_ids = db.scalars(
            select(Project.id).where(Project.name.in_(ALL_TEST_PROJECT_NAMES))
        ).all()
        if project_ids:
            db.execute(delete(Appointment).where(Appointment.project_id.in_(project_ids)))
        db.execute(delete(Project).where(Project.name.in_(ALL_TEST_PROJECT_NAMES)))
        db.execute(delete(ActivityLog).where(ActivityLog.title.like(f"{TEST_PREFIX}%")))
        db.execute(delete(User).where(User.email == NO_ROLE_EMAIL))
        db.commit()
    finally:
        db.close()


def _future_iso(days: int = 3) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _create_project(client, headers, name: str) -> dict:
    response = client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()


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
        project = _create_project(client, auth_headers, TEST_PROJECT_NAME)
        project_id = project["id"]

        with SessionLocal() as db:
            expected_tenant_id = db.get(Project, uuid.UUID(project_id)).tenant_id

        scheduled_at = _future_iso()

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


def test_create_appointment_rejects_naive_scheduled_at(client, auth_headers):
    """Decision 5 (sprint-022.md): a client-supplied scheduled_at with no
    timezone information is rejected with 422, not silently assumed to be
    any particular timezone."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_PROJECT_NAME)

        naive = (datetime.now() + timedelta(days=3)).isoformat()

        response = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": naive},
            headers=auth_headers,
        )

        assert response.status_code == 422
    finally:
        _cleanup()


def test_list_appointments_for_a_project_returns_them_ordered_by_scheduled_at_ascending(
    client, auth_headers
):
    """List contract (sprint-022.md): GET returns every Appointment for the
    Project, ordered scheduled_at ASC — not creation order."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_LIST_PROJECT_NAME)
        project_id = project["id"]

        later = _future_iso(days=10)
        sooner = _future_iso(days=2)

        later_response = client.post(
            f"/api/v1/projects/{project_id}/appointments",
            json={"scheduled_at": later},
            headers=auth_headers,
        )
        assert later_response.status_code == 201

        sooner_response = client.post(
            f"/api/v1/projects/{project_id}/appointments",
            json={"scheduled_at": sooner},
            headers=auth_headers,
        )
        assert sooner_response.status_code == 201

        listing = client.get(
            f"/api/v1/projects/{project_id}/appointments", headers=auth_headers
        )
        assert listing.status_code == 200
        body = listing.json()
        assert len(body) == 2
        assert body[0]["id"] == sooner_response.json()["id"]
        assert body[1]["id"] == later_response.json()["id"]
    finally:
        _cleanup()


def test_create_appointment_against_another_tenants_project_returns_404(
    client, auth_headers, other_tenant_auth_headers
):
    """Tenant B must not be able to schedule a site visit against Tenant
    A's Project — same tenant-scoped-lookup-hides-existence convention as
    every relationship check in this codebase (ADR-029)."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_CROSS_TENANT_PROJECT_NAME)

        response = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": _future_iso()},
            headers=other_tenant_auth_headers,
        )

        assert response.status_code == 404

        with SessionLocal() as db:
            count = (
                db.query(Appointment)
                .filter(Appointment.project_id == uuid.UUID(project["id"]))
                .count()
            )
            assert count == 0
    finally:
        _cleanup()


def test_list_appointments_for_another_tenants_project_returns_404(
    client, auth_headers, other_tenant_auth_headers
):
    """Same tenant-isolation convention for the list route."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_CROSS_TENANT_PROJECT_NAME)

        response = client.get(
            f"/api/v1/projects/{project['id']}/appointments",
            headers=other_tenant_auth_headers,
        )

        assert response.status_code == 404
    finally:
        _cleanup()


def test_same_tenant_user_without_owner_staff_role_cannot_create_appointment(
    client, auth_headers
):
    """RBAC (not tenant isolation): a same-tenant, authenticated user who is
    neither OWNER nor STAFF must not be able to schedule a site visit.
    role=None is the repository's real "no role assigned" state — see
    tests/test_enquiry_conversion.py's
    test_same_tenant_user_without_owner_staff_role_cannot_convert_enquiry,
    the direct template for this test."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_RBAC_PROJECT_NAME)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
            auth_service.create_user(
                db,
                tenant_id=tenant_id,
                name="Pytest No-Role User",
                email=NO_ROLE_EMAIL,
                password=NO_ROLE_PASSWORD,
            )

        login = client.post(
            "/api/v1/auth/login",
            json={"email": NO_ROLE_EMAIL, "password": NO_ROLE_PASSWORD},
        )
        assert login.status_code == 200
        no_role_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": _future_iso()},
            headers=no_role_headers,
        )

        assert response.status_code == 403

        with SessionLocal() as db:
            count = (
                db.query(Appointment)
                .filter(Appointment.project_id == uuid.UUID(project["id"]))
                .count()
            )
            assert count == 0
    finally:
        _cleanup()


def test_appointment_can_transition_to_completed_and_then_repeat_call_is_idempotent(
    client, auth_headers
):
    """Status-transition contract (Decision 2/3, sprint-022.md): a
    scheduled appointment can transition to completed. A repeat call with
    the same terminal target is idempotent (200, no mutation, no second
    activity) rather than an error."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_TRANSITION_PROJECT_NAME)
        created = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": _future_iso()},
            headers=auth_headers,
        )
        assert created.status_code == 201
        appointment_id = created.json()["id"]

        first = client.patch(
            f"/api/v1/appointments/{appointment_id}/status",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert first.status_code == 200
        assert first.json()["status"] == "completed"

        second = client.patch(
            f"/api/v1/appointments/{appointment_id}/status",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert second.status_code == 200
        assert second.json()["status"] == "completed"
    finally:
        _cleanup()


def test_completed_appointment_cannot_transition_to_cancelled(client, auth_headers):
    """A terminal appointment (completed) transitioning to the *other*
    terminal status (cancelled) is a real conflict, not an idempotent
    retry — 409, not 200."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_TRANSITION_PROJECT_NAME)
        created = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": _future_iso()},
            headers=auth_headers,
        )
        assert created.status_code == 201
        appointment_id = created.json()["id"]

        completed = client.patch(
            f"/api/v1/appointments/{appointment_id}/status",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert completed.status_code == 200

        conflict = client.patch(
            f"/api/v1/appointments/{appointment_id}/status",
            json={"status": "cancelled"},
            headers=auth_headers,
        )
        assert conflict.status_code == 409

        with SessionLocal() as db:
            persisted = db.get(Appointment, uuid.UUID(appointment_id))
            assert persisted.status == "completed"
    finally:
        _cleanup()


def test_status_update_for_another_tenants_appointment_returns_404(
    client, auth_headers, other_tenant_auth_headers
):
    """Same tenant-isolation convention for the status-transition route."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_CROSS_TENANT_PROJECT_NAME)
        created = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": _future_iso()},
            headers=auth_headers,
        )
        assert created.status_code == 201
        appointment_id = created.json()["id"]

        response = client.patch(
            f"/api/v1/appointments/{appointment_id}/status",
            json={"status": "completed"},
            headers=other_tenant_auth_headers,
        )

        assert response.status_code == 404

        with SessionLocal() as db:
            persisted = db.get(Appointment, uuid.UUID(appointment_id))
            assert persisted.status == "scheduled"
    finally:
        _cleanup()


def test_same_tenant_user_without_owner_staff_role_cannot_update_appointment_status(
    client, auth_headers
):
    """RBAC negative for the status-transition route, same convention as
    the create-route RBAC test above."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_RBAC_PROJECT_NAME)
        created = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": _future_iso()},
            headers=auth_headers,
        )
        assert created.status_code == 201
        appointment_id = created.json()["id"]

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
            auth_service.create_user(
                db,
                tenant_id=tenant_id,
                name="Pytest No-Role User",
                email=NO_ROLE_EMAIL,
                password=NO_ROLE_PASSWORD,
            )

        login = client.post(
            "/api/v1/auth/login",
            json={"email": NO_ROLE_EMAIL, "password": NO_ROLE_PASSWORD},
        )
        assert login.status_code == 200
        no_role_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = client.patch(
            f"/api/v1/appointments/{appointment_id}/status",
            json={"status": "completed"},
            headers=no_role_headers,
        )

        assert response.status_code == 403

        with SessionLocal() as db:
            persisted = db.get(Appointment, uuid.UUID(appointment_id))
            assert persisted.status == "scheduled"
    finally:
        _cleanup()


def test_successful_appointment_creation_logs_exactly_one_site_visit_scheduled_activity(
    client, auth_headers
):
    """Activity contract (sprint-022.md): creating an appointment must be
    audited through the existing ActivityLog infrastructure — same
    mechanism as enquiry_converted (Sprint 021) — as its own domain event
    type, site_visit_scheduled."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_ACTIVITY_PROJECT_NAME)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
            activity_count_before = db.query(ActivityLog).filter_by(tenant_id=tenant_id).count()

        response = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": _future_iso()},
            headers=auth_headers,
        )
        assert response.status_code == 201

        with SessionLocal() as db:
            activities = list(
                db.scalars(
                    select(ActivityLog)
                    .where(ActivityLog.tenant_id == tenant_id)
                    .order_by(ActivityLog.timestamp.desc())
                )
            )
        assert len(activities) == activity_count_before + 1
        assert activities[0].type == "site_visit_scheduled"
        assert activities[0].tenant_id == tenant_id
    finally:
        _cleanup()


def test_completing_an_appointment_logs_exactly_one_site_visit_completed_activity(
    client, auth_headers
):
    """Activity contract for the transition route: completing an
    appointment logs site_visit_completed, and an idempotent repeat call
    (already asserted 200-and-unchanged above) must not log a second one."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_ACTIVITY_PROJECT_NAME)
        created = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": _future_iso()},
            headers=auth_headers,
        )
        assert created.status_code == 201
        appointment_id = created.json()["id"]

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
            activity_count_before = db.query(ActivityLog).filter_by(tenant_id=tenant_id).count()

        first = client.patch(
            f"/api/v1/appointments/{appointment_id}/status",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert first.status_code == 200

        second = client.patch(
            f"/api/v1/appointments/{appointment_id}/status",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert second.status_code == 200

        with SessionLocal() as db:
            activities = list(
                db.scalars(
                    select(ActivityLog)
                    .where(ActivityLog.tenant_id == tenant_id)
                    .order_by(ActivityLog.timestamp.desc())
                )
            )
        assert len(activities) == activity_count_before + 1
        assert activities[0].type == "site_visit_completed"
    finally:
        _cleanup()


def test_appointment_creation_rolls_back_if_activity_logging_fails(
    client, auth_headers, monkeypatch
):
    """Transaction-atomicity contract: creating the Appointment row and
    logging site_visit_scheduled are one logical domain transaction. If the
    final step (activity logging) fails, the Appointment must not survive —
    same pattern and reasoning as
    tests/test_enquiry_conversion.py's
    test_conversion_rolls_back_customer_and_project_link_if_activity_logging_fails."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_ATOMICITY_PROJECT_NAME)

        with SessionLocal() as db:
            appointment_count_before = (
                db.query(Appointment)
                .filter(Appointment.project_id == uuid.UUID(project["id"]))
                .count()
            )

        def fail_activity_log(*args, **kwargs):
            raise RuntimeError("synthetic activity failure")

        monkeypatch.setattr(activity_service, "log", fail_activity_log)

        with pytest.raises(RuntimeError, match="synthetic activity failure"):
            client.post(
                f"/api/v1/projects/{project['id']}/appointments",
                json={"scheduled_at": _future_iso()},
                headers=auth_headers,
            )

        with SessionLocal() as db:
            appointment_count_after = (
                db.query(Appointment)
                .filter(Appointment.project_id == uuid.UUID(project["id"]))
                .count()
            )
            assert appointment_count_after == appointment_count_before
    finally:
        _cleanup()


def test_appointment_status_transition_rolls_back_if_activity_logging_fails(
    client, auth_headers, monkeypatch
):
    """Transaction-atomicity contract for the transition route: updating
    Appointment.status and logging site_visit_completed are one logical
    domain transaction. If the final step fails, the status change must not
    survive."""
    _cleanup()
    try:
        project = _create_project(client, auth_headers, TEST_ATOMICITY_TRANSITION_PROJECT_NAME)
        created = client.post(
            f"/api/v1/projects/{project['id']}/appointments",
            json={"scheduled_at": _future_iso()},
            headers=auth_headers,
        )
        assert created.status_code == 201
        appointment_id = created.json()["id"]

        def fail_activity_log(*args, **kwargs):
            raise RuntimeError("synthetic activity failure")

        monkeypatch.setattr(activity_service, "log", fail_activity_log)

        with pytest.raises(RuntimeError, match="synthetic activity failure"):
            client.patch(
                f"/api/v1/appointments/{appointment_id}/status",
                json={"status": "completed"},
                headers=auth_headers,
            )

        with SessionLocal() as db:
            persisted = db.get(Appointment, uuid.UUID(appointment_id))
            assert persisted.status == "scheduled"
    finally:
        _cleanup()
