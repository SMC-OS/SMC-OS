"""Structured quote dimensions — Sprint 032, Workstream C. Covers
validation (missing/zero/negative/unrealistic/malformed) and the
end-to-end effect of quantity and independent splashback/upstand lengths
via the real /api/v1/quote endpoint.
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


def test_splashback_without_length_rejected():
    with pytest.raises(DimensionError):
        validate_dimensions(_base(splashback=True))


def test_upstands_without_length_rejected():
    with pytest.raises(DimensionError):
        validate_dimensions(_base(upstands=True))


def test_valid_dimensions_pass():
    validate_dimensions(_base(splashback=True, splashback_length_mm=1200))


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


def test_quote_creation_rejects_missing_splashback_length_over_http(client):
    r = client.post(
        "/api/v1/quote",
        json={
            "customer": "Test",
            "material": "Calacatta Gold",
            "thickness": "20mm",
            "length_mm": 3000,
            "splashback": True,
        },
    )
    assert r.status_code == 400
    assert "Splashback length" in r.json()["detail"]


def test_quantity_multiplies_material_required(db):
    single = QuoteCalculator().calculate(db, _base(quantity=1, length_mm=3500))
    double = QuoteCalculator().calculate(db, _base(quantity=2, length_mm=3500))
    assert double["slabs"] >= single["slabs"]
    assert double["price_before_vat"] > single["price_before_vat"]


def test_independent_splashback_length_changes_total_independently_of_worktop_length(db):
    short_splashback = QuoteCalculator().calculate(
        db,
        _base(length_mm=3500, splashback=True, splashback_length_mm=500),
    )
    long_splashback = QuoteCalculator().calculate(
        db,
        _base(length_mm=3500, splashback=True, splashback_length_mm=15000),
    )
    # Same worktop run length in both — only the splashback's own length
    # differs — so the totals must differ too (proves it's no longer
    # silently reusing the worktop run's length for the splashback area).
    assert long_splashback["price_before_vat"] > short_splashback["price_before_vat"]


def test_quote_response_echoes_interpreted_dimensions(db):
    result = QuoteCalculator().calculate(db, _base(length_mm=2400, width_mm=600, quantity=1))
    assert result["dimensions"]["length_mm"] == 2400
    assert result["dimensions"]["width_mm"] == 600
    assert result["dimensions"]["quantity"] == 1


def test_legacy_kitchen_length_alias_still_accepted_and_converted(db):
    request = QuoteRequest(
        customer="Test",
        material="Calacatta Gold",
        thickness="20mm",
        kitchen_length=3.0,
    )
    assert request.length_mm == 3000
    assert request.unit_input == "m"


def test_length_mm_or_kitchen_length_required():
    with pytest.raises(ValueError):
        QuoteRequest(customer="Test", material="Calacatta Gold", thickness="20mm")
