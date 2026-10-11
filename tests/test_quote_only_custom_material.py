"""Stone-Hard DEF022: quote-only custom material must keep its name and price."""
import uuid
from unittest.mock import patch
import pytest
from pydantic import ValidationError
from app.quotes.models import QuoteRequest, QuoteItemRequest
from app.quotes.calculator import QuoteCalculator, CataloguePriceMissingError


def custom(**changes):
    return {"canonical_name": "Synthetic private quartz", "material_family": "quartz", "variant": {"thickness_mm": 20, "slab_length_mm": 3000, "slab_width_mm": 1400}, "buy_cost_per_slab": 400, "selling_price_per_slab": 600, "save_to_catalogue": False, **changes}


def item(**changes):
    return {"material": "Synthetic private quartz", "thickness": "20mm", "item_type": "worktop", "length_mm": 2400, "width_mm": 650, "custom_material": custom(), **changes}


def test_quote_only_custom_price_is_used_and_snapshotted_without_catalogue_lookup():
    request = QuoteRequest(customer="Synthetic customer", items=[item()])
    with patch("app.quotes.calculator.material_service.get_by_name_and_thickness", return_value=None) as legacy:
        result = QuoteCalculator().calculate(None, request, tenant_id=uuid.uuid4())
    legacy.assert_not_called()
    row = result["items"][0]
    assert row["material"] == "Synthetic private quartz"
    assert row["price_per_slab"] == row["line_total"] == 600
    assert row["catalogue_surface_id"] is None
    assert row["catalogue_snapshot"]["source"] == "quote_custom"
    assert row["catalogue_snapshot"]["slab_size"] == "3000x1400"
    assert result["total"] == 720


def test_custom_without_sale_price_never_falls_back_to_global_material_price():
    request = QuoteRequest(customer="Synthetic", items=[item(custom_material=custom(selling_price_per_slab=None))])
    with patch("app.quotes.calculator.material_service.get_by_name_and_thickness", return_value=None) as legacy:
        with pytest.raises(CataloguePriceMissingError):
            QuoteCalculator().calculate(None, request, tenant_id=uuid.uuid4())
    legacy.assert_not_called()


@pytest.mark.parametrize("changes", [{"catalogue_surface_id": str(uuid.uuid4())}, {"custom_material": custom(save_to_catalogue=True)}])
def test_inline_custom_cannot_ambiguously_select_or_write_a_catalogue_record(changes):
    with pytest.raises(ValidationError):
        QuoteItemRequest(**item(**changes))


def test_quote_only_custom_material_requires_a_workspace():
    request = QuoteRequest(customer="Synthetic", items=[item()])
    with pytest.raises(KeyError, match="authenticated workspace"):
        QuoteCalculator().calculate(None, request, tenant_id=None)


def test_quote_only_custom_material_is_persisted_only_inside_its_quote(client, auth_headers):
    from sqlalchemy import delete
    from app.database.database import SessionLocal
    from app.database.models import Quote, QuoteItem
    response = client.post("/api/v1/quote", headers=auth_headers, json={"customer": "Synthetic custom customer", "items": [item()]})
    assert response.status_code == 200, response.text
    quote_id = response.json()["id"]
    try:
        saved = client.get(f"/api/v1/quotes/{quote_id}", headers=auth_headers)
        assert saved.status_code == 200
        row = saved.json()["items"][0]
        assert row["material"] == "Synthetic private quartz"
        assert row["catalogue_surface_id"] is None
        with SessionLocal() as db:
            persisted = db.query(QuoteItem).filter(QuoteItem.quote_id == uuid.UUID(quote_id)).one()
            assert persisted.catalogue_snapshot["source"] == "quote_custom"
            assert persisted.catalogue_snapshot["selling_price_per_slab"] == 600
        assert row["price_per_slab"] == 600
        assert saved.json()["total"] == 720
    finally:
        with SessionLocal() as db:
            db.execute(delete(QuoteItem).where(QuoteItem.quote_id == uuid.UUID(quote_id)))
            db.execute(delete(Quote).where(Quote.id == uuid.UUID(quote_id)))
            db.commit()
