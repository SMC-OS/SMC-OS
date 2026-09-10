"""Sprint 024 — Notifications / Follow-up Automation (stale enquiry
follow-up). See docs/SPRINTS/sprint-024.md for the locked contract.
Unlike prior sprints' first RED (an HTTP route), this is a pure
domain-service test — the locked contract has no HTTP boundary for
automation (docs/SPRINTS/sprint-024.md §7/§9) — so every test calls
app.notifications.follow_up_service directly against a plain DB session.

Every test signs up its own fresh, fully isolated tenant (never the
shared seeded `auth_headers` tenant every other test file also uses):
follow_up_service.run() scans *globally* across every tenant by design
(§6), so running it against the shared seeded tenant would create a
real, persistent NotificationRecord there — with a synthetic future
`timestamp` that then sorts ahead of any real notification another test
file creates later in the same run, breaking that other file's exact
"most recent notification" assertions. A fresh tenant with no
pre-existing Projects has nothing else for a global scan to pick up.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.auth.service import auth_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import ActivityLog, NotificationRecord, Project, Tenant, User
from app.notifications.follow_up_service import STALE_ENQUIRY_THRESHOLD, follow_up_service

RUN_ID = uuid.uuid4().hex[:8]
TEST_PREFIX = f"Pytest Sprint 024 {RUN_ID}"


def _stale_now(created_at):
    return created_at + STALE_ENQUIRY_THRESHOLD + timedelta(days=1)


def _signup(client, suffix: str) -> tuple[dict[str, str], uuid.UUID]:
    """Signs up a brand-new tenant + Owner, isolated from every other
    test (including other tests in this same file, via `suffix`) and
    from the shared seeded tenant every other test file's `auth_headers`
    fixture uses."""
    email = f"pytest-sprint024-{RUN_ID}-{suffix}@example.invalid"
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": f"{TEST_PREFIX} Co {suffix}",
            "name": "Pytest Owner",
            "email": email,
            "password": f"pytest-sprint024-{suffix}-password",
        },
    )
    assert response.status_code == 201
    body = response.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    with SessionLocal() as db:
        tenant_id = db.get(User, uuid.UUID(body["user"]["id"])).tenant_id
    return headers, tenant_id


def _cleanup_tenant(tenant_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        # Notification/ActivityLog rows must go before the User/Project/
        # Tenant they reference (no ON DELETE CASCADE anywhere in this
        # schema) — same ordering lesson as tests/test_appointments.py.
        db.execute(delete(NotificationRecord).where(NotificationRecord.tenant_id == tenant_id))
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(Project).where(Project.tenant_id == tenant_id))
        db.execute(delete(User).where(User.tenant_id == tenant_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
    finally:
        db.close()


def test_run_creates_exactly_one_notification_for_a_stale_enquiry_with_assigned_staff(client):
    """First Sprint 024 contract: a stale (status=="enquiry", created more
    than the locked threshold ago) Project with an assigned Staff member
    produces exactly one NotificationRecord targeted at that Staff member.
    Idempotency, not-due/wrong-state exclusions, cross-tenant isolation,
    Owner fallback, and failure safety are later RED/GREEN cycles, not
    this one — see docs/SPRINTS/sprint-024.md's locked TDD sequence."""
    headers, tenant_id = _signup(client, "assigned")
    try:
        project_res = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Project"}, headers=headers
        )
        assert project_res.status_code == 201
        project_id = uuid.UUID(project_res.json()["id"])

        with SessionLocal() as db:
            staff = auth_service.create_user(
                db,
                tenant_id=tenant_id,
                name="Pytest Staff",
                email=f"pytest-sprint024-{RUN_ID}-assigned-staff@example.invalid",
                password="pytest-sprint024-assigned-staff-password",
                role="Staff",
            )
            staff_id = staff.id

        assign_res = client.patch(
            f"/api/v1/projects/{project_id}/assign",
            json={"assigned_user_id": str(staff_id)},
            headers=headers,
        )
        assert assign_res.status_code == 200

        with SessionLocal() as db:
            project = db.get(Project, project_id)
            # Sprint 039 — a workspace signed up today is on the
            # trade-neutral pipeline, so its first stage is "lead". The
            # scan itself selects by *role*, so this test would read the
            # same for a stone tenant sitting on "enquiry".
            assert project.status == "lead"
            created_at = project.created_at

        with SessionLocal() as db:
            result = follow_up_service.run(db, now=_stale_now(created_at))

        # Sprint 027 (docs/SPRINTS/sprint-027.md §3 finding): run() scans
        # *globally* across every tenant (by design, see this file's module
        # docstring), so `result.created` is a whole-database count, not
        # this test's own count — a stale enquiry left behind anywhere by
        # an earlier interrupted run (this is a long-lived shared dev
        # Postgres, not a fresh database per run) makes `== 1` fail without
        # this test doing anything wrong. The scoped query directly below,
        # filtered to this test's own project_id, is what actually proves
        # the locked contract ("exactly one notification for *this*
        # project") and is unaffected by any other tenant's data.
        assert result.created >= 1

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
        _cleanup_tenant(tenant_id)


def test_running_twice_creates_no_duplicate_notification(client):
    """Idempotency contract (sprint-024.md §6): the same logical reminder
    must not generate duplicate notifications on every run."""
    headers, tenant_id = _signup(client, "idempotent")
    try:
        project_res = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Project"}, headers=headers
        )
        assert project_res.status_code == 201
        project_id = uuid.UUID(project_res.json()["id"])

        with SessionLocal() as db:
            created_at = db.get(Project, project_id).created_at
        now = _stale_now(created_at)

        with SessionLocal() as db:
            first = follow_up_service.run(db, now=now)
        # See the Sprint 027 note above test_run_creates_exactly_one_...:
        # a global-scan count, not scoped to this test's own project.
        assert first.created >= 1

        with SessionLocal() as db:
            second = follow_up_service.run(db, now=now)
        assert second.created == 0
        assert second.skipped_existing >= 1

        with SessionLocal() as db:
            count = (
                db.query(NotificationRecord)
                .filter(NotificationRecord.source_id == project_id)
                .count()
            )
        assert count == 1
    finally:
        _cleanup_tenant(tenant_id)


def test_duplicate_dedupe_key_is_rejected_at_the_database_level(client):
    """DB-enforced invariant (sprint-024.md §6): the unique constraint is
    a hard backstop, not just a service-level pre-check."""
    headers, tenant_id = _signup(client, "dbunique")
    try:
        project_res = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Project"}, headers=headers
        )
        assert project_res.status_code == 201
        project_id = uuid.UUID(project_res.json()["id"])

        with SessionLocal() as db:
            created_at = db.get(Project, project_id).created_at

        dedupe_key = f"stale_enquiry_follow_up:{project_id}"
        with SessionLocal() as db:
            crud.create_notification(
                db,
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                title="Enquiry needs follow-up",
                message="first",
                type="warning",
                timestamp=_stale_now(created_at),
                dedupe_key=dedupe_key,
            )

        with SessionLocal() as db, pytest.raises(IntegrityError):
            crud.create_notification(
                db,
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                title="Enquiry needs follow-up",
                message="second",
                type="warning",
                timestamp=_stale_now(created_at),
                dedupe_key=dedupe_key,
            )
    finally:
        _cleanup_tenant(tenant_id)


def test_project_younger_than_threshold_is_not_due(client):
    """Not-due contract: a Project created less than the locked threshold
    before `now` is not eligible, no notification created."""
    headers, tenant_id = _signup(client, "notdue")
    try:
        project_res = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Project"}, headers=headers
        )
        assert project_res.status_code == 201
        project_id = uuid.UUID(project_res.json()["id"])

        with SessionLocal() as db:
            created_at = db.get(Project, project_id).created_at

        # Exactly at the threshold boundary minus a day — still not due.
        not_due_now = created_at + STALE_ENQUIRY_THRESHOLD - timedelta(days=1)

        with SessionLocal() as db:
            follow_up_service.run(db, now=not_due_now)

        with SessionLocal() as db:
            count = (
                db.query(NotificationRecord)
                .filter(NotificationRecord.source_id == project_id)
                .count()
            )
        assert count == 0
    finally:
        _cleanup_tenant(tenant_id)


def test_project_not_in_enquiry_status_is_not_examined(client):
    """Wrong-lifecycle-state contract: a Project that has advanced past
    `enquiry` is never eligible, regardless of age."""
    headers, tenant_id = _signup(client, "wrongstate")
    try:
        project_res = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Project"}, headers=headers
        )
        assert project_res.status_code == 201
        project_id = uuid.UUID(project_res.json()["id"])

        advance_res = client.patch(
            f"/api/v1/projects/{project_id}/status",
            json={"status": "quoted"},
            headers=headers,
        )
        assert advance_res.status_code == 200

        with SessionLocal() as db:
            created_at = db.get(Project, project_id).created_at

        with SessionLocal() as db:
            follow_up_service.run(db, now=_stale_now(created_at))

        with SessionLocal() as db:
            count = (
                db.query(NotificationRecord)
                .filter(NotificationRecord.source_id == project_id)
                .count()
            )
        # The global query only ever selects projects at a `lead`-role
        # stage, so this "quoted" Project is never examined at all (not
        # "examined then skipped for the wrong reason") — proven by there
        # being no notification for it, the only externally-observable
        # evidence.
        assert count == 0
    finally:
        _cleanup_tenant(tenant_id)


def test_two_tenants_each_get_their_own_correctly_scoped_notification(client):
    """Tenant isolation (sprint-024.md §6/§8): each tenant's stale enquiry
    produces its own correctly-tenant-scoped notification, zero
    cross-talk."""
    headers_a, tenant_a_id = _signup(client, "tenantA")
    headers_b, tenant_b_id = _signup(client, "tenantB")
    try:
        project_a = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Project"}, headers=headers_a
        )
        assert project_a.status_code == 201
        project_a_id = uuid.UUID(project_a.json()["id"])

        project_b = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Project"}, headers=headers_b
        )
        assert project_b.status_code == 201
        project_b_id = uuid.UUID(project_b.json()["id"])

        with SessionLocal() as db:
            created_at_a = db.get(Project, project_a_id).created_at
            created_at_b = db.get(Project, project_b_id).created_at

        with SessionLocal() as db:
            follow_up_service.run(db, now=_stale_now(max(created_at_a, created_at_b)))

        with SessionLocal() as db:
            notification_a = (
                db.query(NotificationRecord).filter(NotificationRecord.source_id == project_a_id).one()
            )
            notification_b = (
                db.query(NotificationRecord).filter(NotificationRecord.source_id == project_b_id).one()
            )

        assert notification_a.tenant_id == tenant_a_id
        assert notification_b.tenant_id == tenant_b_id
    finally:
        _cleanup_tenant(tenant_a_id)
        _cleanup_tenant(tenant_b_id)


def test_unassigned_project_falls_back_to_tenant_owner(client):
    """Recipient fallback (sprint-024.md §5): no assigned Staff member →
    the tenant's Owner receives the follow-up."""
    headers, tenant_id = _signup(client, "unassigned")
    try:
        project_res = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Project"}, headers=headers
        )
        assert project_res.status_code == 201
        project_id = uuid.UUID(project_res.json()["id"])

        with SessionLocal() as db:
            project = db.get(Project, project_id)
            assert project.assigned_user_id is None
            created_at = project.created_at
            owner = (
                db.query(User)
                .filter(User.tenant_id == tenant_id, User.role == "Owner")
                .order_by(User.created_at)
                .first()
            )
            owner_id = owner.id

        with SessionLocal() as db:
            result = follow_up_service.run(db, now=_stale_now(created_at))
        # See the Sprint 027 note above test_run_creates_exactly_one_...:
        # a global-scan count, not scoped to this test's own project.
        assert result.created >= 1

        with SessionLocal() as db:
            notification = (
                db.query(NotificationRecord).filter(NotificationRecord.source_id == project_id).one()
            )
        assert notification.recipient_user_id == owner_id
    finally:
        _cleanup_tenant(tenant_id)


def test_failure_creating_one_notification_does_not_affect_another_already_committed(
    client, monkeypatch
):
    """Failure safety (sprint-024.md §8): each Project's notification
    insert commits independently (no multi-write transaction wraps the
    whole batch, by design). A failure processing one Project in a later
    run must never remove or corrupt a different Project's notification
    that a prior, successful run already committed."""
    headers, tenant_id = _signup(client, "failure")
    try:
        good_project = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Good Project"}, headers=headers
        )
        assert good_project.status_code == 201
        good_project_id = uuid.UUID(good_project.json()["id"])

        with SessionLocal() as db:
            good_created_at = db.get(Project, good_project_id).created_at

        # Run 1: only the good Project exists and is due — its
        # notification commits successfully.
        with SessionLocal() as db:
            first_result = follow_up_service.run(db, now=_stale_now(good_created_at))
        # See the Sprint 027 note above test_run_creates_exactly_one_...:
        # a global-scan count, not scoped to this test's own project.
        assert first_result.created >= 1

        bad_project = client.post(
            "/api/v1/projects", json={"name": f"{TEST_PREFIX} Bad Project"}, headers=headers
        )
        assert bad_project.status_code == 201
        bad_project_id = uuid.UUID(bad_project.json()["id"])

        with SessionLocal() as db:
            bad_created_at = db.get(Project, bad_project_id).created_at

        from app.notifications import follow_up_service as follow_up_module

        original_create_notification = follow_up_module.crud.create_notification

        def failing_create_notification(*args, **kwargs):
            raise RuntimeError("synthetic failure creating the notification")

        monkeypatch.setattr(
            follow_up_module.crud, "create_notification", failing_create_notification
        )

        # Run 2: the bad Project is now also due; its insert is forced to
        # fail. The good Project (already stale from run 1 too) is
        # examined again but skipped as already-existing before any write
        # is attempted for it, so only the bad Project's insert is
        # exercised here.
        with SessionLocal() as db:
            with pytest.raises(RuntimeError, match="synthetic failure"):
                follow_up_service.run(db, now=_stale_now(max(good_created_at, bad_created_at)))

        with SessionLocal() as db:
            good_count = (
                db.query(NotificationRecord)
                .filter(NotificationRecord.source_id == good_project_id)
                .count()
            )
            bad_count = (
                db.query(NotificationRecord)
                .filter(NotificationRecord.source_id == bad_project_id)
                .count()
            )
        # The good Project's run-1 notification survives run 2's failure
        # untouched; the bad Project's insert never committed.
        assert good_count == 1
        assert bad_count == 0

        monkeypatch.setattr(follow_up_module.crud, "create_notification", original_create_notification)

        with SessionLocal() as db:
            third_result = follow_up_service.run(db, now=_stale_now(max(good_created_at, bad_created_at)))
        # See the Sprint 027 note above test_run_creates_exactly_one_...:
        # a global-scan count, not scoped to this test's own project.
        assert third_result.created >= 1

        with SessionLocal() as db:
            bad_count_after = (
                db.query(NotificationRecord)
                .filter(NotificationRecord.source_id == bad_project_id)
                .count()
            )
        assert bad_count_after == 1
    finally:
        _cleanup_tenant(tenant_id)
