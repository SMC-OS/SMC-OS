"""Sprint 013 — app/portal/ (docs/DECISIONS.md ADR-030).

Covers the full lifecycle through the HTTP layer (create/list/revoke, the
public token-view route, and its reusability — the key behavioral
difference from app/invitations' single-use accept flow) plus the
"expired" derivation and full tenant/relationship isolation, exercised
the same way tests/test_invitations.py and Sprint 012's cross-tenant
suite already do.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.database import crud
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, PortalLink, Project, Quote

TEST_CUSTOMER_NAME = "Pytest Portal Customer"
OTHER_CUSTOMER_NAME = "Pytest Portal Other Customer"
TEST_PROJECT_NAME = "Pytest Portal Project"
TEST_QUOTE_POSTCODE = "PYTESTPORTAL1"


def _cleanup():
    db = SessionLocal()
    try:
        customer_ids = [
            row.id
            for row in db.query(Customer)
            .filter(Customer.name.in_([TEST_CUSTOMER_NAME, OTHER_CUSTOMER_NAME]))
            .all()
        ]
        if customer_ids:
            db.execute(delete(PortalLink).where(PortalLink.customer_id.in_(customer_ids)))
        db.execute(delete(Project).where(Project.name == TEST_PROJECT_NAME))
        db.execute(delete(Quote).where(Quote.postcode == TEST_QUOTE_POSTCODE))
        db.execute(
            delete(ActivityLog).where(
                ActivityLog.description.in_([TEST_CUSTOMER_NAME, OTHER_CUSTOMER_NAME, TEST_PROJECT_NAME])
            )
        )
        db.execute(delete(Customer).where(Customer.name.in_([TEST_CUSTOMER_NAME, OTHER_CUSTOMER_NAME])))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def created_customer(client, auth_headers):
    _cleanup()
    r = client.post("/api/v1/customers", json={"name": TEST_CUSTOMER_NAME}, headers=auth_headers)
    customer = r.json()

    client.post(
        "/api/v1/projects",
        json={"name": TEST_PROJECT_NAME, "customer_id": customer["id"]},
        headers=auth_headers,
    )
    client.post(
        "/api/v1/quote",
        json={
            "customer": TEST_CUSTOMER_NAME,
            "customer_id": customer["id"],
            "material": "calacatta gold",
            "thickness": "20mm",
            "kitchen_length": 3.0,
            "postcode": TEST_QUOTE_POSTCODE,
        },
        headers=auth_headers,
    )
    yield customer
    _cleanup()


@pytest.fixture()
def created_portal_link(client, auth_headers, created_customer):
    r = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    )
    return r.json()


def test_create_portal_link_success(client, auth_headers, created_customer):
    r = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    )
    assert r.status_code == 201
    body = r.json()
    assert body["customer_id"] == created_customer["id"]
    assert body["status"] == "active"
    assert body["token"]


def test_create_portal_link_unknown_customer_returns_404(client, auth_headers):
    r = client.post(
        "/api/v1/portal-links", json={"customer_id": str(uuid.uuid4())}, headers=auth_headers
    )
    assert r.status_code == 404


def test_create_portal_link_cross_tenant_customer_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_customer
):
    r = client.post(
        "/api/v1/portal-links",
        json={"customer_id": created_customer["id"]},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404


def test_portal_link_routes_require_auth(client, created_customer):
    assert (
        client.post("/api/v1/portal-links", json={"customer_id": created_customer["id"]}).status_code
        == 401
    )
    assert client.get("/api/v1/portal-links").status_code == 401
    assert client.delete(f"/api/v1/portal-links/{uuid.uuid4()}").status_code == 401


def test_list_portal_links_scoped_to_tenant(client, auth_headers, created_portal_link):
    r = client.get("/api/v1/portal-links", headers=auth_headers)
    assert r.status_code == 200
    ids = [link["id"] for link in r.json()]
    assert created_portal_link["id"] in ids


def test_revoke_portal_link(client, auth_headers, created_portal_link):
    r = client.delete(f"/api/v1/portal-links/{created_portal_link['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"


def test_revoke_unknown_portal_link_returns_404(client, auth_headers):
    r = client.delete(f"/api/v1/portal-links/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


def test_revoke_cross_tenant_portal_link_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_portal_link
):
    r = client.delete(
        f"/api/v1/portal-links/{created_portal_link['id']}", headers=other_tenant_auth_headers
    )
    assert r.status_code == 404


def test_get_portal_by_token_public(client, created_portal_link):
    r = client.get(f"/api/v1/portal-links/token/{created_portal_link['token']}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active"
    assert body["customer_name"] == TEST_CUSTOMER_NAME
    assert any(p["name"] == TEST_PROJECT_NAME for p in body["projects"])
    assert any(q["material"] == "calacatta gold" for q in body["quotes"])
    assert "id" not in body
    assert "customer_id" not in body


def test_get_portal_by_unknown_token_returns_404(client):
    r = client.get("/api/v1/portal-links/token/not-a-real-token")
    assert r.status_code == 404


def test_portal_link_is_reusable(client, created_portal_link):
    """The key behavioral difference from Invitation.accept: fetching the
    same active token twice must succeed both times, with no state
    change."""
    first = client.get(f"/api/v1/portal-links/token/{created_portal_link['token']}")
    second = client.get(f"/api/v1/portal-links/token/{created_portal_link['token']}")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "active"


def test_revoked_portal_link_reads_as_revoked_and_returns_no_data(
    client, auth_headers, created_portal_link
):
    client.delete(f"/api/v1/portal-links/{created_portal_link['id']}", headers=auth_headers)

    r = client.get(f"/api/v1/portal-links/token/{created_portal_link['token']}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "revoked"
    assert body["projects"] == []
    assert body["quotes"] == []


def test_expired_portal_link_reads_as_expired_and_returns_no_data(
    client, auth_headers, created_customer
):
    raw_token = "pytest-expired-portal-link-raw-token"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    db = SessionLocal()
    try:
        crud.create_portal_link(
            db,
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(me["tenant_id"]),
            customer_id=uuid.UUID(created_customer["id"]),
            created_by_user_id=uuid.UUID(me["id"]),
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    finally:
        db.close()

    r = client.get(f"/api/v1/portal-links/token/{raw_token}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "expired"
    assert body["projects"] == []
    assert body["quotes"] == []


def test_portal_returns_only_that_customers_projects_and_quotes(client, auth_headers, created_customer):
    _cleanup_other_customer = "Pytest Portal Unrelated Customer"
    db = SessionLocal()
    try:
        db.execute(delete(Customer).where(Customer.name == _cleanup_other_customer))
        db.commit()
    finally:
        db.close()

    try:
        other_customer = client.post(
            "/api/v1/customers", json={"name": _cleanup_other_customer}, headers=auth_headers
        ).json()
        client.post(
            "/api/v1/projects",
            json={"name": "Pytest Portal Unrelated Project", "customer_id": other_customer["id"]},
            headers=auth_headers,
        )

        link = client.post(
            "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
        ).json()

        r = client.get(f"/api/v1/portal-links/token/{link['token']}")
        names = [p["name"] for p in r.json()["projects"]]
        assert TEST_PROJECT_NAME in names
        assert "Pytest Portal Unrelated Project" not in names
    finally:
        db = SessionLocal()
        try:
            db.execute(
                delete(Project).where(Project.name == "Pytest Portal Unrelated Project")
            )
            db.execute(delete(Customer).where(Customer.name == _cleanup_other_customer))
            db.commit()
        finally:
            db.close()


def test_download_portal_invoice_success(client, auth_headers, created_portal_link):
    quote = client.get("/api/v1/quotes", headers=auth_headers).json()[0]

    r = client.get(f"/api/v1/portal-links/token/{created_portal_link['token']}/invoice/{quote['id']}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_download_portal_invoice_unknown_quote_returns_404(client, created_portal_link):
    r = client.get(
        f"/api/v1/portal-links/token/{created_portal_link['token']}/invoice/{uuid.uuid4()}"
    )
    assert r.status_code == 404


def test_download_portal_invoice_wrong_customer_returns_404(
    client, auth_headers, created_portal_link
):
    """A quote belonging to a *different* customer in the same tenant must
    not be downloadable through this link — the token only grants access
    to its own customer_id's data, not the whole tenant's."""
    other_customer = client.post(
        "/api/v1/customers", json={"name": "Pytest Portal Wrong Customer"}, headers=auth_headers
    ).json()
    other_quote = client.post(
        "/api/v1/quote",
        json={
            "customer": "Pytest Portal Wrong Customer",
            "customer_id": other_customer["id"],
            "material": "calacatta gold",
            "thickness": "20mm",
            "kitchen_length": 2.0,
            "postcode": "PYTESTPORTAL2",
        },
        headers=auth_headers,
    ).json()

    try:
        r = client.get(
            f"/api/v1/portal-links/token/{created_portal_link['token']}/invoice/{other_quote['id']}"
        )
        assert r.status_code == 404
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(Quote).where(Quote.postcode == "PYTESTPORTAL2"))
            db.execute(delete(Customer).where(Customer.name == "Pytest Portal Wrong Customer"))
            db.commit()
        finally:
            db.close()


def test_download_portal_invoice_revoked_link_returns_404(
    client, auth_headers, created_portal_link
):
    quote = client.get("/api/v1/quotes", headers=auth_headers).json()[0]
    client.delete(f"/api/v1/portal-links/{created_portal_link['id']}", headers=auth_headers)

    r = client.get(f"/api/v1/portal-links/token/{created_portal_link['token']}/invoice/{quote['id']}")
    assert r.status_code == 404


def test_portal_cross_tenant_isolation(
    client, auth_headers, other_tenant_auth_headers, created_portal_link
):
    """A token minted under tenant A must never surface tenant B's data —
    confirmed by creating a same-named project under tenant B and checking
    tenant A's portal link still only shows tenant A's project."""
    db = SessionLocal()
    try:
        db.execute(delete(Customer).where(Customer.name == OTHER_CUSTOMER_NAME))
        db.commit()
    finally:
        db.close()

    try:
        other_customer = client.post(
            "/api/v1/customers", json={"name": OTHER_CUSTOMER_NAME}, headers=other_tenant_auth_headers
        ).json()
        client.post(
            "/api/v1/projects",
            json={"name": TEST_PROJECT_NAME, "customer_id": other_customer["id"]},
            headers=other_tenant_auth_headers,
        )

        r = client.get(f"/api/v1/portal-links/token/{created_portal_link['token']}")
        body = r.json()
        assert body["customer_name"] == TEST_CUSTOMER_NAME
        assert len(body["projects"]) == 1
    finally:
        db = SessionLocal()
        try:
            # The other tenant's project shares TEST_PROJECT_NAME with
            # tenant A's — delete both before either customer, same
            # child-before-parent FK ordering Sprint 012 established.
            db.execute(delete(Project).where(Project.name == TEST_PROJECT_NAME))
            db.execute(delete(Customer).where(Customer.name == OTHER_CUSTOMER_NAME))
            db.commit()
        finally:
            db.close()
