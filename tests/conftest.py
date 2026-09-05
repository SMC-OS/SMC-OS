import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Appointment,
    Automation,
    AutomationRun,
    Customer,
    Document,
    Invitation,
    Message,
    NotificationRecord,
    PortalLink,
    Project,
    Quote,
    QuoteItem,
    Task,
    Tenant,
    User,
)
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    """A plain DB session for tests that call service-layer code directly
    (not through the HTTP client) — reusable by any module's tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def auth_headers(client):
    """Bearer header for the seeded owner — reusable by any module's tests
    that need to call an authenticated route (customers, and beyond)."""
    r = client.post(
        "/api/v1/auth/login",
        json={"email": settings.seed_admin_email, "password": settings.seed_admin_password},
    )
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# Sprint 012 (ADR-029) — cross-tenant isolation tests need two genuinely
# separate tenants, not just two users. `other_tenant_auth_headers` signs
# up a brand-new company/owner distinct from the seeded owner `auth_headers`
# uses, so a test can assert Tenant A's records are invisible/unreachable
# from Tenant B and vice versa.
#
# Sprint 027 (docs/SPRINTS/sprint-027.md §6.2 finding) — the email/company
# below used to be a fixed literal, cleaned up before and after each use,
# unlike every Playwright spec's own RUN_ID-randomized convention. Safe
# under today's sequential pytest execution, but a real determinism risk
# if this suite is ever parallelized (pytest-xdist) or if a crashed prior
# run left the fixed row behind before its own teardown ran. A
# session-scoped RUN_ID (computed once at import time, stable for every
# test in this run) removes the collision risk without changing the
# fixture's cleanup contract — cleanup still runs before and after, just
# against this session's own row.
_CONFTEST_RUN_ID = uuid.uuid4().hex[:10]
OTHER_TENANT_EMAIL = f"pytest-other-tenant-owner-{_CONFTEST_RUN_ID}@example.invalid"
OTHER_TENANT_COMPANY = f"Pytest Other Tenant Co {_CONFTEST_RUN_ID}"
OTHER_TENANT_PASSWORD = "pytest-other-tenant-password-1"


def _cleanup_other_tenant():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == OTHER_TENANT_EMAIL).first()
        if user is not None:
            tenant_id = user.tenant_id
            # Sprint 012: TenantService.create() now logs a real ActivityLog
            # row against the new tenant's own id (ADR-029), so it must be
            # deleted before the Tenant row or the FK constraint added in
            # Sprint 008 (ADR-025) rejects the delete.
            #
            # Sprint 036: the same reasoning now covers every table a test
            # can legitimately create rows in under this throwaway tenant.
            # A cross-tenant isolation test's whole job is to create a
            # record in the *other* tenant and prove it is unreachable —
            # so this fixture has to be able to clean up after one. Before
            # this sprint it only removed ActivityLog/User/Tenant, and any
            # test that created so much as a customer here left a row that
            # made the next FK-constrained delete fail.
            #
            # Ordered children-before-parents, and deliberately explicit
            # rather than a cascade: a cascade on these FKs would also
            # apply in production, where deleting a tenant's data by
            # accident is exactly what the constraints exist to prevent.
            quote_ids = select(Quote.id).where(Quote.tenant_id == tenant_id)
            db.execute(delete(AutomationRun).where(AutomationRun.tenant_id == tenant_id))
            db.execute(delete(Automation).where(Automation.tenant_id == tenant_id))
            db.execute(delete(Task).where(Task.tenant_id == tenant_id))
            db.execute(delete(NotificationRecord).where(NotificationRecord.tenant_id == tenant_id))
            db.execute(delete(Appointment).where(Appointment.tenant_id == tenant_id))
            db.execute(delete(Message).where(Message.tenant_id == tenant_id))
            db.execute(delete(Document).where(Document.tenant_id == tenant_id))
            db.execute(delete(PortalLink).where(PortalLink.tenant_id == tenant_id))
            db.execute(delete(Invitation).where(Invitation.tenant_id == tenant_id))
            db.execute(delete(Project).where(Project.tenant_id == tenant_id))
            db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
            db.execute(delete(Quote).where(Quote.tenant_id == tenant_id))
            db.execute(delete(Customer).where(Customer.tenant_id == tenant_id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
            db.execute(delete(User).where(User.email == OTHER_TENANT_EMAIL))
            db.execute(delete(Tenant).where(Tenant.id == tenant_id))
            db.commit()
    finally:
        db.close()


@pytest.fixture()
def other_tenant_auth_headers(client):
    """Bearer header for a second, fully separate tenant + Owner — signs up
    fresh each test run and is torn down after, same shape as the
    created_tenant/created_customer fixtures elsewhere in this suite."""
    _cleanup_other_tenant()
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": OTHER_TENANT_COMPANY,
            "name": "Other Tenant Owner",
            "email": OTHER_TENANT_EMAIL,
            "password": OTHER_TENANT_PASSWORD,
        },
    )
    token = r.json()["access_token"]
    yield {"Authorization": f"Bearer {token}"}
    _cleanup_other_tenant()
