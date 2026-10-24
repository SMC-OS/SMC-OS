"""Typed material names may save specifications without manufacturing a price."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.quotes.models import QuoteRequest
from app.quotes.calculator import QuoteCalculator, CataloguePriceMissingError
from app.quotes.service import QuoteService, QuotePricingPendingError


def request(**changes):
    return QuoteRequest(**{
        "customer": "Synthetic", "postcode": "NW2 7RP", "site_address_line1": "1 Synthetic Street, London",
        "allow_unpriced": True,
        "items": [{"material": "An entirely new stone", "thickness": "20mm", "length_mm": 2400}],
        **changes,
    })


def test_unknown_name_saves_without_zero_or_partial_price():
    with patch("app.quotes.calculator.material_service.get_by_name_and_thickness", return_value=None):
        result = QuoteCalculator().calculate(None, request(), tenant_id=uuid.uuid4())
    assert result["items"][0]["material"] == "An entirely new stone"
    assert result["pricing_pending"] is True
    assert result["total"] is result["vat"] is result["price_before_vat"] is None
    assert result["items"][0]["slabs"] is result["items"][0]["line_total"] is None


def test_legacy_and_anonymous_requests_still_do_not_silently_allow_missing_prices():
    with patch("app.quotes.calculator.material_service.get_by_name_and_thickness", return_value=None):
        for quote, tenant in [(request(allow_unpriced=False), uuid.uuid4()), (request(), None)]:
            with pytest.raises(KeyError):
                QuoteCalculator().calculate(None, quote, tenant_id=tenant)


def test_mixed_quote_does_not_present_the_priced_lines_as_the_total():
    items = [
        {"material": "Unknown", "thickness": "20mm", "length_mm": 2400},
        {"material": "Priced", "thickness": "20mm", "length_mm": 2400},
    ]
    with patch("app.quotes.calculator.material_service.get_by_name_and_thickness", side_effect=[None, SimpleNamespace(price=500, slab_size="3200x1600")]):
        result = QuoteCalculator().calculate(None, request(items=items), tenant_id=uuid.uuid4())
    assert result["items"][1]["line_total"] == 500
    assert result["total"] is None


def test_catalogue_price_missing_can_save_but_a_foreign_surface_cannot():
    items = [{"material": "Reference stone", "thickness": "20mm", "length_mm": 2400, "catalogue_surface_id": uuid.uuid4()}]
    with patch.object(QuoteCalculator, "_resolve_catalogue_item", side_effect=CataloguePriceMissingError("Reference stone")):
        assert QuoteCalculator().calculate(None, request(items=items), tenant_id=uuid.uuid4())["total"] is None
    with patch.object(QuoteCalculator, "_resolve_catalogue_item", side_effect=KeyError("catalogue surface")):
        with pytest.raises(KeyError):
            QuoteCalculator().calculate(None, request(items=items), tenant_id=uuid.uuid4())


@pytest.mark.parametrize("missing", ["postcode", "site_address_line1"])
def test_stone_editor_requires_address_and_postcode(missing):
    with pytest.raises(ValidationError):
        request(**{missing: " "})


@pytest.mark.parametrize("operation", ["approve", "mark_sent", "send_and_mark_sent"])
def test_unpriced_drafts_cannot_become_customer_offers(operation):
    quote = SimpleNamespace(total=None, status="draft")
    kwargs = {"actor_user_id": uuid.uuid4()} if operation == "approve" else {"sender_user_id": uuid.uuid4()} if operation == "send_and_mark_sent" else {}
    with patch("app.quotes.service.crud.get_quote_by_id", return_value=quote):
        with pytest.raises(QuotePricingPendingError):
            getattr(QuoteService(), operation)(None, uuid.uuid4(), uuid.uuid4(), **kwargs)


def test_missing_or_foreign_draft_cannot_be_replaced():
    from app.quotes.service import QuoteNotFoundError
    with patch("app.quotes.service.crud.get_quote_by_id", return_value=None):
        with pytest.raises(QuoteNotFoundError):
            QuoteService().create(None, request(draft_id=uuid.uuid4()), tenant_id=uuid.uuid4())


@pytest.mark.parametrize("kind,status,total", [("general", "draft", None), ("stone", "sent", None), ("stone", "draft", 500)])
def test_priced_or_non_draft_records_cannot_be_overwritten(kind, status, total):
    from app.quotes.service import QuoteEditStateError
    with patch("app.quotes.service.crud.get_quote_by_id", return_value=SimpleNamespace(quote_kind=kind, status=status, total=total)):
        with pytest.raises(QuoteEditStateError):
            QuoteService().create(None, request(draft_id=uuid.uuid4()), tenant_id=uuid.uuid4())


def test_unpriced_draft_can_be_priced_in_place(client, auth_headers):
    payload = request().model_dump(mode="json")
    created = client.post("/api/v1/quote", json=payload, headers=auth_headers)
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["total"] is None
    payload["draft_id"] = data["id"]
    payload["items"][0]["custom_material"] = {
        "canonical_name": "An entirely new stone", "material_family": "quartz", "selling_price_per_slab": 600,
        "variant": {"slab_length_mm": 3200, "slab_width_mm": 1600, "thickness_mm": 20},
    }
    priced = client.post("/api/v1/quote", json=payload, headers=auth_headers)
    assert priced.status_code == 200, priced.text
    assert priced.json()["id"] == data["id"]
    assert priced.json()["total"] == 720
    saved = client.get(f'/api/v1/quotes/{data["id"]}', headers=auth_headers)
    assert saved.status_code == 200
    assert len(saved.json()["items"]) == 1
    assert saved.json()["site_address_line1"] == "1 Synthetic Street, London"
    assert saved.json()["site_postcode"] == "NW2 7RP"
