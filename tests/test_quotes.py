from app.quotes.calculator import QuoteCalculator
from app.quotes.models import QuoteRequest


def _base_request(**overrides):
    defaults = dict(
        customer="Test Customer",
        material="calacatta gold",
        thickness="20mm",
        kitchen_length=3.5,
    )
    defaults.update(overrides)
    return QuoteRequest(**defaults)


def test_calculate_known_material_math(db):
    result = QuoteCalculator().calculate(db, _base_request())

    assert result["customer"] == "Test Customer"
    assert result["material"] == "calacatta gold"
    assert result["slabs"] >= 1
    assert result["price_per_slab"] == 2650

    expected_vat = round(result["price_before_vat"] * 0.20, 2)
    assert result["vat"] == expected_vat
    assert result["total"] == round(result["price_before_vat"] + expected_vat, 2)


def test_extras_increase_the_price(db):
    base = QuoteCalculator().calculate(db, _base_request())
    loaded = QuoteCalculator().calculate(
        db, _base_request(island=True, waterfall=1, splashback=True, upstands=True)
    )
    assert loaded["price_before_vat"] > base["price_before_vat"]


def test_thicker_material_costs_more(db):
    thin = QuoteCalculator().calculate(db, _base_request(thickness="20mm"))
    thick = QuoteCalculator().calculate(db, _base_request(thickness="30mm"))
    assert thick["price_per_slab"] > thin["price_per_slab"]


def test_larger_job_needs_more_slabs(db):
    small = QuoteCalculator().calculate(db, _base_request(kitchen_length=1.5))
    large = QuoteCalculator().calculate(
        db, _base_request(kitchen_length=6.0, island=True, waterfall=2)
    )
    assert large["slabs"] > small["slabs"]


def test_unrecognised_material_raises_key_error(db):
    import pytest

    with pytest.raises(KeyError):
        QuoteCalculator().calculate(db, _base_request(material="not-a-real-material"))


def test_unrecognised_material_returns_400_over_http(client):
    r = client.post(
        "/api/v1/quote",
        json={
            "customer": "Test",
            "material": "not-a-real-material",
            "thickness": "20mm",
            "kitchen_length": 3.0,
        },
    )
    assert r.status_code == 400
    assert "not-a-real-material" in r.json()["detail"]
