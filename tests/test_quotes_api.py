import uuid

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Quote

TEST_POSTCODE = "PYTEST999"
TEST_CUSTOMER_NAME = "Pytest Quote Customer"

_QUOTE_PAYLOAD = {
    "customer": TEST_CUSTOMER_NAME,
    "material": "calacatta gold",
    "thickness": "20mm",
    "kitchen_length": 3.0,
    "postcode": TEST_POSTCODE,
}


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(Quote).where(Quote.postcode == TEST_POSTCODE))
        db.execute(
            delete(ActivityLog).where(
                ActivityLog.description.like(f"{TEST_CUSTOMER_NAME}%")
            )
        )
        db.execute(
            delete(ActivityLog).where(ActivityLog.description == TEST_CUSTOMER_NAME)
        )
        db.execute(delete(Customer).where(Customer.name == TEST_CUSTOMER_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def created_quote(client, auth_headers):
    # Sprint 012: POST /quote stays public (ADR-023/ADR-029), but now
    # opportunistically tags the quote with the caller's tenant when a
    # token is presented. Tests that read the quote back via an
    # authenticated route need it created under that same tenant.
    _cleanup()
    r = client.post("/api/v1/quote", json=_QUOTE_PAYLOAD, headers=auth_headers)
    yield r.json()
    _cleanup()


def test_create_quote_persists_and_is_listed(client, auth_headers):
    _cleanup()
    try:
        r = client.post("/api/v1/quote", json=_QUOTE_PAYLOAD, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        assert "created_at" in body

        listed = client.get("/api/v1/quotes", headers=auth_headers)
        ids = [q["id"] for q in listed.json()]
        assert body["id"] in ids
    finally:
        _cleanup()


def test_create_quote_without_token_is_not_visible_to_any_tenant(
    client, auth_headers, other_tenant_auth_headers
):
    """POST /quote stays callable with no token at all (ADR-023) — the
    quote is still created (still 200), but has no tenant, so it never
    appears in any tenant's authenticated /quotes list (ADR-029)."""
    _cleanup()
    try:
        r = client.post("/api/v1/quote", json=_QUOTE_PAYLOAD)
        assert r.status_code == 200
        quote_id = r.json()["id"]

        for headers in (auth_headers, other_tenant_auth_headers):
            listed = client.get("/api/v1/quotes", headers=headers)
            ids = [q["id"] for q in listed.json()]
            assert quote_id not in ids

            got = client.get(f"/api/v1/quotes/{quote_id}", headers=headers)
            assert got.status_code == 404
    finally:
        _cleanup()


def test_create_quote_logs_activity(client, auth_headers):
    _cleanup()
    try:
        client.post("/api/v1/quote", json=_QUOTE_PAYLOAD, headers=auth_headers)
        # Sprint 012: /activity now requires auth and is tenant-scoped.
        r = client.get("/api/v1/activity?limit=50", headers=auth_headers)
        descriptions = [e["description"] for e in r.json()]
        assert any(d.startswith(TEST_CUSTOMER_NAME) for d in descriptions)
    finally:
        _cleanup()


def test_create_quote_with_customer_id_round_trips(client, auth_headers):
    _cleanup()
    try:
        customer = client.post(
            "/api/v1/customers",
            json={"name": TEST_CUSTOMER_NAME},
            headers=auth_headers,
        ).json()

        payload = {**_QUOTE_PAYLOAD, "customer_id": customer["id"]}
        r = client.post("/api/v1/quote", json=payload, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["customer_id"] == customer["id"]
    finally:
        _cleanup()


def test_get_quote_by_id(client, auth_headers, created_quote):
    r = client.get(f"/api/v1/quotes/{created_quote['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["material"] == "calacatta gold"


def test_get_unknown_quote_returns_404(client, auth_headers):
    r = client.get(f"/api/v1/quotes/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


def test_download_invoice_returns_pdf(client, auth_headers, created_quote):
    r = client.get(
        f"/api/v1/quotes/{created_quote['id']}/invoice", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_invoice_unknown_quote_returns_404(client, auth_headers):
    r = client.get(f"/api/v1/quotes/{uuid.uuid4()}/invoice", headers=auth_headers)
    assert r.status_code == 404


def test_quotes_routes_require_auth(client, created_quote):
    assert client.get("/api/v1/quotes").status_code == 401
    assert client.get(f"/api/v1/quotes/{created_quote['id']}").status_code == 401
    assert (
        client.get(f"/api/v1/quotes/{created_quote['id']}/invoice").status_code == 401
    )


def test_old_quote_pdf_route_is_gone(client):
    assert client.post("/api/v1/quote/pdf", json=_QUOTE_PAYLOAD).status_code == 404


# --- Sprint 012 (ADR-029): cross-tenant isolation ---------------------------


def test_quote_not_visible_to_other_tenant(
    client, auth_headers, other_tenant_auth_headers, created_quote
):
    r = client.get("/api/v1/quotes", headers=other_tenant_auth_headers)
    assert r.status_code == 200
    ids = [q["id"] for q in r.json()]
    assert created_quote["id"] not in ids


def test_get_quote_cross_tenant_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_quote
):
    r = client.get(
        f"/api/v1/quotes/{created_quote['id']}", headers=other_tenant_auth_headers
    )
    assert r.status_code == 404


def test_invoice_cross_tenant_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_quote
):
    r = client.get(
        f"/api/v1/quotes/{created_quote['id']}/invoice",
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404


def test_create_quote_with_other_tenants_customer_id_returns_404(
    client, auth_headers, other_tenant_auth_headers
):
    """Relationship-bypass check (ADR-029): an authenticated caller linking
    a quote to a customer_id belonging to a different tenant must be
    rejected, not silently allowed — otherwise a quote record could
    reference another tenant's customer despite every id-based lookup
    being tenant-scoped."""
    _cleanup()
    try:
        their_customer = client.post(
            "/api/v1/customers",
            json={"name": TEST_CUSTOMER_NAME},
            headers=other_tenant_auth_headers,
        ).json()

        payload = {**_QUOTE_PAYLOAD, "customer_id": their_customer["id"]}
        r = client.post("/api/v1/quote", json=payload, headers=auth_headers)
        assert r.status_code == 404

        # No quote was persisted as a side effect either.
        mine = client.get("/api/v1/quotes", headers=auth_headers).json()
        assert not any(q["postcode"] == TEST_POSTCODE for q in mine)
    finally:
        _cleanup()
