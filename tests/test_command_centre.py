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
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Appointment,
    Customer,
    NotificationRecord,
    Project,
    Quote,
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
            "password": f"pytest-sprint025-{suffix}-password",
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
        db.execute(delete(NotificationRecord).where(NotificationRecord.tenant_id == tenant_id))
        db.execute(delete(Appointment).where(Appointment.tenant_id == tenant_id))
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(Quote).where(Quote.tenant_id == tenant_id))
        db.execute(delete(Project).where(Project.tenant_id == tenant_id))
        db.execute(delete(Customer).where(Customer.tenant_id == tenant_id))
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
