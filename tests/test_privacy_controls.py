"""Focused database-backed coverage for the Phase 2 privacy controls.

All requests use TestClient and the disposable local database selected by
DATABASE_URL; these tests never construct a real email or AI provider.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, update

from app.auth.models import UserRole
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    CopyrightCase,
    Customer,
    EmailSuppression,
    EmailVerificationToken,
    MarketingPreference,
    MarketingUnsubscribeToken,
    Subscription,
    Tenant,
    User,
    Project,
    Quote,
    WorkspaceDeletion,
    WorkspaceExport,
)


def _cleanup_workspace(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            return
        tenant_id = user.tenant_id
        db.execute(delete(MarketingUnsubscribeToken).where(MarketingUnsubscribeToken.tenant_id == tenant_id))
        db.execute(delete(MarketingPreference).where(MarketingPreference.tenant_id == tenant_id))
        db.execute(delete(WorkspaceExport).where(WorkspaceExport.tenant_id == tenant_id))
        db.execute(delete(WorkspaceDeletion).where(WorkspaceDeletion.tenant_id == tenant_id))
        db.execute(delete(EmailSuppression).where(EmailSuppression.tenant_id == tenant_id))
        db.execute(delete(Communication).where(Communication.tenant_id == tenant_id))
        db.execute(delete(Project).where(Project.tenant_id == tenant_id))
        db.execute(delete(Quote).where(Quote.tenant_id == tenant_id))
        db.execute(delete(Customer).where(Customer.tenant_id == tenant_id))
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
        db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(User).where(User.id == user.id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def workspace(client):
    email = f"phase2-{uuid.uuid4().hex}@example.invalid"
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": f"Phase 2 {uuid.uuid4().hex[:8]}",
            "name": "Phase Two Owner",
            "email": email,
            "password": "Phase-2-Validation-Password-1!",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    tenant_id = uuid.UUID(data["user"]["tenant_id"])
    db = SessionLocal()
    try:
        db.execute(update(User).where(User.email == email).values(email_verified_at=datetime.now(timezone.utc)))
        crud.upsert_subscription(
            db,
            tenant_id=tenant_id,
            plan="pro",
            billing_period="monthly",
            status="active",
            legacy_grandfathered=True,
        )
        db.commit()
    finally:
        db.close()
    try:
        yield {"Authorization": f"Bearer {data['access_token']}"}, tenant_id, email
    finally:
        _cleanup_workspace(email)


def test_owner_export_is_one_time_and_tenant_scoped(client, workspace):
    headers, _, _ = workspace
    created = client.post("/api/v1/privacy/exports", headers=headers)
    assert created.status_code == 201
    export_id = created.json()["id"]

    downloaded = client.get(f"/api/v1/privacy/exports/{export_id}/download", headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/zip")
    assert downloaded.headers["content-disposition"] == "attachment; filename=geocore-workspace-export.zip"
    assert downloaded.headers["cache-control"] == "no-store"
    assert client.get(f"/api/v1/privacy/exports/{export_id}/download", headers=headers).status_code == 410


def test_other_tenant_cannot_download_export(client, workspace):
    owner_headers, _, _ = workspace
    created = client.post("/api/v1/privacy/exports", headers=owner_headers)
    assert created.status_code == 201
    other_email = f"phase2-other-{uuid.uuid4().hex}@example.invalid"
    signup = client.post("/api/v1/auth/signup", json={"company_name": "Other phase 2", "name": "Other Owner", "email": other_email, "password": "Phase-2-Validation-Password-1!"})
    assert signup.status_code == 201
    other = signup.json()
    other_tenant_id = uuid.UUID(other["user"]["tenant_id"])
    db = SessionLocal()
    try:
        db.execute(update(User).where(User.email == other_email).values(email_verified_at=datetime.now(timezone.utc)))
        crud.upsert_subscription(db, tenant_id=other_tenant_id, plan="pro", billing_period="monthly", status="active", legacy_grandfathered=True)
        db.commit()
        response = client.get(f"/api/v1/privacy/exports/{created.json()['id']}/download", headers={"Authorization": f"Bearer {other['access_token']}"})
        assert response.status_code == 404
    finally:
        db.close()
        _cleanup_workspace(other_email)


def test_marketing_preference_and_opaque_unsubscribe_are_idempotent(client, workspace):
    headers, tenant_id, email = workspace
    assert client.get("/api/v1/privacy/marketing-preference", headers=headers).json()["enabled"] is False
    disabled = client.put("/api/v1/privacy/marketing-preference", headers=headers, json={"enabled": False})
    assert disabled.status_code == 200 and disabled.json()["enabled"] is False
    assert client.put("/api/v1/privacy/marketing-preference", headers=headers, json={"enabled": True}).json()["enabled"] is True

    token = "phase2-unsubscribe-token"
    db = SessionLocal()
    try:
        db.add(MarketingUnsubscribeToken(id=uuid.uuid4(), tenant_id=tenant_id, email=email, token_hash=hashlib.sha256(token.encode()).hexdigest()))
        db.commit()
    finally:
        db.close()
    path = f"/api/v1/privacy/marketing-unsubscribe/{token}"
    assert client.post(path).status_code == 204
    assert client.post(path).status_code == 204
    preference = client.get("/api/v1/privacy/marketing-preference", headers=headers).json()
    assert preference["enabled"] is False and preference["source"] == "unsubscribe"
    invalid = client.post("/api/v1/privacy/marketing-unsubscribe/not-a-valid-token")
    assert invalid.status_code == 404
    assert str(tenant_id) not in invalid.text and email not in invalid.text


def test_workspace_deletion_requires_owner_confirmation_and_enforces_recovery(client, workspace):
    headers, tenant_id, _ = workspace
    assert client.post("/api/v1/privacy/workspace-deletion", headers=headers, json={"confirmation": "delete"}).status_code == 422
    requested = client.post("/api/v1/privacy/workspace-deletion", headers=headers, json={"confirmation": "DELETE WORKSPACE"})
    assert requested.status_code == 200
    assert requested.json()["state"] == "deletion_requested"
    requested_at = datetime.fromisoformat(requested.json()["requested_at"].replace("Z", "+00:00"))
    eligible_at = datetime.fromisoformat(requested.json()["eligible_for_purge_at"].replace("Z", "+00:00"))
    assert eligible_at - requested_at == timedelta(days=30)

    db = SessionLocal()
    try:
        db.execute(update(User).where(User.tenant_id == tenant_id).values(role=UserRole.STAFF))
        db.commit()
        assert client.post("/api/v1/privacy/workspace-deletion/cancel", headers=headers).status_code == 403
    finally:
        db.close()


def test_internal_purge_requires_dedicated_token_and_is_idempotent(client, workspace, monkeypatch):
    headers, tenant_id, _ = workspace
    assert client.post("/api/v1/privacy/workspace-deletion", headers=headers, json={"confirmation": "DELETE WORKSPACE"}).status_code == 200
    project_response = client.post("/api/v1/projects", headers=headers, json={"name": "Private project"})
    assert project_response.status_code == 201
    project_id = uuid.UUID(project_response.json()["id"])
    db = SessionLocal()
    try:
        db.execute(update(WorkspaceDeletion).where(WorkspaceDeletion.tenant_id == tenant_id).values(eligible_for_purge_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.add(EmailSuppression(id=uuid.uuid4(), tenant_id=tenant_id, email="retained@example.invalid", reason="complaint"))
        db.add(Customer(id=uuid.uuid4(), tenant_id=tenant_id, name="Private customer", email="customer@example.invalid", address_line1="1 Private Road", postcode="NW2 7RP", notes="private notes"))
        db.execute(update(Project).where(Project.id == project_id).values(notes="private notes", description="private description", site_address_line1="1 Private Road", site_postcode="NW2 7RP"))
        db.add(Quote(id=uuid.uuid4(), tenant_id=tenant_id, title="Private quote", site_address_line1="1 Private Road", site_postcode="NW2 7RP", scope_of_works="private scope", notes="private notes"))
        db.commit()
    finally:
        db.close()
    endpoint = f"/api/v1/privacy/internal/workspace-deletions/{tenant_id}/purge"
    assert client.post(endpoint, headers=headers).status_code == 403
    internal_token = "t" * 32
    monkeypatch.setattr(settings, "internal_compliance_token", internal_token)
    first = client.post(endpoint, headers={"X-GeoCore-Internal-Token": internal_token})
    assert first.status_code == 200 and first.json()["state"] == "purged"
    second = client.post(endpoint, headers={"X-GeoCore-Internal-Token": internal_token})
    assert second.status_code == 200 and second.json()["state"] == "purged"
    db = SessionLocal()
    try:
        assert db.query(EmailSuppression).filter_by(tenant_id=tenant_id, email="retained@example.invalid").count() == 1
        customer = db.query(Customer).filter_by(tenant_id=tenant_id).one()
        project = db.query(Project).filter_by(tenant_id=tenant_id).one()
        quote = db.query(Quote).filter_by(tenant_id=tenant_id).one()
        assert customer.name == "Deleted customer" and customer.email is None and customer.notes is None
        assert project.name == "Deleted project" and project.site_address_line1 is None and project.notes is None
        assert quote.title == "Deleted quote" and quote.site_address_line1 is None and quote.scope_of_works is None
    finally:
        db.close()


def test_copyright_intake_is_public_but_administration_requires_internal_token(client, monkeypatch):
    payload = {"reporter_name": "Reporter", "reporter_email": "reporter@example.invalid", "work_description": "A work", "location": "https://example.invalid/location", "statement": "I believe this is unauthorised."}
    created = client.post("/api/v1/compliance/copyright-reports", json=payload)
    assert created.status_code == 201
    case_id = created.json()["id"]
    assert client.get("/api/v1/compliance/internal/copyright-reports").status_code == 403
    internal_token = "c" * 32
    monkeypatch.setattr(settings, "internal_compliance_token", internal_token)
    updated = client.patch(f"/api/v1/compliance/internal/copyright-reports/{case_id}", headers={"X-GeoCore-Internal-Token": internal_token}, json={"status": "under_review", "internal_notes": "Reviewed locally."})
    assert updated.status_code == 200 and updated.json()["status"] == "under_review"
    db = SessionLocal()
    try:
        db.execute(delete(CopyrightCase).where(CopyrightCase.id == uuid.UUID(case_id)))
        db.commit()
    finally:
        db.close()
