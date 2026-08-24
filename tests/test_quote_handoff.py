"""Sprint 020 — quote approval and approved-quote project handoff."""

from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Quote


TEST_PREFIX = "Pytest Sprint 020"
TEST_POSTCODE = "S020-TEST"


def _cleanup() -> None:
    db = SessionLocal()
    try:
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
