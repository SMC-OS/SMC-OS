"""Sprint 025 — Business Command Centre. See docs/SPRINTS/sprint-025.md for
the locked contract.

Every "exact metric" test signs up a brand-new, fully isolated tenant per
test (never the shared seeded `auth_headers` tenant) — the same lesson
Sprint 024 learned the hard way (docs/SPRINTS/sprint-024.md): the shared
seeded tenant accumulates Projects/Quotes/Appointments from every other
test file that also uses `auth_headers`, which would make an exact-count
assertion here flaky and order-dependent.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.auth.service import auth_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Appointment,
    Communication,
    Customer,
    EmailVerificationToken,
    NotificationRecord,
    Project,
    ProjectWorkflowHistory,
    Quote,
    QuoteItem,
    Subscription,
    Tenant,
    User,
)

RUN_ID = uuid.uuid4().hex[:8]
TEST_PREFIX = f"Pytest Sprint 025 {RUN_ID}"


def _signup(client, suffix: str) -> tuple[dict[str, str], uuid.UUID]:
    email = f"pytest-sprint025-{RUN_ID}-{suffix}@example.invalid"
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": f"{TEST_PREFIX} Co {suffix}",
            "name": "Pytest Owner",
            "email": email,
            "password": f"Pytest-Sprint025-{suffix}-Password-1!",
        },
    )
    assert response.status_code == 201
    body = response.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    with SessionLocal() as db:
        user_row = db.get(User, uuid.UUID(body["user"]["id"]))
        tenant_id = user_row.tenant_id
        # Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix —
        # this helper stands up an established tenant under test (command-
        # centre metrics), not the verification flow itself, so it marks
        # itself verified immediately — same reasoning as conftest.py's
        # other_tenant_auth_headers.
        user_row.email_verified_at = datetime.now(timezone.utc)
        db.commit()
        # GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES — same reasoning
        # again, one gate further in: a real signup gets no Subscription
        # at all, so this helper grants one explicitly too.
        crud.upsert_subscription(
            db,
            tenant_id=tenant_id,
            plan="pro",
            billing_period="monthly",
            status="active",
            legacy_grandfathered=True,
        )
    return headers, tenant_id


def _cleanup_tenant(tenant_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(NotificationRecord).where(NotificationRecord.tenant_id == tenant_id))
        db.execute(delete(Appointment).where(Appointment.tenant_id == tenant_id))
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        # GeoCore Premium OS Plan 01 (Sprint 040) — a workflow transition
        # (Task 5) writes a ProjectWorkflowHistory row with no ON DELETE
        # cascade on its project_id FK, same "children before parents"
        # ordering as everything else here.
        db.execute(delete(ProjectWorkflowHistory).where(ProjectWorkflowHistory.tenant_id == tenant_id))
        # Project.quote_id references quotes.id (no ON DELETE CASCADE) —
        # Project must go before Quote, opposite of most other cleanup
        # helpers in this suite which never link the two.
        db.execute(delete(Project).where(Project.tenant_id == tenant_id))
        db.execute(
            delete(QuoteItem).where(
                QuoteItem.quote_id.in_(select(Quote.id).where(Quote.tenant_id == tenant_id))
            )
        )
        db.execute(delete(Quote).where(Quote.tenant_id == tenant_id))
        db.execute(delete(Customer).where(Customer.tenant_id == tenant_id))
        # Sprint 039 Production Readiness Defect Gate, Blocker 1 — _signup()
        # now also creates an EmailVerificationToken (user_id FK, no
        # ondelete) and a Communication row (tenant_id FK) — same
        # "children before parents" ordering as everything else here.
        db.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id.in_(select(User.id).where(User.tenant_id == tenant_id))
            )
        )
        db.execute(delete(Communication).where(Communication.tenant_id == tenant_id))
        # Sprint 039 Production Readiness Defect Gate, Blocker 3 — _signup()
        # now also starts a real trial Subscription row (tenant_id FK, no
        # ondelete) — same "children before parents" ordering as everything
        # else here.
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
        db.execute(delete(User).where(User.tenant_id == tenant_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
    finally:
        db.close()


# The linear pipeline (app/projects/service.py) only accepts the exact
# next status in sequence — a Project reaching "booked" must pass through
# "quoted" first via two separate PATCH calls, never a single skip.
_STATUS_SEQUENCE = ["enquiry", "quoted", "booked", "templated", "fabricated", "installed", "complete"]


def _create_project(client, headers, name: str, status: str | None = None) -> str:
    r = client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert r.status_code == 201
    project_id = r.json()["id"]
    if status is not None and status != "enquiry":
        target_index = _STATUS_SEQUENCE.index(status)
        for next_status in _STATUS_SEQUENCE[1 : target_index + 1]:
            r = client.patch(
                f"/api/v1/projects/{project_id}/status",
                json={"status": next_status},
                headers=headers,
            )
            assert r.status_code == 200
    return project_id


def test_pipeline_counts_are_exact_and_tenant_scoped(client):
    """First Sprint 025 contract: given multiple Projects across statuses
    in the caller's tenant, plus a Project in a completely separate
    tenant, GET /dashboard/command-centre returns exact per-status counts
    for the caller's tenant only (docs/SPRINTS/sprint-025.md §3)."""
    headers, tenant_id = _signup(client, "pipeline")
    other_headers, other_tenant_id = _signup(client, "pipeline-other")
    try:
        _create_project(client, headers, f"{TEST_PREFIX} Enquiry 1")
        _create_project(client, headers, f"{TEST_PREFIX} Enquiry 2")
        _create_project(client, headers, f"{TEST_PREFIX} Quoted 1", status="quoted")
        _create_project(client, headers, f"{TEST_PREFIX} Booked 1", status="booked")

        # A Project in a completely different tenant must never be counted.
        _create_project(client, other_headers, f"{TEST_PREFIX} Other Tenant Enquiry")

        response = client.get("/api/v1/dashboard/command-centre", headers=headers)
        assert response.status_code == 200
        body = response.json()

        assert body["pipeline"] == {
            "enquiry": 2,
            "quoted": 1,
            "booked": 1,
            "templated": 0,
            "fabricated": 0,
            "installed": 0,
            "complete": 0,
        }
    finally:
        _cleanup_tenant(tenant_id)
        _cleanup_tenant(other_tenant_id)


def test_pipeline_by_role_aggregates_across_trades_and_is_tenant_scoped(client):
    """GeoCore Premium OS Plan 01 (Sprint 040, Task 7) — a stone project on
    "Measure / Site Visit" and an electrical project on "Site Assessment"
    are different labels on two different trade workflows, but both are
    the SURVEY role, so a company-wide "what's out on survey right now"
    number must count them together. A Project in a different tenant, and
    one left at its default "Enquiry" (LEAD), must not be miscounted."""
    headers, tenant_id = _signup(client, "role-pipeline")
    other_headers, other_tenant_id = _signup(client, "role-pipeline-other")
    try:
        lead_stone = client.post(
            "/api/v1/projects",
            json={"name": f"{TEST_PREFIX} Stone Lead", "project_type": "stone"},
            headers=headers,
        )
        assert lead_stone.status_code == 201

        survey_stone = client.post(
            "/api/v1/projects",
            json={"name": f"{TEST_PREFIX} Stone Survey", "project_type": "stone"},
            headers=headers,
        )
        assert survey_stone.status_code == 201
        moved_stone = client.post(
            f"/api/v1/projects/{survey_stone.json()['id']}/workflow/transition",
            json={"target_stage_key": "measure_site_visit"},
            headers=headers,
        )
        assert moved_stone.status_code == 200
        assert moved_stone.json()["workflow"]["role"] == "survey"

        survey_electrical = client.post(
            "/api/v1/projects",
            json={"name": f"{TEST_PREFIX} Electrical Survey", "project_type": "electrical"},
            headers=headers,
        )
        assert survey_electrical.status_code == 201
        moved_electrical = client.post(
            f"/api/v1/projects/{survey_electrical.json()['id']}/workflow/transition",
            json={"target_stage_key": "site_assessment"},
            headers=headers,
        )
        assert moved_electrical.status_code == 200
        assert moved_electrical.json()["workflow"]["role"] == "survey"

        # A Project in a completely different tenant must never be counted.
        other_project = client.post(
            "/api/v1/projects",
            json={"name": f"{TEST_PREFIX} Other Tenant Survey", "project_type": "electrical"},
            headers=other_headers,
        )
        assert other_project.status_code == 201
        client.post(
            f"/api/v1/projects/{other_project.json()['id']}/workflow/transition",
            json={"target_stage_key": "site_assessment"},
            headers=other_headers,
        )

        response = client.get("/api/v1/dashboard/command-centre", headers=headers)
        assert response.status_code == 200
        by_role = response.json()["pipeline_by_role"]

        assert by_role["lead"] == 1
        assert by_role["survey"] == 2
        assert sum(by_role.values()) == 3
    finally:
        _cleanup_tenant(tenant_id)
        _cleanup_tenant(other_tenant_id)


def _create_customer(client, headers, name: str) -> str:
    r = client.post("/api/v1/customers", json={"name": name}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def _create_draft_quote(client, headers, customer_id: str, postcode: str) -> dict:
    r = client.post(
        "/api/v1/quote",
        json={
            "customer": f"{TEST_PREFIX} Customer",
            "customer_id": customer_id,
            "material": "Calacatta Gold",
            "thickness": "20mm",
            "kitchen_length": 3.0,
            "postcode": postcode,
        },
        headers=headers,
    )
    assert r.status_code == 200
    return r.json()


def test_quote_funnel_and_value_are_exact(client):
    """Locks docs/SPRINTS/sprint-025.md §3's exact quote-funnel/value
    semantics: `handed_off` counts Projects with quote_id set (not derived
    arithmetic from draft/approved), `quoted_value` sums every quote
    regardless of status, `approved_quoted_value` sums only approved
    ones."""
    headers, tenant_id = _signup(client, "funnel")
    try:
        customer_id = _create_customer(client, headers, f"{TEST_PREFIX} Funnel Customer")

        draft = _create_draft_quote(client, headers, customer_id, "S025-DRAFT")

        to_approve = _create_draft_quote(client, headers, customer_id, "S025-APPROVE")
        approve_res = client.post(
            f"/api/v1/quotes/{to_approve['id']}/approve", headers=headers
        )
        assert approve_res.status_code == 200

        to_handoff = _create_draft_quote(client, headers, customer_id, "S025-HANDOFF")
        approve_res = client.post(
            f"/api/v1/quotes/{to_handoff['id']}/approve", headers=headers
        )
        assert approve_res.status_code == 200
        handoff_res = client.post(
            f"/api/v1/quotes/{to_handoff['id']}/handoff", headers=headers
        )
        assert handoff_res.status_code == 200

        response = client.get("/api/v1/dashboard/command-centre", headers=headers)
        assert response.status_code == 200
        body = response.json()

        assert body["quotes"] == {"draft": 1, "approved": 2, "handed_off": 1}

        expected_quoted_value = draft["total"] + to_approve["total"] + to_handoff["total"]
        expected_approved_value = to_approve["total"] + to_handoff["total"]
        assert body["value"]["quoted_value"] == pytest.approx(expected_quoted_value)
        assert body["value"]["approved_quoted_value"] == pytest.approx(expected_approved_value)
    finally:
        _cleanup_tenant(tenant_id)


def test_site_visit_counts_are_exact(client):
    headers, tenant_id = _signup(client, "visits")
    try:
        project_id = _create_project(client, headers, f"{TEST_PREFIX} Visits Project")
        scheduled_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        appointment_ids = []
        for _ in range(3):
            r = client.post(
                f"/api/v1/projects/{project_id}/appointments",
                json={"scheduled_at": scheduled_at},
                headers=headers,
            )
            assert r.status_code == 201
            appointment_ids.append(r.json()["id"])

        completed = client.patch(
            f"/api/v1/appointments/{appointment_ids[0]}/status",
            json={"status": "completed"},
            headers=headers,
        )
        assert completed.status_code == 200
        cancelled = client.patch(
            f"/api/v1/appointments/{appointment_ids[1]}/status",
            json={"status": "cancelled"},
            headers=headers,
        )
        assert cancelled.status_code == 200
        # appointment_ids[2] stays "scheduled".

        response = client.get("/api/v1/dashboard/command-centre", headers=headers)
        assert response.status_code == 200
        assert response.json()["site_visits"] == {
            "scheduled": 1,
            "completed": 1,
            "cancelled": 1,
        }
    finally:
        _cleanup_tenant(tenant_id)


def test_follow_up_attention_counts_unread_project_sourced_notifications_tenant_wide(client):
    """Tenant-wide, not per-recipient (docs/SPRINTS/sprint-025.md §3): an
    unread project-sourced notification counts regardless of which user
    (or no user) it's addressed to. A read one, and a non-project-sourced
    one, must not be counted."""
    headers, tenant_id = _signup(client, "followup")
    try:
        project_id = _create_project(client, headers, f"{TEST_PREFIX} Follow-up Project")

        with SessionLocal() as db:
            crud.create_notification(
                db,
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                title="Enquiry needs follow-up",
                message="Unread, project-sourced — must count.",
                type="warning",
                timestamp=datetime.now(timezone.utc),
                read=False,
                source_type="project",
                source_id=uuid.UUID(project_id),
                dedupe_key=f"pytest-sprint025-{RUN_ID}-followup-unread",
            )
            crud.create_notification(
                db,
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                title="Enquiry needs follow-up",
                message="Already read — must not count.",
                type="warning",
                timestamp=datetime.now(timezone.utc),
                read=True,
                source_type="project",
                source_id=uuid.UUID(project_id),
                dedupe_key=f"pytest-sprint025-{RUN_ID}-followup-read",
            )
            crud.create_notification(
                db,
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                title="Tenant broadcast",
                message="Unread but no source_type — must not count.",
                type="info",
                timestamp=datetime.now(timezone.utc),
                read=False,
                source_type=None,
                source_id=None,
            )

        response = client.get("/api/v1/dashboard/command-centre", headers=headers)
        assert response.status_code == 200
        assert response.json()["follow_up"] == {"unread_follow_ups": 1}
    finally:
        _cleanup_tenant(tenant_id)


def test_owner_and_staff_can_both_access_command_centre(client):
    headers, tenant_id = _signup(client, "rbac-owner")
    try:
        with SessionLocal() as db:
            staff = auth_service.create_user(
                db,
                tenant_id=tenant_id,
                name="Pytest Staff",
                email=f"pytest-sprint025-{RUN_ID}-rbac-staff@example.invalid",
                password="pytest-sprint025-rbac-staff-password",
                role="Staff",
            )
            staff_id = staff.id

        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": f"pytest-sprint025-{RUN_ID}-rbac-staff@example.invalid",
                "password": "pytest-sprint025-rbac-staff-password",
            },
        )
        assert login.status_code == 200
        staff_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        assert client.get("/api/v1/dashboard/command-centre", headers=headers).status_code == 200
        assert (
            client.get("/api/v1/dashboard/command-centre", headers=staff_headers).status_code
            == 200
        )
        assert staff_id is not None
    finally:
        _cleanup_tenant(tenant_id)


def test_role_none_is_forbidden(client):
    """role=None is the repository's real "no role assigned" state (see
    tests/test_permissions.py's test_require_role_rejects_missing_role) —
    not a fabricated role. Locks in the endpoint's require_role(OWNER,
    STAFF) gate as permanent regression coverage."""
    headers, tenant_id = _signup(client, "rbac-none")
    try:
        email = f"pytest-sprint025-{RUN_ID}-rbac-none-user@example.invalid"
        password = "pytest-sprint025-rbac-none-password"
        with SessionLocal() as db:
            auth_service.create_user(
                db, tenant_id=tenant_id, name="Pytest No-Role User", email=email, password=password
            )

        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200
        no_role_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = client.get("/api/v1/dashboard/command-centre", headers=no_role_headers)
        assert response.status_code == 403
    finally:
        _cleanup_tenant(tenant_id)


def test_empty_tenant_gets_all_zeros_not_nulls_or_500(client):
    """Locks docs/SPRINTS/sprint-025.md §3's empty-state contract: a
    brand-new tenant with zero rows anywhere gets a valid 200 with every
    count 0 and every value 0.0 — never a null explosion or a 500."""
    headers, tenant_id = _signup(client, "empty")
    try:
        response = client.get("/api/v1/dashboard/command-centre", headers=headers)
        assert response.status_code == 200
        assert response.json() == {
            "customers": 0,
            "pipeline": {
                "enquiry": 0,
                "quoted": 0,
                "booked": 0,
                "templated": 0,
                "fabricated": 0,
                "installed": 0,
                "complete": 0,
            },
            # GeoCore Premium OS Plan 01 (Sprint 040, Task 7) — additive
            # alongside "pipeline" above, same never-null empty-state
            # contract, now for all 13 semantic WorkflowRole buckets.
            "pipeline_by_role": {
                "lead": 0,
                "survey": 0,
                "quoted": 0,
                "approved": 0,
                "procurement": 0,
                "scheduled": 0,
                "in_progress": 0,
                "inspection": 0,
                "snagging": 0,
                "handover": 0,
                "completed": 0,
                "on_hold": 0,
                "cancelled": 0,
            },
            "quotes": {"draft": 0, "approved": 0, "handed_off": 0},
            "value": {"quoted_value": 0.0, "approved_quoted_value": 0.0},
            "site_visits": {"scheduled": 0, "completed": 0, "cancelled": 0},
            "follow_up": {"unread_follow_ups": 0},
            # GeoCore Premium OS Plan 04 (Sprint 043), Task 20 — additive,
            # same never-null empty-state contract as everything above.
            "financials": {
                "approved_contract_value": 0.0,
                "approved_variations_value": 0.0,
                "projects_with_margin_risk": 0,
                "projects_with_missing_cost_data": 0,
                "projects_with_a_contract": 0,
            },
            # GeoCore Premium OS Plan 05 (Sprint 044), Task 25 — additive,
            # same never-null empty-state contract as everything above.
            "procurement": {
                "materials_required": 0,
                "purchase_orders_awaiting_approval": 0,
                "purchase_orders_ordered": 0,
                "late_deliveries": 0,
                "materials_due_this_week": 0,
                "projects_blocked_by_materials": 0,
            },
        }
    finally:
        _cleanup_tenant(tenant_id)
