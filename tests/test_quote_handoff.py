"""Sprint 020 — quote approval and approved-quote project handoff."""

import uuid

from sqlalchemy import delete, select

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Project, Quote


TEST_PREFIX = "Pytest Sprint 020"
TEST_POSTCODE = "S020-TEST"


def _cleanup() -> None:
    db = SessionLocal()
    try:
        # Projects (if handoff created any) must go before their Customer —
        # Project.customer_id has no ON DELETE CASCADE.
        customer_ids = list(
            db.scalars(select(Customer.id).where(Customer.name.like(f"{TEST_PREFIX}%")))
        )
        if customer_ids:
            db.execute(delete(Project).where(Project.customer_id.in_(customer_ids)))
        db.execute(delete(Quote).where(Quote.postcode == TEST_POSTCODE))
        db.execute(delete(ActivityLog).where(ActivityLog.title.like(f"{TEST_PREFIX}%")))
        db.execute(delete(Customer).where(Customer.name.like(f"{TEST_PREFIX}%")))
        db.commit()
    finally:
        db.close()


def _create_linked_quote(client, headers: dict[str, str]) -> tuple[dict, dict]:
    customer = client.post(
        "/api/v1/customers",
        json={"name": f"{TEST_PREFIX} Customer"},
        headers=headers,
    )
    assert customer.status_code == 201
    quote = client.post(
        "/api/v1/quote",
        json={
            "customer": f"{TEST_PREFIX} Customer",
            "customer_id": customer.json()["id"],
            "material": "Calacatta Gold",
            "thickness": "20mm",
            "kitchen_length": 3.0,
            "postcode": TEST_POSTCODE,
        },
        headers=headers,
    )
    assert quote.status_code == 200
    return customer.json(), quote.json()


def _tenant_id(customer_id: str):
    with SessionLocal() as db:
        return db.get(Customer, uuid.UUID(customer_id)).tenant_id


def test_staff_can_approve_a_draft_quote(client, auth_headers):
    """Smallest Sprint 020 contract: a linked draft quote becomes approved."""
    _cleanup()
    try:
        _customer, quote = _create_linked_quote(client, auth_headers)

        approved = client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        assert approved.json()["approved_at"] is not None
    finally:
        _cleanup()


def test_approving_quote_creates_exactly_one_tenant_scoped_activity_record(client, auth_headers):
    """Approval must be audited through the existing ActivityLog
    infrastructure — same mechanism as QUOTE_CREATED (app/quotes/service.py)
    and every other staff mutation — not a parallel audit system."""
    _cleanup()
    try:
        customer, quote = _create_linked_quote(client, auth_headers)
        tenant_id = _tenant_id(customer["id"])
        with SessionLocal() as db:
            activity_count_before = db.query(ActivityLog).filter_by(tenant_id=tenant_id).count()

        approved = client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        with SessionLocal() as db:
            activities = list(
                db.scalars(
                    select(ActivityLog)
                    .where(ActivityLog.tenant_id == tenant_id)
                    .order_by(ActivityLog.timestamp.desc())
                )
            )
        assert len(activities) == activity_count_before + 1
        assert activities[0].type == "quote_approved"
        assert activities[0].tenant_id == tenant_id
    finally:
        _cleanup()


def test_staff_can_hand_off_an_approved_quote_into_a_project(client, auth_headers):
    """First Sprint 020 handoff contract: an approved, customer-linked quote
    becomes a tenant-scoped Project through the existing Project pipeline
    (app/projects/), traceable back to the quote it came from — not a
    parallel handoff record. Repeat-handoff idempotency, unapproved-quote
    rejection, cross-tenant denial, RBAC, and handoff activity are later
    RED/GREEN cycles, not this one."""
    _cleanup()
    try:
        customer, quote = _create_linked_quote(client, auth_headers)
        approved = client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)
        assert approved.status_code == 200

        handoff = client.post(f"/api/v1/quotes/{quote['id']}/handoff", headers=auth_headers)
        assert handoff.status_code in (200, 201)
        project = handoff.json()
        assert project["customer_id"] == customer["id"]
        assert project["status"] == "booked"

        fetched = client.get(f"/api/v1/projects/{project['id']}", headers=auth_headers)
        assert fetched.status_code == 200
        assert fetched.json()["customer_id"] == customer["id"]
        assert fetched.json()["status"] == "booked"

        assert project["quote_id"] == quote["id"]
    finally:
        _cleanup()


def test_repeat_handoff_of_the_same_quote_is_idempotent(client, auth_headers):
    """Calling handoff twice for the same approved quote must never create a
    second Project — safe retry behavior for UI double-clicks and network
    retries. Cross-tenant, RBAC denial, handoff activity, and frontend are
    later RED/GREEN cycles, not this one."""
    _cleanup()
    try:
        customer, quote = _create_linked_quote(client, auth_headers)
        approved = client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)
        assert approved.status_code == 200

        first = client.post(f"/api/v1/quotes/{quote['id']}/handoff", headers=auth_headers)
        assert first.status_code in (200, 201)

        second = client.post(f"/api/v1/quotes/{quote['id']}/handoff", headers=auth_headers)
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["quote_id"] == quote["id"]

        with SessionLocal() as db:
            assert (
                db.query(Project)
                .filter_by(quote_id=uuid.UUID(quote["id"]))
                .count()
                == 1
            )
    finally:
        _cleanup()


def test_handoff_rejects_a_draft_quote(client, auth_headers):
    """A quote must be approved before it can be handed off — draft quotes
    must not create a Project. Repeated handoff, cross-tenant access, RBAC
    denial, and handoff activity are later RED/GREEN cycles, not this one."""
    _cleanup()
    try:
        customer, quote = _create_linked_quote(client, auth_headers)

        handoff = client.post(f"/api/v1/quotes/{quote['id']}/handoff", headers=auth_headers)
        assert handoff.status_code == 409

        with SessionLocal() as db:
            still_draft = db.get(Quote, uuid.UUID(quote["id"]))
            assert still_draft.status == "draft"
            assert (
                db.query(Project)
                .filter_by(customer_id=uuid.UUID(customer["id"]))
                .count()
                == 0
            )
    finally:
        _cleanup()


def test_handoff_of_another_tenants_quote_returns_404(
    client, auth_headers, other_tenant_auth_headers
):
    """Tenant B must not be able to hand off Tenant A's approved quote —
    same tenant-scoped-lookup-hides-existence convention as
    test_get_quote_cross_tenant_returns_404 (tests/test_quotes_api.py) and
    test_get_project_cross_tenant_returns_404 (tests/test_projects.py).
    RBAC role denial is a later RED/GREEN cycle, not this one — both
    callers here are OWNER."""
    _cleanup()
    try:
        customer, quote = _create_linked_quote(client, auth_headers)
        approved = client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)
        assert approved.status_code == 200

        handoff = client.post(
            f"/api/v1/quotes/{quote['id']}/handoff", headers=other_tenant_auth_headers
        )
        assert handoff.status_code == 404

        with SessionLocal() as db:
            assert (
                db.query(Project).filter_by(quote_id=uuid.UUID(quote["id"])).count() == 0
            )
            still_approved = db.get(Quote, uuid.UUID(quote["id"]))
            assert still_approved.status == "approved"
    finally:
        _cleanup()
