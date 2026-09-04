"""Structured quote dimensions — Sprint 032 (single item), extended in
Sprint 033 to validate every independent line item on a multi-item quote.
Covers validation (missing/zero/negative/unrealistic/malformed) and the
end-to-end effect of quantity and independent item lengths via the real
/api/v1/quote endpoint.
"""

import pytest

from app.quotes.calculator import QuoteCalculator
from app.quotes.models import QuoteRequest
from app.quotes.validator import DimensionError, validate_dimensions


def _base(**overrides):
    defaults = dict(
        customer="Test Customer",
        material="Calacatta Gold",
        thickness="20mm",
        length_mm=3500,
    )
    defaults.update(overrides)
    return QuoteRequest(**defaults)


def test_zero_length_rejected():
    with pytest.raises(DimensionError):
        validate_dimensions(_base(length_mm=0))


def test_negative_length_rejected():
    with pytest.raises(DimensionError):
        validate_dimensions(_base(length_mm=-100))


def test_zero_width_rejected():
    with pytest.raises(DimensionError):
        validate_dimensions(_base(width_mm=0))


def test_negative_quantity_rejected():
    with pytest.raises(DimensionError):
        validate_dimensions(_base(quantity=0))


def test_unrealistic_length_rejected():
    # A plausible unit-confusion bug: 3.5 metres mis-stored as 3.5mm*1000
    # in the wrong unit, or an AI parse gone wrong e.g. 35000mm.
    with pytest.raises(DimensionError):
        validate_dimensions(_base(length_mm=999_999))


def test_unsupported_unit_rejected():
    with pytest.raises(DimensionError):
        validate_dimensions(_base(unit_input="furlongs"))


def test_every_item_validated_independently():
    """A second item's bad dimension is caught even when the first item
    is perfectly valid — Sprint 033."""
    request = QuoteRequest(
        customer="Test",
        items=[
            dict(item_type="worktop", material="Calacatta Gold", thickness="20mm", length_mm=2400),
            dict(item_type="splashback", material="Calacatta Gold", thickness="20mm", length_mm=0),
        ],
    )
    with pytest.raises(DimensionError):
        validate_dimensions(request)


def test_at_least_one_item_required():
    with pytest.raises(DimensionError):
        request = QuoteRequest.model_construct(customer="Test", items=[])
        validate_dimensions(request)


def test_quote_creation_rejects_zero_length_over_http(client):
    r = client.post(
        "/api/v1/quote",
        json={
            "customer": "Test",
            "material": "Calacatta Gold",
            "thickness": "20mm",
            "length_mm": 0,
        },
    )
    assert r.status_code == 400


def test_quote_creation_rejects_zero_length_item_over_http(client):
    r = client.post(
        "/api/v1/quote",
        json={
            "customer": "Test",
            "items": [
                {"item_type": "worktop", "material": "Calacatta Gold", "thickness": "20mm", "length_mm": 2400},
                {"item_type": "splashback", "material": "Calacatta Gold", "thickness": "20mm", "length_mm": 0},
            ],
        },
    )
    assert r.status_code == 400
    assert "Length must be greater than zero" in r.json()["detail"]


def test_quantity_multiplies_material_required(db):
    single = QuoteCalculator().calculate(db, _base(quantity=1, length_mm=3500))
    double = QuoteCalculator().calculate(db, _base(quantity=2, length_mm=3500))
    assert double["slabs"] >= single["slabs"]
    assert double["price_before_vat"] > single["price_before_vat"]


def test_independent_item_lengths_never_share_dimensions(db):
    """Two items on the same quote — a worktop and a splashback — each
    keep their own length. Changing only the splashback's length changes
    the total without touching the worktop's own contribution, proving
    no item silently reuses another's dimensions (Sprint 033)."""

    def _quote(splashback_length_mm: float):
        return QuoteRequest(
            customer="Test",
            items=[
                dict(item_type="worktop", material="Calacatta Gold", thickness="20mm", length_mm=3500),
                # width_mm deliberately large here (not a realistic
                # splashback height) purely so this specific item's own
                # required area crosses a whole-slab boundary on its own
                # — the point being proven is independence, not realism.
                dict(
                    item_type="splashback",
                    material="Calacatta Gold",
                    thickness="20mm",
                    length_mm=splashback_length_mm,
                    width_mm=900,
                ),
            ],
        )

    short = QuoteCalculator().calculate(db, _quote(500))
    long = QuoteCalculator().calculate(db, _quote(19000))

    worktop_short = next(i for i in short["items"] if i["item_type"] == "worktop")
    worktop_long = next(i for i in long["items"] if i["item_type"] == "worktop")
    assert worktop_short["line_total"] == worktop_long["line_total"]
    assert long["price_before_vat"] > short["price_before_vat"]


def test_quote_response_echoes_interpreted_dimensions_per_item(db):
    result = QuoteCalculator().calculate(db, _base(length_mm=2400, width_mm=600, quantity=1))
    item = result["items"][0]
    assert item["length_mm"] == 2400
    assert item["width_mm"] == 600
    assert item["quantity"] == 1


def test_legacy_kitchen_length_alias_still_accepted_and_converted():
    request = QuoteRequest(
        customer="Test",
        material="Calacatta Gold",
        thickness="20mm",
        kitchen_length=3.0,
    )
    assert request.items[0].length_mm == 3000
    assert request.items[0].unit_input == "m"


def test_length_mm_or_kitchen_length_required():
    with pytest.raises(ValueError):
        QuoteRequest(customer="Test", material="Calacatta Gold", thickness="20mm")
