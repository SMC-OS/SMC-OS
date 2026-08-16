"""Sprint 016 — app/documents/ (docs/DECISIONS.md ADR-032).

Covers the full lifecycle through the HTTP layer: upload (success,
cross-tenant customer_id rejected, oversized rejected, disallowed
extension rejected), staff list/download, cross-tenant staff download
rejected. Portal-token-side access (list/download/isolation/revoked-link)
is covered separately in this same file once Task 3 adds those routes.
"""

import io
import uuid

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Document, PortalLink

TEST_CUSTOMER_NAME = "Pytest Documents Customer"


def _cleanup():
    db = SessionLocal()
    try:
        customer_ids = [
            row.id for row in db.query(Customer).filter(Customer.name == TEST_CUSTOMER_NAME).all()
        ]
        if customer_ids:
            # FK-safe order: PortalLink and Document both reference
            # Customer — delete both before the Customer row itself.
            db.execute(delete(PortalLink).where(PortalLink.customer_id.in_(customer_ids)))
            db.execute(delete(Document).where(Document.customer_id.in_(customer_ids)))
        db.execute(
            delete(ActivityLog).where(ActivityLog.description == TEST_CUSTOMER_NAME)
        )
        db.execute(delete(Customer).where(Customer.name == TEST_CUSTOMER_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def created_customer(client, auth_headers):
    _cleanup()
    r = client.post("/api/v1/customers", json={"name": TEST_CUSTOMER_NAME}, headers=auth_headers)
    yield r.json()
    _cleanup()


def _pdf_bytes(size: int = 100) -> bytes:
    return b"%PDF-1.4\n" + (b"0" * size)


def test_upload_document_success(client, auth_headers, created_customer):
    r = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["original_filename"] == "contract.pdf"
    assert body["size_bytes"] == len(_pdf_bytes())
    assert "storage_filename" not in body  # never exposed to any client


def test_upload_document_cross_tenant_customer_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_customer
):
    r = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404


def test_upload_document_too_large_returns_413(client, auth_headers, created_customer):
    oversized = io.BytesIO(b"0" * (20 * 1024 * 1024 + 1))
    r = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("big.pdf", oversized, "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 413


def test_upload_document_disallowed_extension_returns_422(client, auth_headers, created_customer):
    r = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("script.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_list_documents_is_tenant_scoped(client, auth_headers, created_customer):
    client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    r = client.get(f"/api/v1/documents?customer_id={created_customer['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert any(d["original_filename"] == "contract.pdf" for d in r.json())


def test_download_document_success(client, auth_headers, created_customer):
    upload = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = upload.json()["id"]
    r = client.get(f"/api/v1/documents/{doc_id}/download", headers=auth_headers)
    assert r.status_code == 200
    assert r.content == _pdf_bytes()
    assert 'attachment; filename="contract.pdf"' in r.headers["content-disposition"]


def test_download_document_cross_tenant_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_customer
):
    upload = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = upload.json()["id"]
    r = client.get(f"/api/v1/documents/{doc_id}/download", headers=other_tenant_auth_headers)
    assert r.status_code == 404


def test_download_unknown_document_returns_404(client, auth_headers):
    r = client.get(f"/api/v1/documents/{uuid.uuid4()}/download", headers=auth_headers)
    assert r.status_code == 404


def test_portal_lists_only_that_customers_documents(client, auth_headers, created_customer):
    client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()

    r = client.get(f"/api/v1/portal-links/token/{link['token']}/documents")
    assert r.status_code == 200
    assert any(d["original_filename"] == "contract.pdf" for d in r.json())


def test_portal_downloads_document_successfully(client, auth_headers, created_customer):
    upload = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = upload.json()["id"]
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()

    r = client.get(f"/api/v1/portal-links/token/{link['token']}/documents/{doc_id}/download")
    assert r.status_code == 200
    assert r.content == _pdf_bytes()
    assert 'attachment; filename="contract.pdf"' in r.headers["content-disposition"]


def test_portal_cannot_download_another_customers_document(client, auth_headers, created_customer):
    """A document belonging to a different customer in the SAME tenant,
    requested through a portal link scoped to created_customer, must 404
    — this is the relationship-bypass check on the public path, distinct
    from cross-tenant isolation."""
    other = client.post(
        "/api/v1/customers", json={"name": "Pytest Documents Other Customer"}, headers=auth_headers
    ).json()
    try:
        upload = client.post(
            f"/api/v1/documents?customer_id={other['id']}",
            files={"file": ("other.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
            headers=auth_headers,
        )
        doc_id = upload.json()["id"]
        link = client.post(
            "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
        ).json()

        r = client.get(f"/api/v1/portal-links/token/{link['token']}/documents/{doc_id}/download")
        assert r.status_code == 404
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(Document).where(Document.customer_id == other["id"]))
            db.execute(delete(Customer).where(Customer.id == other["id"]))
            db.commit()
        finally:
            db.close()


def test_portal_revoked_link_cannot_access_documents(client, auth_headers, created_customer):
    upload = client.post(
        f"/api/v1/documents?customer_id={created_customer['id']}",
        files={"file": ("contract.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = upload.json()["id"]
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()
    client.delete(f"/api/v1/portal-links/{link['id']}", headers=auth_headers)

    r = client.get(f"/api/v1/portal-links/token/{link['token']}/documents/{doc_id}/download")
    assert r.status_code == 404
