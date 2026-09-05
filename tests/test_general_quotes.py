"""Universal (general construction) quoting — Sprint 036, Workstream E.

The point of this file is the sprint's central product claim: GeoCore can
quote a bathroom refit, a roof and a set of worktops, and the stone
workflow that existed before is preserved exactly.

Covers: creating a general quote priced from line items, per-line rounding,
discounts and VAT, the draft-only edit rule, the send lifecycle, approval
and handoff working identically for both kinds, stone quotes still
behaving as they did, validation, and tenant isolation.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select

from app.database.database import SessionLocal
from app.database.models import Project, Quote, QuoteItem

RUN_ID = uuid.uuid4().hex[:8]
TEST_POSTCODE = f"PYT36{RUN_ID[:5]}".upper()


def _cleanup():
    db = SessionLocal()
    try:
        quote_ids = select(Quote.id).where(Quote.postcode == TEST_POSTCODE)
        db.execute(delete(Project).where(Project.quote_id.in_(quote_ids)))
        db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
        db.execute(delete(Quote).where(Quote.postcode == TEST_POSTCODE))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


def _payload(**overrides):
    payload = {
        "title": "Bathroom refit, 14 Elm Road",
        "trade": "bathroom",
        "site_address_line1": "14 Elm Road",
        "site_city": "Manchester",
        "site_postcode": TEST_POSTCODE,
        "scope_of_works": "Full strip-out and refit of family bathroom.",
        "exclusions": "Making good to decoration is excluded.",
        "terms": "50% on commencement, balance on completion.",
        "valid_until": (date.today() + timedelta(days=30)).isoformat(),
        "lines": [
            {
                "line_kind": "labour",
                "description": "Strip out existing bathroom",
                "quantity": 2.5,
                "unit": "day",
                "unit_price": 320,
            },
            {
                "line_kind": "material",
                "description": "Sanitaryware and brassware",
                "quantity": 1,
                "unit": "item",
                "unit_price": 1450.50,
            },
        ],
    }
    payload.update(overrides)
    return payload


def _create(client, auth_headers, **overrides):
    r = client.post("/api/v1/quotes", json=_payload(**overrides), headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


# --- Creation and pricing -------------------------------------------------


def test_creates_a_general_quote_with_no_stone_fields(client, auth_headers):
    quote = _create(client, auth_headers)

    assert quote["quote_kind"] == "general"
    assert quote["title"] == "Bathroom refit, 14 Elm Road"
    assert quote["trade"] == "bathroom"
    assert quote["site_city"] == "Manchester"
    assert quote["status"] == "draft"

    # The whole point: a construction quote carries no slab data at all,
    # rather than sentinel values pretending to be one.
    assert quote["material"] is None
    assert quote["thickness"] is None
    assert quote["length_mm"] is None
    assert quote["kitchen_length"] is None


def test_prices_lines_and_totals(client, auth_headers):
    quote = _create(client, auth_headers)

    # 2.5 x 320 = 800.00, 1 x 1450.50 = 1450.50
    assert [item["line_total"] for item in quote["items"]] == [800.0, 1450.5]
    assert quote["subtotal"] == 2250.5
    assert quote["price_before_vat"] == 2250.5
    assert quote["vat"] == 450.1
    assert quote["total"] == 2700.6
    assert quote["currency"] == "GBP"
    assert quote["vat_rate"] == 0.2


def test_line_items_keep_their_description_unit_and_rate(client, auth_headers):
    quote = _create(client, auth_headers)
    first = quote["items"][0]

    assert first["line_kind"] == "labour"
    assert first["description"] == "Strip out existing bathroom"
    assert first["unit"] == "day"
    assert first["unit_price"] == 320
    # A labour line is 2.5 days — the exact case the integer quantity
    # column could not express before this sprint.
    assert first["quantity"] == 2.5


def test_discount_is_applied_before_vat(client, auth_headers):
    quote = _create(client, auth_headers, discount_amount=250.5)

    assert quote["subtotal"] == 2250.5
    assert quote["discount_amount"] == 250.5
    assert quote["price_before_vat"] == 2000.0
    assert quote["vat"] == 400.0
    assert quote["total"] == 2400.0


def test_discount_larger_than_the_quote_produces_zero_not_a_negative(client, auth_headers):
    quote = _create(client, auth_headers, discount_amount=99999)

    assert quote["price_before_vat"] == 0.0
    assert quote["total"] == 0.0
    # Clamped, not rejected: "£99,999 off" a £2,250 job means "free".
    assert quote["discount_amount"] == 2250.5


def test_custom_vat_rate_is_honoured(client, auth_headers):
    quote = _create(client, auth_headers, vat_rate=0.05)

    assert quote["vat_rate"] == 0.05
    assert quote["vat"] == round(2250.5 * 0.05, 2)


def test_zero_priced_line_is_allowed(client, auth_headers):
    quote = _create(
        client,
        auth_headers,
        lines=[
            {"description": "Site survey — included", "quantity": 1, "unit": "item", "unit_price": 0}
        ],
    )
    assert quote["total"] == 0.0


# --- Validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"lines": []},
        {"title": ""},
        {"trade": "underwater_basket_weaving"},
        {"vat_rate": 20},
        {"discount_amount": -10},
        {"lines": [{"description": "x", "quantity": -1, "unit": "item", "unit_price": 5}]},
        {"lines": [{"description": "x", "quantity": 1, "unit": "furlong", "unit_price": 5}]},
        {"lines": [{"line_kind": "stone", "description": "x", "quantity": 1, "unit": "item"}]},
    ],
)
def test_rejects_invalid_payloads(client, auth_headers, override):
    r = client.post("/api/v1/quotes", json=_payload(**override), headers=auth_headers)
    assert r.status_code == 422, r.text


def test_rejects_a_customer_belonging_to_another_tenant(
    client, auth_headers, other_tenant_auth_headers
):
    other = client.post(
        "/api/v1/customers",
        json={"name": f"Pytest 036 Other {RUN_ID}"},
        headers=other_tenant_auth_headers,
    ).json()

    r = client.post(
        "/api/v1/quotes",
        json=_payload(customer_id=other["id"]),
        headers=auth_headers,
    )
    assert r.status_code == 404


# --- Editing --------------------------------------------------------------


def test_patch_replaces_lines_and_reprices(client, auth_headers):
    quote = _create(client, auth_headers)

    r = client.patch(
        f"/api/v1/quotes/{quote['id']}",
        json={
            "lines": [
                {"description": "Revised scope", "quantity": 3, "unit": "day", "unit_price": 300}
            ]
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()

    assert len(updated["items"]) == 1
    assert updated["subtotal"] == 900.0
    assert updated["total"] == 1080.0


def test_patch_without_lines_leaves_them_alone_but_still_reprices(client, auth_headers):
    quote = _create(client, auth_headers)

    r = client.patch(
        f"/api/v1/quotes/{quote['id']}",
        json={"discount_amount": 250.5},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()

    assert len(updated["items"]) == 2
    assert updated["subtotal"] == 2250.5
    assert updated["total"] == 2400.0


def test_patch_refuses_an_approved_quote(client, auth_headers):
    quote = _create(client, auth_headers)
    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    r = client.patch(
        f"/api/v1/quotes/{quote['id']}",
        json={"title": "Changed after approval"},
        headers=auth_headers,
    )
    assert r.status_code == 409


def test_patch_refuses_a_stone_quote(client, auth_headers):
    stone = client.post(
        "/api/v1/quote",
        json={
            "customer": "Pytest 036 Stone",
            "postcode": TEST_POSTCODE,
            "material": "Calacatta Oro",
            "thickness": "20mm",
            "length_mm": 2400,
        },
        headers=auth_headers,
    ).json()

    r = client.patch(
        f"/api/v1/quotes/{stone['id']}",
        json={"title": "Not a general quote"},
        headers=auth_headers,
    )
    assert r.status_code == 409


def test_patch_is_404_for_another_tenants_quote(
    client, auth_headers, other_tenant_auth_headers
):
    quote = _create(client, auth_headers)
    r = client.patch(
        f"/api/v1/quotes/{quote['id']}",
        json={"title": "Nope"},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404


# --- Lifecycle ------------------------------------------------------------


def test_send_marks_the_quote_sent_and_is_idempotent(client, auth_headers):
    quote = _create(client, auth_headers)

    first = client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["status"] == "sent"
    assert first.json()["sent_at"] is not None

    second = client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["sent_at"] == first.json()["sent_at"]


def test_a_sent_quote_can_still_be_approved(client, auth_headers):
    quote = _create(client, auth_headers)
    client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)

    r = client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_send_refuses_an_approved_quote(client, auth_headers):
    quote = _create(client, auth_headers)
    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    r = client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)
    assert r.status_code == 409


def test_handoff_carries_the_quotes_own_details_onto_the_project(client, auth_headers):
    customer = client.post(
        "/api/v1/customers",
        json={"name": f"Pytest 036 Customer {RUN_ID}"},
        headers=auth_headers,
    ).json()
    quote = _create(client, auth_headers, customer_id=customer["id"])
    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    r = client.post(f"/api/v1/quotes/{quote['id']}/handoff", headers=auth_headers)
    assert r.status_code == 200, r.text
    project = r.json()

    assert project["project_type"] == "bathroom"
    assert project["site_address_line1"] == "14 Elm Road"
    assert project["site_city"] == "Manchester"
    assert project["estimated_value"] == quote["total"]


# --- The stone workflow is preserved --------------------------------------


def test_stone_quotes_are_unchanged_and_marked_as_stone(client, auth_headers):
    r = client.post(
        "/api/v1/quote",
        json={
            "customer": "Pytest 036 Stone Preserved",
            "postcode": TEST_POSTCODE,
            "items": [
                {
                    "item_type": "worktop",
                    "material": "Calacatta Oro",
                    "thickness": "20mm",
                    "quantity": 1,
                    "length_mm": 2400,
                    "width_mm": 600,
                }
            ],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    created = r.json()

    detail = client.get(f"/api/v1/quotes/{created['id']}", headers=auth_headers).json()
    assert detail["quote_kind"] == "stone"
    assert detail["material"] == "Calacatta Oro"
    assert detail["length_mm"] == 2400
    assert detail["items"][0]["line_kind"] == "stone"
    assert detail["items"][0]["slabs"] is not None
    assert detail["total"] > 0


def test_general_and_stone_quotes_share_one_list(client, auth_headers):
    general = _create(client, auth_headers)
    client.post(
        "/api/v1/quote",
        json={
            "customer": "Pytest 036 Mixed",
            "postcode": TEST_POSTCODE,
            "material": "Calacatta Oro",
            "thickness": "20mm",
            "length_mm": 2400,
        },
        headers=auth_headers,
    )

    listed = client.get("/api/v1/quotes?limit=50", headers=auth_headers).json()
    kinds = {q["quote_kind"] for q in listed if q["postcode"] == TEST_POSTCODE}
    assert kinds == {"general", "stone"}
    assert general["id"] in {q["id"] for q in listed}


def test_invoice_pdf_renders_a_general_quote(client, auth_headers):
    quote = _create(client, auth_headers)
    r = client.get(f"/api/v1/quotes/{quote['id']}/invoice", headers=auth_headers)

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


# --- Vocabulary -----------------------------------------------------------


def test_trades_include_stone_as_one_option_among_many(client, auth_headers):
    trades = client.get("/api/v1/quotes/meta/trades", headers=auth_headers).json()
    keys = [t["key"] for t in trades]

    assert "stone" in keys
    assert {"general_building", "roofing", "bathroom", "electrical"} <= set(keys)
    # The product claim, asserted: stone is one trade among many and does
    # not lead the list.
    assert keys[0] != "stone"
    assert len(keys) >= 12


def test_units_are_a_curated_list(client, auth_headers):
    units = client.get("/api/v1/quotes/meta/units", headers=auth_headers).json()
    keys = {u["key"] for u in units}
    assert {"item", "day", "hour", "m2"} <= keys
