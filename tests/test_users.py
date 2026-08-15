"""Sprint 015 — app/users/ (docs/DECISIONS.md ADR-031).

Covers the full lifecycle through the HTTP layer: listing a tenant's team,
deactivating a Staff member, require_role(OWNER) rejecting a Staff caller,
self-deactivation blocked, cross-tenant isolation, and that a deactivated
teammate's portal links keep resolving (no cascade). The deactivated user's
own existing token actually being rejected is covered separately in this
same file once Task 3 wires that check into get_current_user.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.customers.models import CustomerCreate
from app.customers.service import customer_service
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, PortalLink, Tenant, User
from app.portal.service import portal_service
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

TENANT_NAME = "Pytest Users Tenant"
OWNER_EMAIL = "pytest-users-owner@example.invalid"
STAFF_EMAIL = "pytest-users-staff@example.invalid"
PASSWORD = "correct-horse-battery-staple"


def _cleanup():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            # FK-safe order: PortalLink references both Customer and
            # User(created_by_user_id) — delete it before either. Customer
            # and ActivityLog both reference Tenant only. User rows last
            # (PortalLink.created_by_user_id/Invitation.invited_by_user_id
            # reference them), Tenant last of all.
            db.execute(delete(PortalLink).where(PortalLink.tenant_id == tenant.id))
            db.execute(delete(Customer).where(Customer.tenant_id == tenant.id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
        db.execute(delete(User).where(User.email.in_([OWNER_EMAIL, STAFF_EMAIL])))
        db.execute(delete(Tenant).where(Tenant.name == TENANT_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def owner_and_staff():
    """A tenant with a real Owner and a real (non-invited) Staff user —
    same shape as tests/test_invitations.py's fixture of the same name."""
    _cleanup()
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=TENANT_NAME))
        owner = auth_service.create_user(
            db, tenant_id=tenant.id, name="Pytest Owner", email=OWNER_EMAIL, password=PASSWORD, role="Owner"
        )
        staff = auth_service.create_user(
            db, tenant_id=tenant.id, name="Pytest Staff", email=STAFF_EMAIL, password=PASSWORD, role="Staff"
        )
        yield tenant, owner, staff
    finally:
        db.close()
        _cleanup()


@pytest.fixture()
def owner_headers(client, owner_and_staff):
    r = client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def staff_headers(client, owner_and_staff):
    r = client.post("/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_users_returns_owner_and_staff(client, owner_headers, owner_and_staff):
    r = client.get("/api/v1/users", headers=owner_headers)
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert emails == {OWNER_EMAIL, STAFF_EMAIL}
    assert all(u["is_active"] is True for u in r.json())


def test_list_users_requires_owner_role(client, staff_headers):
    r = client.get("/api/v1/users", headers=staff_headers)
    assert r.status_code == 403


def test_deactivate_user_flips_is_active_and_logs_activity(client, owner_headers, owner_and_staff):
    _, _, staff = owner_and_staff
    r = client.post(f"/api/v1/users/{staff.id}/deactivate", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    activity = client.get(
        "/api/v1/activity?limit=50&type=team_member_deactivated", headers=owner_headers
    )
    events = activity.json()
    assert any(e["description"] == "Pytest Staff" for e in events)
    assert all(e["title"] == "Team member deactivated" for e in events)


def test_deactivate_activity_not_visible_to_other_tenant(
    client, owner_headers, other_tenant_auth_headers, owner_and_staff
):
    _, _, staff = owner_and_staff
    client.post(f"/api/v1/users/{staff.id}/deactivate", headers=owner_headers)

    activity = client.get(
        "/api/v1/activity?limit=50&type=team_member_deactivated", headers=other_tenant_auth_headers
    )
    events = activity.json()
    assert not any(e["description"] == "Pytest Staff" for e in events)


def test_deactivate_self_returns_409(client, owner_headers, owner_and_staff):
    _, owner, _ = owner_and_staff
    r = client.post(f"/api/v1/users/{owner.id}/deactivate", headers=owner_headers)
    assert r.status_code == 409


def test_deactivate_unknown_user_returns_404(client, owner_headers):
    r = client.post(f"/api/v1/users/{uuid.uuid4()}/deactivate", headers=owner_headers)
    assert r.status_code == 404


def test_deactivate_cross_tenant_user_returns_404(
    client, owner_headers, other_tenant_auth_headers, owner_and_staff
):
    _, _, staff = owner_and_staff
    r = client.post(f"/api/v1/users/{staff.id}/deactivate", headers=other_tenant_auth_headers)
    assert r.status_code == 404


def test_deactivated_users_portal_links_still_resolve(client, owner_headers, owner_and_staff, db):
    """Deliberate: deactivation does NOT cascade-revoke portal links the
    teammate created (spec §4/§11/§15) — tenant-owned data, not tied to
    who happened to generate the link."""
    tenant, _, staff = owner_and_staff
    customer = customer_service.create(db, CustomerCreate(name="Pytest Users Portal Customer"), tenant.id)
    _, raw_token = portal_service.create_link(
        db, tenant_id=tenant.id, created_by_user_id=staff.id, customer_id=customer.id
    )

    client.post(f"/api/v1/users/{staff.id}/deactivate", headers=owner_headers)

    r = client.get(f"/api/v1/portal-links/token/{raw_token}")
    assert r.status_code == 200


def test_deactivated_users_existing_token_is_rejected(
    client, owner_headers, owner_and_staff, staff_headers
):
    """staff_headers logs in (issuing a real, unexpired token) via its own
    fixture before this test body runs — deactivation then happens with
    that token already issued, exercising "an existing session stops
    working," not just "can't log in again.\""""
    _, _, staff = owner_and_staff
    client.post(f"/api/v1/users/{staff.id}/deactivate", headers=owner_headers)

    r = client.get("/api/v1/auth/me", headers=staff_headers)
    assert r.status_code == 401
