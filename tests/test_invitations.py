"""Sprint 011 — app/invitations/ (docs/DECISIONS.md ADR-028).

Covers the full lifecycle through the HTTP layer (create/list/revoke/accept,
the public token-view route, and require_role(OWNER) actually rejecting a
Staff caller — the first route in the codebase where that matters) plus the
"expired" derivation (InvitationService.derive_status()), exercised via a
row seeded directly through crud so its expires_at can be forced into the
past without waiting.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Invitation, Tenant, User
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

TENANT_NAME = "Pytest Invitations Tenant"
OWNER_EMAIL = "pytest-invitations-owner@example.invalid"
STAFF_EMAIL = "pytest-invitations-staff@example.invalid"
INVITEE_EMAIL = "pytest-invitations-invitee@example.invalid"
EXPIRED_INVITEE_EMAIL = "pytest-invitations-expired@example.invalid"
ALREADY_USER_EMAIL = "pytest-invitations-already-user@example.invalid"
PASSWORD = "correct-horse-battery-staple"


def _cleanup():
    db = SessionLocal()
    try:
        emails = [OWNER_EMAIL, STAFF_EMAIL, INVITEE_EMAIL, EXPIRED_INVITEE_EMAIL, ALREADY_USER_EMAIL]
        db.execute(delete(Invitation).where(Invitation.email.in_(emails)))
        db.execute(delete(User).where(User.email.in_(emails)))
        # Sprint 012: TenantService.create() now logs a real ActivityLog row
        # against the new tenant's own id (ADR-029) — must be deleted before
        # the Tenant row or the FK constraint (ADR-025) rejects the delete.
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
        db.execute(delete(Tenant).where(Tenant.name == TENANT_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def owner_and_staff():
    """A tenant with a real Owner and a real (non-invited) Staff user —
    enough to exercise require_role(OWNER) rejecting a Staff caller without
    depending on the invitation-accept flow under test."""
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


def test_create_invitation_requires_owner_role(client, owner_headers, staff_headers):
    r = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=staff_headers)
    assert r.status_code == 403


def test_invitation_routes_require_auth(client):
    assert client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}).status_code == 401
    assert client.get("/api/v1/invitations").status_code == 401
    assert client.delete(f"/api/v1/invitations/{uuid.uuid4()}").status_code == 401


def test_create_invitation_success(client, owner_headers):
    r = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == INVITEE_EMAIL
    assert body["role"] == "Staff"
    assert body["status"] == "pending"
    assert body["token"]


def test_create_invitation_duplicate_email_conflict(client, owner_headers, owner_and_staff):
    r = client.post("/api/v1/invitations", json={"email": OWNER_EMAIL}, headers=owner_headers)
    assert r.status_code == 409


def test_create_invitation_pending_already_exists_conflict(client, owner_headers):
    first = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers)
    assert first.status_code == 201
    second = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers)
    assert second.status_code == 409


def test_list_invitations_scoped_to_tenant(client, owner_headers):
    client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers)
    r = client.get("/api/v1/invitations", headers=owner_headers)
    assert r.status_code == 200
    emails = [inv["email"] for inv in r.json()]
    assert INVITEE_EMAIL in emails


def test_revoke_invitation(client, owner_headers):
    created = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers).json()
    r = client.delete(f"/api/v1/invitations/{created['id']}", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"


def test_revoke_unknown_invitation_returns_404(client, owner_headers):
    r = client.delete(f"/api/v1/invitations/{uuid.uuid4()}", headers=owner_headers)
    assert r.status_code == 404


def test_revoke_cross_tenant_invitation_returns_404(
    client, owner_headers, other_tenant_auth_headers
):
    """A second tenant's Owner must not be able to revoke this tenant's
    invitation — and the failure must read identically to "doesn't exist"
    (404, not 403), per ADR-028's cross-tenant-lookup-leak reasoning.

    Sprint 012: reuses the shared other_tenant_auth_headers fixture
    (tests/conftest.py) instead of hand-rolling a second tenant/owner here
    — same isolation guarantee, one fewer place that has to remember to
    delete a tenant's ActivityLog row before the tenant itself (ADR-029)."""
    created = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers).json()

    r = client.delete(f"/api/v1/invitations/{created['id']}", headers=other_tenant_auth_headers)
    assert r.status_code == 404


def test_get_invitation_by_token_public(client, owner_headers):
    created = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers).json()
    r = client.get(f"/api/v1/invitations/token/{created['token']}")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == INVITEE_EMAIL
    assert body["role"] == "Staff"
    assert body["tenant_name"] == TENANT_NAME
    assert body["status"] == "pending"
    assert "id" not in body


def test_get_invitation_by_unknown_token_returns_404(client):
    r = client.get("/api/v1/invitations/token/not-a-real-token")
    assert r.status_code == 404


def test_accept_invitation_creates_staff_user_and_logs_in(client, owner_headers):
    created = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers).json()

    r = client.post(
        f"/api/v1/invitations/token/{created['token']}/accept",
        json={"name": "New Staffer", "password": PASSWORD},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == INVITEE_EMAIL
    assert body["user"]["role"] == "Staff"
    assert body["user"]["tenant_name"] == TENANT_NAME

    # The new user can log in normally afterwards.
    login = client.post("/api/v1/auth/login", json={"email": INVITEE_EMAIL, "password": PASSWORD})
    assert login.status_code == 200


def test_accept_invitation_unknown_token_returns_404(client):
    r = client.post(
        "/api/v1/invitations/token/not-a-real-token/accept",
        json={"name": "X", "password": PASSWORD},
    )
    assert r.status_code == 404


def test_accept_invitation_twice_returns_409(client, owner_headers):
    created = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers).json()
    first = client.post(
        f"/api/v1/invitations/token/{created['token']}/accept",
        json={"name": "New Staffer", "password": PASSWORD},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/invitations/token/{created['token']}/accept",
        json={"name": "New Staffer", "password": PASSWORD},
    )
    assert second.status_code == 409


def test_accept_revoked_invitation_returns_409(client, owner_headers):
    created = client.post("/api/v1/invitations", json={"email": INVITEE_EMAIL}, headers=owner_headers).json()
    client.delete(f"/api/v1/invitations/{created['id']}", headers=owner_headers)

    r = client.post(
        f"/api/v1/invitations/token/{created['token']}/accept",
        json={"name": "New Staffer", "password": PASSWORD},
    )
    assert r.status_code == 409
    assert "revoked" in r.json()["detail"].lower()


def test_accept_invitation_email_registered_between_invite_and_accept_returns_409(client, owner_headers):
    created = client.post("/api/v1/invitations", json={"email": ALREADY_USER_EMAIL}, headers=owner_headers).json()

    db = SessionLocal()
    try:
        tenant = tenant_service.get(db, uuid.UUID(created["tenant_id"]))
        auth_service.create_user(
            db, tenant_id=tenant.id, name="Snuck In First", email=ALREADY_USER_EMAIL, password=PASSWORD, role="Staff"
        )
    finally:
        db.close()

    r = client.post(
        f"/api/v1/invitations/token/{created['token']}/accept",
        json={"name": "New Staffer", "password": PASSWORD},
    )
    assert r.status_code == 409


def test_expired_invitation_reads_as_expired_and_cannot_be_accepted(client, owner_headers, owner_and_staff):
    tenant, owner, _staff = owner_and_staff
    raw_token = "pytest-expired-invitation-raw-token"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    db = SessionLocal()
    try:
        crud.create_invitation(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            invited_by_user_id=owner.id,
            email=EXPIRED_INVITEE_EMAIL,
            role="Staff",
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    finally:
        db.close()

    public = client.get(f"/api/v1/invitations/token/{raw_token}")
    assert public.status_code == 200
    assert public.json()["status"] == "expired"

    listed = client.get("/api/v1/invitations", headers=owner_headers)
    matching = [inv for inv in listed.json() if inv["email"] == EXPIRED_INVITEE_EMAIL]
    assert matching and matching[0]["status"] == "expired"

    accept = client.post(
        f"/api/v1/invitations/token/{raw_token}/accept",
        json={"name": "Too Late", "password": PASSWORD},
    )
    assert accept.status_code == 409
    assert "expired" in accept.json()["detail"].lower()
