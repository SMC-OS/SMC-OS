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
    _cleanup()
    r = client.post("/api/v1/quote", json=_QUOTE_PAYLOAD)
    yield r.json()
    _cleanup()


def test_create_quote_persists_and_is_listed(client, auth_headers):
    _cleanup()
    try:
        r = client.post("/api/v1/quote", json=_QUOTE_PAYLOAD)
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        assert "created_at" in body

        listed = client.get("/api/v1/quotes", headers=auth_headers)
        ids = [q["id"] for q in listed.json()]
        assert body["id"] in ids
    finally:
        _cleanup()


def test_create_quote_logs_activity(client, auth_headers):
    _cleanup()
    try:
        client.post("/api/v1/quote", json=_QUOTE_PAYLOAD)
        r = client.get("/api/v1/activity?limit=50")
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
        r = client.post("/api/v1/quote", json=payload)
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
