"""Sprint 021 — Enquiry (a project at a `lead`-role stage) to Customer
conversion. Sprint 039 moved the gate from the literal status "enquiry"
onto the stage's trade-neutral role, so this reads the same for a stone
tenant (whose lead stage is "enquiry") and a standard one (whose is
"lead"); these tests run against the latter.

See docs/SPRINTS/sprint-021.md for the locked contract this test implements
the first RED cycle of. Same route-level-client test pattern as
tests/test_quote_handoff.py (Sprint 020's Quote->Project handoff, the direct
template for this Project->Customer conversion).
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.activity.service import activity_service
from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Project, User

TEST_PREFIX = "Pytest Sprint 021"
TEST_PROJECT_NAME = f"{TEST_PREFIX} Project"
TEST_CUSTOMER_NAME = f"{TEST_PREFIX} Customer"
TEST_CUSTOMER_EMAIL = "pytest-sprint021-customer@example.invalid"
TEST_CUSTOMER_PHONE = "+44 7000 000021"

# Distinct name/project/email from the happy-path test above, so this test's
# "exactly one Customer" count is deterministic and never entangled with the
# happy-path test's own rows, regardless of run order.
TEST_RETRY_PROJECT_NAME = f"{TEST_PREFIX} Retry Project"
TEST_RETRY_CUSTOMER_NAME = f"{TEST_PREFIX} Retry Customer"
TEST_RETRY_CUSTOMER_EMAIL = "pytest-sprint021-retry-customer@example.invalid"
TEST_RETRY_CUSTOMER_PHONE = "+44 7000 000022"

# Distinct name/project/email again, for the non-enquiry lifecycle-guard
# test below — its own unique rows, never entangled with the other two
# tests' counts.
TEST_NON_ENQUIRY_PROJECT_NAME = f"{TEST_PREFIX} Non-Enquiry Project"
TEST_NON_ENQUIRY_CUSTOMER_NAME = f"{TEST_PREFIX} Non-Enquiry Customer"
TEST_NON_ENQUIRY_CUSTOMER_EMAIL = "pytest-sprint021-non-enquiry-customer@example.invalid"
TEST_NON_ENQUIRY_CUSTOMER_PHONE = "+44 7000 000023"
TEST_NON_ENQUIRY_STATUS = "quoted"
# Sprint 023 (docs/SPRINTS/sprint-023.md §4): status transitions are now
# strictly the exact next value in the pipeline, so this must be the one
# status immediately after "enquiry" — any later stage would need an
# intermediate transition first. Only "not enquiry" matters to this test's
# purpose (conversion is rejected once a Project has left the enquiry
# stage); which specific later status was never load-bearing.

# Distinct name/project/email again, for the cross-tenant isolation test
# below — its own unique rows, never entangled with the other tests' counts.
TEST_CROSS_TENANT_PROJECT_NAME = f"{TEST_PREFIX} Cross-Tenant Project"
TEST_CROSS_TENANT_CUSTOMER_NAME = f"{TEST_PREFIX} Cross-Tenant Customer"
TEST_CROSS_TENANT_CUSTOMER_EMAIL = "pytest-sprint021-cross-tenant-customer@example.invalid"
TEST_CROSS_TENANT_CUSTOMER_PHONE = "+44 7000 000024"

# Distinct name/project/email again, for the RBAC-negative test below — its
# own unique rows, never entangled with the other tests' counts. Same
# no-role-user shape as tests/test_quote_handoff.py's NO_ROLE_EMAIL/PASSWORD.
TEST_RBAC_PROJECT_NAME = f"{TEST_PREFIX} RBAC Project"
TEST_RBAC_CUSTOMER_NAME = f"{TEST_PREFIX} RBAC Customer"
TEST_RBAC_CUSTOMER_EMAIL = "pytest-sprint021-rbac-customer@example.invalid"
TEST_RBAC_CUSTOMER_PHONE = "+44 7000 000025"
NO_ROLE_EMAIL = "pytest-sprint021-no-role@example.invalid"
NO_ROLE_PASSWORD = "pytest-sprint021-no-role-password"

# Distinct name/project/email again, for the activity test below — its own
# unique rows, never entangled with the other tests' counts.
TEST_ACTIVITY_PROJECT_NAME = f"{TEST_PREFIX} Activity Project"
TEST_ACTIVITY_CUSTOMER_NAME = f"{TEST_PREFIX} Activity Customer"
TEST_ACTIVITY_CUSTOMER_EMAIL = "pytest-sprint021-activity-customer@example.invalid"
TEST_ACTIVITY_CUSTOMER_PHONE = "+44 7000 000026"

# Distinct name/project/email again, for the transaction-atomicity test
# below — its own unique rows, never entangled with the other tests' counts.
TEST_ATOMICITY_PROJECT_NAME = f"{TEST_PREFIX} Atomicity Project"
TEST_ATOMICITY_CUSTOMER_NAME = f"{TEST_PREFIX} Atomicity Customer"
TEST_ATOMICITY_CUSTOMER_EMAIL = "pytest-sprint021-atomicity-customer@example.invalid"
TEST_ATOMICITY_CUSTOMER_PHONE = "+44 7000 000027"


def _cleanup() -> None:
    db = SessionLocal()
    try:
        # Projects must go before their Customer — Project.customer_id has
        # no ON DELETE CASCADE (same ordering as tests/test_quote_handoff.py).
        db.execute(
            delete(Project).where(
                Project.name.in_(
                    [
                        TEST_PROJECT_NAME,
                        TEST_RETRY_PROJECT_NAME,
                        TEST_NON_ENQUIRY_PROJECT_NAME,
                        TEST_CROSS_TENANT_PROJECT_NAME,
                        TEST_RBAC_PROJECT_NAME,
                        TEST_ACTIVITY_PROJECT_NAME,
                        TEST_ATOMICITY_PROJECT_NAME,
                    ]
                )
            )
        )
        db.execute(delete(ActivityLog).where(ActivityLog.title.like(f"{TEST_PREFIX}%")))
        db.execute(
            delete(Customer).where(
                Customer.name.in_(
                    [
                        TEST_CUSTOMER_NAME,
                        TEST_RETRY_CUSTOMER_NAME,
                        TEST_NON_ENQUIRY_CUSTOMER_NAME,
                        TEST_CROSS_TENANT_CUSTOMER_NAME,
                        TEST_RBAC_CUSTOMER_NAME,
                        TEST_ACTIVITY_CUSTOMER_NAME,
                        TEST_ATOMICITY_CUSTOMER_NAME,
                    ]
                )
            )
        )
        db.execute(delete(User).where(User.email == NO_ROLE_EMAIL))
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
    # Sprint 039 — asserted on the trade-neutral role. Which key this
    # workspace's opening stage carries depends on its pipeline; that a new
    # job starts there does not.
    assert body["status_role"] == "lead"
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
            assert persisted_project.status == "lead"

            customers_after = db.query(Customer).filter_by(name=TEST_CUSTOMER_NAME).count()
            assert customers_after == customers_before + 1
    finally:
        _cleanup()


def test_repeat_conversion_returns_the_same_customer_without_creating_another(
    client, auth_headers
):
    """Sprint 021 project-level idempotency contract (docs/SPRINTS/sprint-021.md
    §4, Decision 2): calling convert-to-customer a second time on the same
    Project must not create a second Customer or re-link the Project — it
    must load and return the already-linked Customer, 200, unchanged. Normal
    retry/double-click behavior must return the same Customer. Non-enquiry
    409, cross-tenant 404, RBAC 403, activity, global dedupe, transaction
    atomicity, and frontend are later RED/GREEN cycles, not this one."""
    _cleanup()
    try:
        project = client.post(
            "/api/v1/projects",
            json={"name": TEST_RETRY_PROJECT_NAME},
            headers=auth_headers,
        )
        assert project.status_code == 201
        project_body = project.json()
        assert project_body["status_role"] == "lead"
        assert project_body["customer_id"] is None

        payload = {
            "name": TEST_RETRY_CUSTOMER_NAME,
            "email": TEST_RETRY_CUSTOMER_EMAIL,
            "phone": TEST_RETRY_CUSTOMER_PHONE,
        }

        first = client.post(
            f"/api/v1/projects/{project_body['id']}/convert-to-customer",
            json=payload,
            headers=auth_headers,
        )
        assert first.status_code == 200
        first_customer = first.json()

        second = client.post(
            f"/api/v1/projects/{project_body['id']}/convert-to-customer",
            json=payload,
            headers=auth_headers,
        )
        assert second.status_code == 200
        second_customer = second.json()

        assert second_customer["id"] == first_customer["id"]

        with SessionLocal() as db:
            persisted_project = db.get(Project, uuid.UUID(project_body["id"]))
            assert str(persisted_project.customer_id) == first_customer["id"]
            assert persisted_project.status == "lead"

            customer_count = (
                db.query(Customer).filter_by(name=TEST_RETRY_CUSTOMER_NAME).count()
            )
            assert customer_count == 1
    finally:
        _cleanup()


def test_conversion_rejects_a_non_enquiry_project(client, auth_headers):
    """Sprint 021 lifecycle-state guard (docs/SPRINTS/sprint-021.md §4,
    Decision 1): conversion is only allowed when Project.status == "enquiry".
    A Project already advanced past that (here: "booked", a real
    ProjectStatus member) must be rejected with 409 — no Customer created, no
    link, no status mutation. Cross-tenant 404, RBAC 403, activity,
    transaction atomicity, frontend, e2e, and global dedupe are later
    RED/GREEN cycles, not this one."""
    _cleanup()
    try:
        project = client.post(
            "/api/v1/projects",
            json={"name": TEST_NON_ENQUIRY_PROJECT_NAME},
            headers=auth_headers,
        )
        assert project.status_code == 201
        project_body = project.json()
        assert project_body["customer_id"] is None

        advanced = client.patch(
            f"/api/v1/projects/{project_body['id']}/status",
            json={"status": TEST_NON_ENQUIRY_STATUS},
            headers=auth_headers,
        )
        assert advanced.status_code == 200
        assert advanced.json()["status"] == TEST_NON_ENQUIRY_STATUS

        response = client.post(
            f"/api/v1/projects/{project_body['id']}/convert-to-customer",
            json={
                "name": TEST_NON_ENQUIRY_CUSTOMER_NAME,
                "email": TEST_NON_ENQUIRY_CUSTOMER_EMAIL,
                "phone": TEST_NON_ENQUIRY_CUSTOMER_PHONE,
            },
            headers=auth_headers,
        )

        assert response.status_code == 409

        with SessionLocal() as db:
            customer_count = (
                db.query(Customer).filter_by(name=TEST_NON_ENQUIRY_CUSTOMER_NAME).count()
            )
            assert customer_count == 0

            persisted_project = db.get(Project, uuid.UUID(project_body["id"]))
            assert persisted_project.customer_id is None
            assert persisted_project.status == TEST_NON_ENQUIRY_STATUS
    finally:
        _cleanup()


def test_conversion_of_another_tenants_project_returns_404(
    client, auth_headers, other_tenant_auth_headers
):
    """Tenant B must not be able to convert Tenant A's enquiry Project —
    same tenant-scoped-lookup-hides-existence convention as
    test_get_project_cross_tenant_returns_404 (tests/test_projects.py) and
    test_handoff_of_another_tenants_quote_returns_404
    (tests/test_quote_handoff.py). RBAC role denial is a later RED/GREEN
    cycle, not this one — both callers here are OWNER."""
    _cleanup()
    try:
        project = client.post(
            "/api/v1/projects",
            json={"name": TEST_CROSS_TENANT_PROJECT_NAME},
            headers=auth_headers,
        )
        assert project.status_code == 201
        project_body = project.json()
        assert project_body["status_role"] == "lead"
        assert project_body["customer_id"] is None

        response = client.post(
            f"/api/v1/projects/{project_body['id']}/convert-to-customer",
            json={
                "name": TEST_CROSS_TENANT_CUSTOMER_NAME,
                "email": TEST_CROSS_TENANT_CUSTOMER_EMAIL,
                "phone": TEST_CROSS_TENANT_CUSTOMER_PHONE,
            },
            headers=other_tenant_auth_headers,
        )

        assert response.status_code == 404

        with SessionLocal() as db:
            customer_count = (
                db.query(Customer).filter_by(name=TEST_CROSS_TENANT_CUSTOMER_NAME).count()
            )
            assert customer_count == 0

            persisted_project = db.get(Project, uuid.UUID(project_body["id"]))
            assert persisted_project.customer_id is None
            assert persisted_project.status == "lead"
    finally:
        _cleanup()


def test_same_tenant_user_without_owner_staff_role_cannot_convert_enquiry(
    client, auth_headers
):
    """RBAC (not tenant isolation — see
    test_conversion_of_another_tenants_project_returns_404): a same-tenant,
    authenticated user who is neither OWNER nor STAFF must not be able to
    convert an enquiry Project into a Customer. role=None is the
    repository's real "no role assigned" state — see
    tests/test_permissions.py's test_require_role_rejects_missing_role and
    tests/test_quote_handoff.py's
    test_non_owner_staff_user_cannot_hand_off_an_approved_quote, the exact
    template for this test — not a fabricated role name; the codebase has
    no third UserRole. The conversion route already declares
    require_role(UserRole.OWNER, UserRole.STAFF) (app/projects/router.py),
    so this locks in existing behavior as permanent regression coverage."""
    _cleanup()
    try:
        project = client.post(
            "/api/v1/projects",
            json={"name": TEST_RBAC_PROJECT_NAME},
            headers=auth_headers,
        )
        assert project.status_code == 201
        project_body = project.json()
        assert project_body["status_role"] == "lead"
        assert project_body["customer_id"] is None

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project_body["id"])).tenant_id
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
            f"/api/v1/projects/{project_body['id']}/convert-to-customer",
            json={
                "name": TEST_RBAC_CUSTOMER_NAME,
                "email": TEST_RBAC_CUSTOMER_EMAIL,
                "phone": TEST_RBAC_CUSTOMER_PHONE,
            },
            headers=no_role_headers,
        )

        assert response.status_code == 403

        with SessionLocal() as db:
            customer_count = db.query(Customer).filter_by(name=TEST_RBAC_CUSTOMER_NAME).count()
            assert customer_count == 0

            persisted_project = db.get(Project, uuid.UUID(project_body["id"]))
            assert persisted_project.customer_id is None
            assert persisted_project.status == "lead"
    finally:
        _cleanup()


def test_successful_enquiry_conversion_creates_exactly_one_tenant_scoped_activity(
    client, auth_headers
):
    """Sprint 021 activity contract (docs/SPRINTS/sprint-021.md): the first
    real conversion (unlinked enquiry Project -> Customer created -> Project
    linked) must be audited through the existing ActivityLog infrastructure
    — same mechanism as QUOTE_APPROVED/QUOTE_HANDED_OFF
    (tests/test_quote_handoff.py) — not a parallel audit system, and not a
    reuse of customer_added/project_created (this is its own domain
    transition, same reasoning Sprint 020 gave for introducing
    quote_handed_off instead of reusing project_created). Repeat-conversion
    idempotency for this activity record is a later RED/GREEN cycle, not
    this one: a retry on an already-linked Project must emit no additional
    enquiry_converted activity."""
    _cleanup()
    try:
        project = client.post(
            "/api/v1/projects",
            json={"name": TEST_ACTIVITY_PROJECT_NAME},
            headers=auth_headers,
        )
        assert project.status_code == 201
        project_body = project.json()
        assert project_body["status_role"] == "lead"
        assert project_body["customer_id"] is None

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project_body["id"])).tenant_id
            activity_count_before = db.query(ActivityLog).filter_by(tenant_id=tenant_id).count()

        response = client.post(
            f"/api/v1/projects/{project_body['id']}/convert-to-customer",
            json={
                "name": TEST_ACTIVITY_CUSTOMER_NAME,
                "email": TEST_ACTIVITY_CUSTOMER_EMAIL,
                "phone": TEST_ACTIVITY_CUSTOMER_PHONE,
            },
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
        assert activities[0].type == "enquiry_converted"
        assert activities[0].tenant_id == tenant_id
    finally:
        _cleanup()


def test_conversion_rolls_back_customer_and_project_link_if_activity_logging_fails(
    client, auth_headers, monkeypatch
):
    """Sprint 021 transaction-atomicity contract: create Customer, link
    Project.customer_id, and log enquiry_converted are one logical domain
    transaction. If the final step (activity logging) fails, the earlier two
    persistence effects must not survive — a genuine domain-integrity RED
    today, since crud.create_customer and crud.update_project_customer each
    commit immediately (app/database/crud.py), and
    PostgresActivityRepository.add() (app/activity/repository.py) commits in
    an entirely separate SessionLocal() of its own — there is no shared
    transaction across the three steps yet. Concurrent conversions, new
    status states, RBAC, tenant logic, and migrations are out of scope for
    this cycle."""
    _cleanup()
    try:
        project = client.post(
            "/api/v1/projects",
            json={"name": TEST_ATOMICITY_PROJECT_NAME},
            headers=auth_headers,
        )
        assert project.status_code == 201
        project_body = project.json()
        assert project_body["status_role"] == "lead"
        assert project_body["customer_id"] is None

        with SessionLocal() as db:
            tenant_id = db.get(Project, uuid.UUID(project_body["id"])).tenant_id

        activity_description_prefix = f"Project {project_body['id']}"

        with SessionLocal() as db:
            assert db.query(Customer).filter_by(name=TEST_ATOMICITY_CUSTOMER_NAME).count() == 0
            assert (
                db.query(ActivityLog)
                .filter(
                    ActivityLog.tenant_id == tenant_id,
                    ActivityLog.type == "enquiry_converted",
                    ActivityLog.description.like(f"{activity_description_prefix}%"),
                )
                .count()
                == 0
            )

        def fail_activity_log(*args, **kwargs):
            raise RuntimeError("synthetic activity failure")

        monkeypatch.setattr(activity_service, "log", fail_activity_log)

        # TestClient's default raise_server_exceptions=True re-raises the
        # original exception to the caller even though app/core/errors.py's
        # catch-all handler also turns it into a 500 response server-side —
        # the HTTP status itself isn't this test's contract, the persisted
        # state after the failure is.
        with pytest.raises(RuntimeError, match="synthetic activity failure"):
            client.post(
                f"/api/v1/projects/{project_body['id']}/convert-to-customer",
                json={
                    "name": TEST_ATOMICITY_CUSTOMER_NAME,
                    "email": TEST_ATOMICITY_CUSTOMER_EMAIL,
                    "phone": TEST_ATOMICITY_CUSTOMER_PHONE,
                },
                headers=auth_headers,
            )

        with SessionLocal() as db:
            customer_count = (
                db.query(Customer).filter_by(name=TEST_ATOMICITY_CUSTOMER_NAME).count()
            )
            assert customer_count == 0

            persisted_project = db.get(Project, uuid.UUID(project_body["id"]))
            assert persisted_project.customer_id is None
            assert persisted_project.status == "lead"

            activity_count = (
                db.query(ActivityLog)
                .filter(
                    ActivityLog.tenant_id == tenant_id,
                    ActivityLog.type == "enquiry_converted",
                    ActivityLog.description.like(f"{activity_description_prefix}%"),
                )
                .count()
            )
            assert activity_count == 0
    finally:
        _cleanup()
