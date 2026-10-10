"""Stone-Hard DEF004/019: contractual content must survive PDF rendering."""
import base64
import re
import zlib
from datetime import date, datetime
from types import SimpleNamespace
from app.quotes.pdf import PDFGenerator, build_line_items


def pdf_text(pdf):
    streams = []
    for match in re.finditer(rb"stream(.*?)endstream", pdf, re.S):
        raw = match.group(1).strip()
        try:
            raw = base64.a85decode(raw, adobe=True)
        except ValueError:
            raw = base64.a85decode(raw.removesuffix(b"~>"))
        streams.append(zlib.decompress(raw).decode("latin-1"))
    return "\n".join(streams)


def test_contractual_sections_and_site_are_present_in_rendered_pdf():
    pdf = PDFGenerator().create({
        "id": "synthetic", "customer": "Synthetic customer", "title": "Renovation",
        "created_at": datetime(2026, 10, 10), "currency": "GBP",
        "line_items": [{"description": "Labour", "amount": 100}],
        "price_before_vat": 100, "vat": 20, "total": 120,
        "site_address": "14 Synthetic Road, Manchester, QA1 2AB",
        "valid_until": date(2026, 11, 9),
        "scope_of_works": "Synthetic scope & fitting\nSecond scope line",
        "exclusions": "Synthetic decorating excluded",
        "terms": "Synthetic fifty percent deposit",
        "notes": "INTERNAL secret margin note",
    })
    text = pdf_text(pdf)
    for expected in ["14 Synthetic Road", "09 November 2026", "Synthetic scope", "Second scope line", "Synthetic decorating excluded", "Synthetic fifty percent deposit"]:
        assert expected in text
    assert "INTERNAL secret margin note" not in text


def test_stone_line_keeps_layout_and_included_extras():
    item = SimpleNamespace(line_kind="stone", item_type="worktop", material="Quartz", thickness="20mm", quantity=1, length_mm=2400, width_mm=650, line_total=600,
                           notes="Layout: Peninsula. Extras: Sink / hob cutout, Polished edge")
    rows = build_line_items(SimpleNamespace(items=[item], currency="GBP"))
    assert "Layout: Peninsula" in rows[0]["description"]
    assert "Sink / hob cutout" in rows[0]["description"]
    assert rows[0]["amount"] == 600


def test_authenticated_pdf_contains_persisted_contract_fields(client, auth_headers):
    from sqlalchemy import delete
    from app.database.database import SessionLocal
    from app.database.models import Quote, QuoteItem
    response = client.post("/api/v1/quotes", headers=auth_headers, json={
        "title": "Synthetic document contract", "site_address_line1": "77 Synthetic Lane",
        "site_city": "Manchester", "scope_of_works": "Agreed synthetic fitting scope",
        "exclusions": "Synthetic decoration excluded", "terms": "Synthetic deposit terms",
        "valid_until": "2027-01-15", "notes": "INTERNAL hidden note",
        "lines": [{"line_kind": "labour", "description": "Fitting", "quantity": 1, "unit": "item", "unit_price": 100}],
    })
    assert response.status_code == 201, response.text
    quote_id = response.json()["id"]
    try:
        result = client.get(f"/api/v1/quotes/{quote_id}/invoice", headers=auth_headers)
        assert result.status_code == 200
        text = pdf_text(result.content)
        for expected in ["77 Synthetic Lane", "Agreed synthetic fitting scope", "Synthetic decoration excluded", "Synthetic deposit terms", "15 January 2027"]:
            assert expected in text
        assert "INTERNAL hidden note" not in text
    finally:
        import uuid
        with SessionLocal() as db:
            db.execute(delete(QuoteItem).where(QuoteItem.quote_id == uuid.UUID(quote_id)))
            db.execute(delete(Quote).where(Quote.id == uuid.UUID(quote_id)))
            db.commit()
