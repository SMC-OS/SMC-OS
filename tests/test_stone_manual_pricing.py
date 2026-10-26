from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.database.models import Tenant, Quote, QuoteItem
from app.quotes.models import QuoteRequest
from app.quotes.calculator import QuoteCalculator
from app.quotes.numbering import invoice_reference
from app.quotes.pdf import PDFGenerator, build_line_items
from app.tenants.models import TenantProfileUpdate


def request(**changes):
    return QuoteRequest(customer="Synthetic", site_address_line1="1 Test Street", postcode="NW2 7RP",
        pricing_mode="manual", items=[dict(material="Unlisted arbitrary stone", thickness="20mm", item_type="island", length_mm=2400, width_mm=650)], **changes)


def test_manual_job_price_never_looks_up_materials_or_adds_island_surcharges():
    db = Mock()
    result = QuoteCalculator().calculate(db, request(manual_price=3000, discount_percent=10, vat_rate=.2), uuid4())
    db.execute.assert_not_called()
    assert result["subtotal"] == 3000
    assert result["discount_amount"] == 300
    assert result["price_before_vat"] == 2700
    assert result["vat"] == 540
    assert result["total"] == 3240
    assert result["items"][0]["price_per_slab"] is None
    assert sum(x["line_total"] for x in result["items"]) == 3000


@pytest.mark.parametrize("changes,expected", [({"manual_price":1000,"vat_rate":0}, 1000), ({"manual_price":1000,"discount_percent":100},0), ({"manual_price":0,"vat_rate":0},0), ({"manual_price":.05,"discount_percent":10,"vat_rate":.2},.05)])
def test_manual_totals(changes, expected):
    assert QuoteCalculator().calculate(Mock(),request(**changes),uuid4())["total"] == expected


@pytest.mark.parametrize("changes", [{"manual_price":-1}, {"manual_price":float('nan')}, {"discount_percent":101}, {"vat_rate":2}])
def test_invalid_manual_money_rejected(changes):
    with pytest.raises(ValidationError): request(**changes)


def test_missing_manual_price_stays_pending_never_a_free_offer():
    result = QuoteCalculator().calculate(Mock(),request(),uuid4())
    assert result["pricing_pending"] and result["total"] is None


def test_foreign_catalogue_material_cannot_be_used_with_manual_price(monkeypatch):
    from app.quotes import calculator
    monkeypatch.setattr(calculator.crud,"get_catalogue_surface_by_id",lambda *a: None)
    quote=request(manual_price=100)
    quote.items[0].catalogue_surface_id=uuid4()
    with pytest.raises(KeyError): QuoteCalculator().calculate(Mock(),quote,uuid4())


@compiles(JSONB,"sqlite")
def jsonb_sqlite(type_, compiler, **kw): return "JSON"


def test_invoice_sequence_is_tenant_scoped_stable_customisable_and_skips_used_numbers():
    engine=create_engine("sqlite://")
    Tenant.__table__.create(engine)
    Quote.__table__.create(engine)
    QuoteItem.__table__.create(engine)
    with Session(engine) as db:
        a=Tenant(name="A",slug="a");b=Tenant(name="B",slug="b")
        db.add_all([a,b]); db.flush()
        q1=Quote(tenant_id=a.id);q2=Quote(tenant_id=a.id);q3=Quote(tenant_id=b.id)
        db.add_all([q1,q2,q3]);db.commit()
        assert invoice_reference(db,q1)=="Invoice-000001";db.commit()
        assert invoice_reference(db,q1)=="Invoice-000001";db.commit()
        assert invoice_reference(db,q2)=="Invoice-000002";db.commit()
        assert invoice_reference(db,q3)=="Invoice-000001";db.commit()
        a.invoice_next_number=1;db.commit()
        q4=Quote(tenant_id=a.id);db.add(q4);db.commit()
        assert invoice_reference(db,q4)=="Invoice-000003";db.commit()
        a.invoice_prefix="SMC-INV";a.invoice_next_number=164;db.commit()
        q5=Quote(tenant_id=a.id);db.add(q5);db.commit()
        assert invoice_reference(db,q5)=="SMC-INV-000164"
        assert q1.invoice_number=="Invoice-000001"


@pytest.mark.parametrize("value",['../invoice','bad"header', 'Bad\r\nHeader',''])
def test_invoice_prefix_rejects_paths_and_header_injection(value):
    with pytest.raises(ValidationError): TenantProfileUpdate(invoice_prefix=value)


def test_manual_job_price_persists_the_same_totals_and_pdf_job_row(monkeypatch):
    from app.quotes.service import QuoteService
    from app.quotes import service
    monkeypatch.setattr(service.activity_service, "log", Mock())
    monkeypatch.setattr(service.automation_dispatcher, "dispatch_quote_created", Mock())
    engine = create_engine("sqlite://")
    Tenant.__table__.create(engine)
    Quote.__table__.create(engine)
    QuoteItem.__table__.create(engine)
    with Session(engine) as db:
        tenant=Tenant(name="Synthetic",slug="manual-persist")
        db.add(tenant);db.commit()
        result=QuoteService().create(db,request(manual_price=3000, discount_percent=10, vat_rate=.2),tenant.id)
        stored=db.get(Quote,result["id"])
        assert (stored.subtotal, stored.discount_amount, stored.price_before_vat, stored.vat_rate, stored.vat, stored.total)==(3000,300,2700,.2,540,3240)
        rows=build_line_items(stored)
        assert len(rows)==1 and rows[0]["amount"]==3000
        assert "Unlisted arbitrary stone" in rows[0]["description"]


def test_wrapped_invoice_retains_long_specifications_and_stable_reference():
    from datetime import datetime
    from tests.test_tenant_identity import _pdf_text
    words = "Worktop with full bullnose polished edge; sink and hob cut-outs. " * 30
    pdf = PDFGenerator().create(dict(id=uuid4(),invoice_number="Invoice-000001",customer="Synthetic",created_at=datetime(2026,10,26),
        line_items=[dict(description=words,amount=1000)], price_before_vat=900,discount_amount=100,discount_percent=10,vat_rate=0,vat=0,total=900))
    text = _pdf_text(pdf)
    assert "Invoice-000001" in text
    assert "Worktop with full bullnose" in text
    assert "Discount" in text
    assert len(pdf)>10000  # embedded fonts, not a printer-dependent substitution
