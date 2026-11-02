"""Purging a workspace must end access through previously issued public links."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import DateTime, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.database import get_db
from app.database.models import (
    ActivityLog, Customer, Document, Message, PortalLink, Project, Quote,
    QuoteItem, Tenant, User, WorkspaceDeletion,
)
from app.portal.router import router as portal_router
from app.privacy.router import router as privacy_router


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@pytest.fixture
def privacy_portal_api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'privacy-portal.db'}")
    for model in (Tenant, User, Customer, Project, Quote, QuoteItem, Document,
                  Message, PortalLink, ActivityLog, WorkspaceDeletion):
        model.__table__.create(engine)

    class PrivacySession(Session):
        pass

    @event.listens_for(PrivacySession, "loaded_as_persistent")
    def restore_timezone(db, row):
        # SQLite drops timezone information; PostgreSQL preserves UTC.
        for column in row.__table__.columns:
            value = getattr(row, column.name)
            if isinstance(column.type, DateTime) and column.type.timezone and value is not None and value.tzinfo is None:
                setattr(row, column.name, value.replace(tzinfo=timezone.utc))

    def database():
        with PrivacySession(engine) as db:
            yield db

    api = FastAPI()
    api.include_router(portal_router, prefix="/api/v1")
    api.include_router(privacy_router, prefix="/api/v1")
    api.dependency_overrides[get_db] = database
    monkeypatch.setattr(settings, "internal_compliance_token", "p" * 32)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    now = datetime.now(timezone.utc)
    fixtures = {}
    with PrivacySession(engine) as db:
        for identity in ("a", "b"):
            tenant = Tenant(name=f"Synthetic {identity}", slug=f"purge-portal-{identity}")
            db.add(tenant)
            db.flush()
            user = User(tenant_id=tenant.id, name="Synthetic Owner", email=f"purge-{identity}@example.invalid",
                        password_hash="unused-test-hash", role="Owner", email_verified_at=now)
            customer = Customer(tenant_id=tenant.id, name="Synthetic customer")
            db.add_all([user, customer])
            db.flush()
            quote = Quote(tenant_id=tenant.id, customer_id=customer.id,
                          price_before_vat=1000, vat=200, total=1200)
            db.add(quote)
            db.flush()
            token = f"synthetic-portal-{identity}"
            link = PortalLink(tenant_id=tenant.id, customer_id=customer.id, created_by_user_id=user.id,
                              token_hash=hashlib.sha256(token.encode()).hexdigest(), status="active",
                              expires_at=now + timedelta(days=30))
            document = Document(tenant_id=tenant.id, customer_id=customer.id, uploaded_by_user_id=user.id,
                                original_filename="synthetic.txt", storage_filename=f"synthetic-{identity}.txt",
                                content_type="text/plain", size_bytes=7)
            (tmp_path / document.storage_filename).write_bytes(b"fixture")
            db.add_all([link, document, Message(tenant_id=tenant.id, customer_id=customer.id,
                         sender_type="customer", body=f"Private synthetic message {identity}")])
            if identity == "a":
                db.add(WorkspaceDeletion(tenant_id=tenant.id, requested_by_user_id=user.id,
                       requested_at=now - timedelta(days=31), eligible_for_purge_at=now - timedelta(days=1)))
            db.flush()
            fixtures[identity] = {"tenant": tenant.id, "token": token, "link": link.id,
                                  "quote": quote.id, "document": document.id}
        db.commit()
    with TestClient(api) as client:
        yield client, engine, PrivacySession, fixtures
    engine.dispose()


def test_workspace_purge_ends_old_public_portal_access(privacy_portal_api):
    client, engine, session_type, fixtures = privacy_portal_api
    fixture = fixtures["a"]
    base = f"/api/v1/portal-links/token/{fixture['token']}"
    assert client.get(base + "/messages").json()[0]["body"] == "Private synthetic message a"
    response = client.post(f"/api/v1/privacy/internal/workspace-deletions/{fixture['tenant']}/purge",
                           headers={"X-GeoCore-Internal-Token": "p" * 32})
    assert response.status_code == 200 and response.json()["state"] == "purged"
    assert client.get(base + "/messages").status_code == 404
    with session_type(engine) as db:
        assert db.get(PortalLink, fixture["link"]).status == "revoked"
    other = client.get(f"/api/v1/portal-links/token/{fixtures['b']['token']}/messages")
    assert other.status_code == 200 and other.json()[0]["body"] == "Private synthetic message b"


@pytest.mark.parametrize("operation", ["summary", "invoice", "documents", "download", "messages", "post_message"])
def test_previously_purged_workspace_cannot_use_legacy_active_links(privacy_portal_api, operation):
    client, engine, session_type, fixtures = privacy_portal_api
    fixture = fixtures["a"]
    with session_type(engine) as db:
        db.get(Tenant, fixture["tenant"]).status = "purged"
        db.commit()
    base = f"/api/v1/portal-links/token/{fixture['token']}"
    suffix = {"summary": "", "invoice": f"/invoice/{fixture['quote']}", "documents": "/documents",
              "download": f"/documents/{fixture['document']}/download", "messages": "/messages",
              "post_message": "/messages"}[operation]
    if operation == "post_message":
        # A rejected link must not create a new message or invoke notifications.
        response = client.post(base + suffix, json={"body": "Should not be saved"})
    else:
        response = client.get(base + suffix)
    assert response.status_code == 404
    assert "Private synthetic" not in response.text
    with session_type(engine) as db:
        assert db.scalar(select(func.count()).select_from(Message).where(Message.tenant_id == fixture["tenant"])) == 1
