"""True multi-line-item quotes — Sprint 033, Workstream C.

Covers: a quote with multiple independent items persisting/round-tripping
correctly, independent dimensions per item, different item types, quantity
> 1, malformed items, legacy single-item compatibility, tenant isolation,
and totals/calculation behavior (sum over items).
"""

import pytest
from sqlalchemy import delete, select

from app.database.database import SessionLocal
from app.database.models import Quote, QuoteItem

TEST_POSTCODE = "PYTESTMULTI1"


def _cleanup(postcode: str = TEST_POSTCODE):
    db = SessionLocal()
    try:
        db.execute(
            delete(QuoteItem).where(
                QuoteItem.quote_id.in_(select(Quote.id).where(Quote.postcode == postcode))
            )
        )
        db.execute(delete(Quote).where(Quote.postcode == postcode))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    _cleanup("PYTESTMULTI2")
    yield
    _cleanup()
    _cleanup("PYTESTMULTI2")


def _multi_item_payload(postcode: str = TEST_POSTCODE):
    return {
        "customer": "Pytest Multi-Item Customer",
        "postcode": postcode,
        "items": [
            {
                "item_type": "worktop",
                "material": "Calacatta Oro",
                "thickness": "20mm",
                "quantity": 1,
                "length_mm": 2400,
                "width_mm": 600,
            },
            {
                "item_type": "island",
                "material": "Calacatta Oro",
                "thickness": "20mm",
                "quantity": 1,
                "length_mm": 2200,
                "width_mm": 1000,
            },
            {
                "item_type": "splashback",
                "material": "Calacatta Oro",
                "thickness": "20mm",
                "quantity": 2,
                "length_mm": 1200,
                "width_mm": 600,
            },
        ],
    }


def test_create_multi_item_quote_persists_every_item(client, auth_headers):
    r = client.post("/api/v1/quote", json=_multi_item_payload(), headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3

    quote_id = body["id"]
    fetched = client.get(f"/api/v1/quotes/{quote_id}", headers=auth_headers)
    assert fetched.status_code == 200
    items = fetched.json()["items"]
    assert len(items) == 3
    assert {i["item_type"] for i in items} == {"worktop", "island", "splashback"}
    assert next(i for i in items if i["item_type"] == "splashback")["quantity"] == 2


def test_each_item_keeps_its_own_independent_dimensions(client, auth_headers):
    r = client.post("/api/v1/quote", json=_multi_item_payload(), headers=auth_headers)
    items = {i["item_type"]: i for i in r.json()["items"]}

    assert items["worktop"]["length_mm"] == 2400
    assert items["worktop"]["width_mm"] == 600
    assert items["island"]["length_mm"] == 2200
    assert items["island"]["width_mm"] == 1000
    assert items["splashback"]["length_mm"] == 1200
    assert items["splashback"]["width_mm"] == 600
    # None of the three accidentally inherited another's dimensions.
    lengths = {items[t]["length_mm"] for t in items}
    assert len(lengths) == 3


def test_total_equals_sum_of_item_line_totals(client, auth_headers):
    r = client.post("/api/v1/quote", json=_multi_item_payload(), headers=auth_headers)
    body = r.json()
    expected_subtotal = round(sum(i["line_total"] for i in body["items"]), 2)
    assert body["price_before_vat"] == expected_subtotal
    assert body["vat"] == round(expected_subtotal * 0.20, 2)
    assert body["total"] == round(expected_subtotal + body["vat"], 2)


def test_editing_one_item_type_does_not_change_another_items_price(client, auth_headers):
    base = client.post("/api/v1/quote", json=_multi_item_payload(), headers=auth_headers).json()

    payload = _multi_item_payload("PYTESTMULTI2")
    payload["items"][1]["length_mm"] = 4000  # only the island grows
    changed = client.post("/api/v1/quote", json=payload, headers=auth_headers).json()

    base_by_type = {i["item_type"]: i for i in base["items"]}
    changed_by_type = {i["item_type"]: i for i in changed["items"]}

    assert base_by_type["worktop"]["line_total"] == changed_by_type["worktop"]["line_total"]
    assert base_by_type["splashback"]["line_total"] == changed_by_type["splashback"]["line_total"]
    assert changed_by_type["island"]["line_total"] >= base_by_type["island"]["line_total"]


def test_quantity_greater_than_one_scales_that_items_material_requirement(client, auth_headers):
    payload = _multi_item_payload()
    payload["items"] = [
        {
            "item_type": "upstand",
            "material": "Calacatta Oro",
            "thickness": "20mm",
            "quantity": 1,
            "length_mm": 1000,
            "width_mm": 900,
        }
    ]
    single = client.post("/api/v1/quote", json=payload, headers=auth_headers).json()

    payload2 = _multi_item_payload("PYTESTMULTI2")
    payload2["items"] = [
        {
            "item_type": "upstand",
            "material": "Calacatta Oro",
            "thickness": "20mm",
            "quantity": 20,
            "length_mm": 1000,
            "width_mm": 900,
        }
    ]
    many = client.post("/api/v1/quote", json=payload2, headers=auth_headers).json()

    assert many["items"][0]["slabs"] > single["items"][0]["slabs"]


def test_malformed_item_type_returns_422(client, auth_headers):
    payload = _multi_item_payload()
    payload["items"][0]["item_type"] = "not-a-real-type"
    r = client.post("/api/v1/quote", json=payload, headers=auth_headers)
    assert r.status_code == 422


def test_missing_required_item_field_returns_422(client, auth_headers):
    payload = _multi_item_payload()
    del payload["items"][0]["material"]
    r = client.post("/api/v1/quote", json=payload, headers=auth_headers)
    assert r.status_code == 422


def test_legacy_single_item_shape_still_produces_exactly_one_item(client):
    r = client.post(
        "/api/v1/quote",
        json={
            "customer": "Pytest Legacy Customer",
            "material": "Calacatta Oro",
            "thickness": "20mm",
            "kitchen_length": 3.0,
            "postcode": TEST_POSTCODE,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["item_type"] == "worktop"
    assert body["items"][0]["length_mm"] == 3000


def test_quote_items_are_tenant_isolated(client, auth_headers, other_tenant_auth_headers):
    created = client.post("/api/v1/quote", json=_multi_item_payload(), headers=auth_headers).json()
    quote_id = created["id"]

    # POST /quote is public/optional-auth (ADR-023), so this quote is
    # tagged with the caller's tenant — a different tenant's authenticated
    # browsing must not be able to reach it or its items at all.
    other = client.get(f"/api/v1/quotes/{quote_id}", headers=other_tenant_auth_headers)
    assert other.status_code == 404
