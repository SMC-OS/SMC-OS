"""Sprint 023 — Project Operations (staff assignment + validated status
transitions). See docs/SPRINTS/sprint-023.md for the locked contract.
Structural twin of tests/test_appointments.py's full TDD sequence (Sprint
022) — create, tenant isolation, RBAC, activity, and transaction atomicity,
for both the new assignment route and the tightened status route.
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.activity.service import activity_service
from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Project, User

TEST_PREFIX = "Pytest Sprint 023"
TEST_PROJECT_NAME = f"{TEST_PREFIX} Project"
STAFF_EMAIL = "pytest-sprint023-staff@example.invalid"
STAFF_PASSWORD = "pytest-sprint023-staff-password"
NO_ROLE_EMAIL = "pytest-sprint023-no-role@example.invalid"
NO_ROLE_PASSWORD = "pytest-sprint023-no-role-password"

TEST_CROSS_TENANT_PROJECT_NAME = f"{TEST_PREFIX} Cross-Tenant Project"
TEST_TRANSITION_PROJECT_NAME = f"{TEST_PREFIX} Transition Project"
TEST_RBAC_PROJECT_NAME = f"{TEST_PREFIX} RBAC Project"
TEST_ACTIVITY_PROJECT_NAME = f"{TEST_PREFIX} Activity Project"
TEST_ATOMICITY_PROJECT_NAME = f"{TEST_PREFIX} Atomicity Project"

ALL_TEST_PROJECT_NAMES = [
    TEST_PROJECT_NAME,
    TEST_CROSS_TENANT_PROJECT_NAME,
    TEST_TRANSITION_PROJECT_NAME,
    TEST_RBAC_PROJECT_NAME,
    TEST_ACTIVITY_PROJECT_NAME,
    TEST_ATOMICITY_PROJECT_NAME,
]


def _cleanup() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Project).where(Project.name.in_(ALL_TEST_PROJECT_NAMES)))
        db.execute(delete(ActivityLog).where(ActivityLog.title.like(f"{TEST_PREFIX}%")))
        db.execute(delete(User).where(User.email.in_([STAFF_EMAIL, NO_ROLE_EMAIL])))
        db.commit()
    finally:
        db.close()


def _create_booked_project(client, headers: dict[str, str], name: str = TEST_PROJECT_NAME) -> dict:
    project = client.post("/api/v1/projects", json={"name": name}, headers=headers)
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


def _create_same_tenant_staff(tenant_id) -> str:
    with SessionLocal() as db:
        staff = auth_service.create_user(
            db,
            tenant_id=tenant_id,
            name="Pytest Sprint 023 Staff",
            email=STAFF_EMAIL,
            password=STAFF_PASSWORD,
            role="Staff",
        )
        return str(staff.id)


def test_owner_can_assign_a_same_tenant_staff_member_to_a_booked_project(client, auth_headers):
    """First Sprint 023 contract: an OWNER caller assigns a same-tenant
    Staff member to their own booked Project."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
        staff_id = _create_same_tenant_staff(tenant_id)

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


def test_owner_can_unassign_a_project(client, auth_headers):
    """assigned_user_id: null is a valid, explicit unassignment."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
        staff_id = _create_same_tenant_staff(tenant_id)

        first = client.patch(
            f"/api/v1/projects/{project['id']}/assign",
            json={"assigned_user_id": staff_id},
            headers=auth_headers,
        )
        assert first.status_code == 200

        second = client.patch(
            f"/api/v1/projects/{project['id']}/assign",
            json={"assigned_user_id": None},
            headers=auth_headers,
        )
        assert second.status_code == 200
        assert second.json()["assigned_user_id"] is None

        with SessionLocal() as db:
            persisted = db.get(Project, uuid.UUID(project["id"]))
            assert persisted.assigned_user_id is None
    finally:
        _cleanup()


def test_assigning_another_tenants_user_returns_404(client, auth_headers, other_tenant_auth_headers):
    """Tenant invariant (sprint-023.md §5): the target user must belong to
    the same tenant as the Project."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers)

        other_me = client.get("/api/v1/auth/me", headers=other_tenant_auth_headers)
        assert other_me.status_code == 200
        other_user_id = other_me.json()["id"]

        response = client.patch(
            f"/api/v1/projects/{project['id']}/assign",
            json={"assigned_user_id": other_user_id},
            headers=auth_headers,
        )

        assert response.status_code == 404

        with SessionLocal() as db:
            persisted = db.get(Project, uuid.UUID(project["id"]))
            assert persisted.assigned_user_id is None
    finally:
        _cleanup()


def test_assign_project_of_another_tenant_returns_404(client, auth_headers, other_tenant_auth_headers):
    """Tenant B must not be able to assign staff to Tenant A's Project —
    same tenant-scoped-lookup-hides-existence convention as every
    relationship check in this codebase (ADR-029)."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_CROSS_TENANT_PROJECT_NAME)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
        staff_id = _create_same_tenant_staff(tenant_id)

        response = client.patch(
            f"/api/v1/projects/{project['id']}/assign",
            json={"assigned_user_id": staff_id},
            headers=other_tenant_auth_headers,
        )

        assert response.status_code == 404
    finally:
        _cleanup()


def test_same_tenant_staff_cannot_assign(client, auth_headers):
    """RBAC (Decision 2): assignment is Owner-only. A same-tenant Staff
    caller must not be able to assign — not even themselves."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_RBAC_PROJECT_NAME)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
        staff_id = _create_same_tenant_staff(tenant_id)

        login = client.post(
            "/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}
        )
        assert login.status_code == 200
        staff_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = client.patch(
            f"/api/v1/projects/{project['id']}/assign",
            json={"assigned_user_id": staff_id},
            headers=staff_headers,
        )

        assert response.status_code == 403

        with SessionLocal() as db:
            persisted = db.get(Project, uuid.UUID(project["id"]))
            assert persisted.assigned_user_id is None
    finally:
        _cleanup()


def test_successful_assignment_logs_exactly_one_project_assigned_activity(client, auth_headers):
    """Activity contract (sprint-023.md §5): assignment is audited through
    the existing ActivityLog infrastructure as its own domain event type."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_ACTIVITY_PROJECT_NAME)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
        staff_id = _create_same_tenant_staff(tenant_id)

        with SessionLocal() as db:
            activity_count_before = db.query(ActivityLog).filter_by(tenant_id=tenant_id).count()

        response = client.patch(
            f"/api/v1/projects/{project['id']}/assign",
            json={"assigned_user_id": staff_id},
            headers=auth_headers,
        )
        assert response.status_code == 200

        with SessionLocal() as db:
            activities = list(
                db.scalars(
                    select(ActivityLog)
                    .where(ActivityLog.tenant_id == tenant_id)
                    .order_by(ActivityLog.timestamp.desc())
                )
            )
        assert len(activities) == activity_count_before + 1
        assert activities[0].type == "project_assigned"
    finally:
        _cleanup()


def test_assignment_rolls_back_if_activity_logging_fails(client, auth_headers, monkeypatch):
    """Transaction-atomicity contract: the assignment write and its
    activity log are one logical transaction — same pattern and reasoning
    as tests/test_appointments.py's equivalent atomicity test."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_ATOMICITY_PROJECT_NAME)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
        staff_id = _create_same_tenant_staff(tenant_id)

        def fail_activity_log(*args, **kwargs):
            raise RuntimeError("synthetic activity failure")

        monkeypatch.setattr(activity_service, "log", fail_activity_log)

        with pytest.raises(RuntimeError, match="synthetic activity failure"):
            client.patch(
                f"/api/v1/projects/{project['id']}/assign",
                json={"assigned_user_id": staff_id},
                headers=auth_headers,
            )

        with SessionLocal() as db:
            persisted = db.get(Project, uuid.UUID(project["id"]))
            assert persisted.assigned_user_id is None
    finally:
        _cleanup()


def test_valid_forward_status_transition_still_succeeds_for_owner(client, auth_headers):
    """Regression lock: a valid single-step-forward transition still
    succeeds now that RBAC and validation are enforced (booked ->
    templated is the next contract this sprint adds beyond the pre-existing
    enquiry -> quoted -> booked sequence _create_booked_project already
    exercises)."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_TRANSITION_PROJECT_NAME)

        response = client.patch(
            f"/api/v1/projects/{project['id']}/status",
            json={"status": "templated"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "templated"
    finally:
        _cleanup()


def test_skipping_a_status_stage_returns_409(client, auth_headers):
    """Decision 4 / §4: only the exact next value is valid — a skip is a
    real conflict, not silently clamped or allowed."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_TRANSITION_PROJECT_NAME)

        response = client.patch(
            f"/api/v1/projects/{project['id']}/status",
            json={"status": "fabricated"},
            headers=auth_headers,
        )

        assert response.status_code == 409

        with SessionLocal() as db:
            persisted = db.get(Project, uuid.UUID(project["id"]))
            assert persisted.status == "booked"
    finally:
        _cleanup()


def test_reverting_a_status_backward_returns_409(client, auth_headers):
    """No arbitrary status jumping — backward moves are rejected too."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_TRANSITION_PROJECT_NAME)

        response = client.patch(
            f"/api/v1/projects/{project['id']}/status",
            json={"status": "quoted"},
            headers=auth_headers,
        )

        assert response.status_code == 409
    finally:
        _cleanup()


def test_repeating_the_current_status_returns_409(client, auth_headers):
    """Decision 4: a same-status repeat is a real conflict here, not an
    idempotent no-op — no UI path would ever submit it."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_TRANSITION_PROJECT_NAME)

        response = client.patch(
            f"/api/v1/projects/{project['id']}/status",
            json={"status": "booked"},
            headers=auth_headers,
        )

        assert response.status_code == 409
    finally:
        _cleanup()


def test_transition_from_complete_is_rejected(client, auth_headers):
    """complete is terminal — no further transition is valid from it."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_TRANSITION_PROJECT_NAME)
        project_id = project["id"]

        for target in ("templated", "fabricated", "installed", "complete"):
            step = client.patch(
                f"/api/v1/projects/{project_id}/status",
                json={"status": target},
                headers=auth_headers,
            )
            assert step.status_code == 200

        response = client.patch(
            f"/api/v1/projects/{project_id}/status",
            json={"status": "complete"},
            headers=auth_headers,
        )
        assert response.status_code == 409
    finally:
        _cleanup()


def test_status_transition_of_another_tenants_project_returns_404(
    client, auth_headers, other_tenant_auth_headers
):
    """Regression lock: cross-tenant status transition already 404s via
    the existing tenant-scoped get_project_by_id lookup."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_CROSS_TENANT_PROJECT_NAME)

        response = client.patch(
            f"/api/v1/projects/{project['id']}/status",
            json={"status": "templated"},
            headers=other_tenant_auth_headers,
        )

        assert response.status_code == 404
    finally:
        _cleanup()


def test_same_tenant_user_without_owner_staff_role_cannot_advance_status(client, auth_headers):
    """RBAC: closes the zero-RBAC gap found in discovery — role=None must
    not be able to advance a Project's status."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_RBAC_PROJECT_NAME)

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
            "/api/v1/auth/login", json={"email": NO_ROLE_EMAIL, "password": NO_ROLE_PASSWORD}
        )
        assert login.status_code == 200
        no_role_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = client.patch(
            f"/api/v1/projects/{project['id']}/status",
            json={"status": "templated"},
            headers=no_role_headers,
        )

        assert response.status_code == 403

        with SessionLocal() as db:
            persisted = db.get(Project, uuid.UUID(project["id"]))
            assert persisted.status == "booked"
    finally:
        _cleanup()


def test_staff_can_advance_status(client, auth_headers):
    """RBAC: Staff, not just Owner, can advance status (§7's summary
    table)."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_RBAC_PROJECT_NAME)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
        staff_id = _create_same_tenant_staff(tenant_id)

        login = client.post(
            "/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}
        )
        assert login.status_code == 200
        staff_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = client.patch(
            f"/api/v1/projects/{project['id']}/status",
            json={"status": "templated"},
            headers=staff_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "templated"
        assert staff_id  # created for realism/consistency with other tests
    finally:
        _cleanup()


def test_successful_status_transition_logs_exactly_one_project_status_changed_activity(
    client, auth_headers
):
    """Activity contract (sprint-023.md §4)."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_ACTIVITY_PROJECT_NAME)

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project["id"])).tenant_id
            activity_count_before = db.query(ActivityLog).filter_by(tenant_id=tenant_id).count()

        response = client.patch(
            f"/api/v1/projects/{project['id']}/status",
            json={"status": "templated"},
            headers=auth_headers,
        )
        assert response.status_code == 200

        with SessionLocal() as db:
            activities = list(
                db.scalars(
                    select(ActivityLog)
                    .where(ActivityLog.tenant_id == tenant_id)
                    .order_by(ActivityLog.timestamp.desc())
                )
            )
        assert len(activities) == activity_count_before + 1
        assert activities[0].type == "project_status_changed"
    finally:
        _cleanup()


def test_status_transition_rolls_back_if_activity_logging_fails(client, auth_headers, monkeypatch):
    """Transaction-atomicity contract for the status route."""
    _cleanup()
    try:
        project = _create_booked_project(client, auth_headers, TEST_ATOMICITY_PROJECT_NAME)

        def fail_activity_log(*args, **kwargs):
            raise RuntimeError("synthetic activity failure")

        monkeypatch.setattr(activity_service, "log", fail_activity_log)

        with pytest.raises(RuntimeError, match="synthetic activity failure"):
            client.patch(
                f"/api/v1/projects/{project['id']}/status",
                json={"status": "templated"},
                headers=auth_headers,
            )

        with SessionLocal() as db:
            persisted = db.get(Project, uuid.UUID(project["id"]))
            assert persisted.status == "booked"
    finally:
        _cleanup()
