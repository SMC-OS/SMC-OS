"""Customers V2 — Sprint 036, Workstream D.

A GeoCore customer was three columns: name, email, phone. That is a
contact, not a customer record for a construction business. This file
covers the expanded record, the partial-update semantics, the context
endpoint that gives the detail page real business context, and — most
importantly — that none of it broke the three-field body every existing
caller still sends.
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.database.database import SessionLocal
from app.database.models import Customer, Project, Quote, QuoteItem

RUN_ID = uuid.uuid4().hex[:8]
TEST_PREFIX = f"Pytest Customers V2 {RUN_ID}"
TEST_POSTCODE = f"PYC36{RUN_ID[:5]}".upper()


def _cleanup():
    db = SessionLocal()
    try:
        customer_ids = select(Customer.id).where(Customer.name.like(f"{TEST_PREFIX}%"))
        quote_ids = select(Quote.id).where(Quote.customer_id.in_(customer_ids))
        db.execute(delete(Project).where(Project.customer_id.in_(customer_ids)))
        db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
        db.execute(delete(Quote).where(Quote.customer_id.in_(customer_ids)))
        db.execute(delete(Customer).where(Customer.name.like(f"{TEST_PREFIX}%")))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


def _create(client, auth_headers, **overrides):
    payload = {"name": f"{TEST_PREFIX} Ada Okafor"}
    payload.update(overrides)
    r = client.post("/api/v1/customers", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_the_original_three_field_body_still_works(client, auth_headers):
    customer = _create(
        client, auth_headers, email="ada@example.invalid", phone="07123 456789"
    )

    assert customer["email"] == "ada@example.invalid"
    assert customer["phone"] == "07123 456789"
    # Defaults, not nulls: an existing caller's customer is an individual,
    # which is what every customer created before this sprint was.
    assert customer["customer_type"] == "individual"
    assert customer["company_name"] is None


def test_creates_a_full_construction_customer_record(client, auth_headers):
    customer = _create(
        client,
        auth_headers,
        customer_type="company",
        company_name="Okafor Developments Ltd",
        address_line1="Unit 7, Riverside Works",
        address_line2="Bridge Lane",
        city="Leeds",
        postcode="LS1 4AB",
        notes="Main contractor. Prefers email. Pays on 30-day terms.",
    )

    assert customer["customer_type"] == "company"
    assert customer["company_name"] == "Okafor Developments Ltd"
    assert customer["city"] == "Leeds"
    assert customer["postcode"] == "LS1 4AB"
    assert customer["notes"].startswith("Main contractor")


def test_rejects_an_unknown_customer_type(client, auth_headers):
    r = client.post(
        "/api/v1/customers",
        json={"name": f"{TEST_PREFIX} bad", "customer_type": "sole_trader"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_patch_leaves_omitted_fields_alone_and_clears_explicit_nulls(client, auth_headers):
    customer = _create(client, auth_headers, city="Leeds", postcode="LS1 4AB")

    r = client.patch(
        f"/api/v1/customers/{customer['id']}",
        json={"city": "Manchester", "postcode": None},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()

    assert updated["city"] == "Manchester"
    # Explicit null clears; the untouched name is untouched.
    assert updated["postcode"] is None
    assert updated["name"] == customer["name"]


def test_patch_is_404_for_another_tenants_customer(
    client, auth_headers, other_tenant_auth_headers
):
    customer = _create(client, auth_headers)
    r = client.patch(
        f"/api/v1/customers/{customer['id']}",
        json={"city": "Nope"},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404


def test_context_returns_quotes_projects_and_value(client, auth_headers):
    customer = _create(client, auth_headers)

    quote = client.post(
        "/api/v1/quotes",
        json={
            "title": f"{TEST_PREFIX} loft conversion",
            "trade": "extension",
            "customer_id": customer["id"],
            "site_postcode": TEST_POSTCODE,
            "lines": [
                {"description": "Loft conversion", "quantity": 1, "unit": "job", "unit_price": 24000}
            ],
        },
        headers=auth_headers,
    ).json()
    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)
    client.post(f"/api/v1/quotes/{quote['id']}/handoff", headers=auth_headers)

    r = client.get(f"/api/v1/customers/{customer['id']}/context", headers=auth_headers)
    assert r.status_code == 200, r.text
    context = r.json()

    assert context["customer"]["id"] == customer["id"]
    assert len(context["quotes"]) == 1
    assert context["quotes"][0]["title"] == f"{TEST_PREFIX} loft conversion"
    assert len(context["projects"]) == 1
    assert context["quoted_value"] == quote["total"]
    assert context["approved_value"] == quote["total"]
    assert context["open_projects"] == 1


def test_context_is_empty_but_valid_for_a_brand_new_customer(client, auth_headers):
    customer = _create(client, auth_headers)
    context = client.get(
        f"/api/v1/customers/{customer['id']}/context", headers=auth_headers
    ).json()

    assert context["quotes"] == []
    assert context["projects"] == []
    assert context["quoted_value"] == 0
    assert context["open_projects"] == 0


def test_context_is_404_across_tenants(client, auth_headers, other_tenant_auth_headers):
    customer = _create(client, auth_headers)
    r = client.get(
        f"/api/v1/customers/{customer['id']}/context", headers=other_tenant_auth_headers
    )
    assert r.status_code == 404
