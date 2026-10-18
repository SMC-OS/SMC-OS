"""Grouped-piece pricing without a database; material lookup is the boundary fixture."""
from types import SimpleNamespace
import pytest
from app.quotes.calculator import QuoteCalculator
from app.quotes.models import QuoteRequest

@pytest.fixture
def calculator(monkeypatch):
    monkeypatch.setattr('app.quotes.calculator.material_service.get_by_name_and_thickness', lambda db, name, thickness: SimpleNamespace(price=1000.0, slab_size='3200x1600'))
    return QuoteCalculator()

def request(grouped=True, **overrides):
    items = [dict(item_type='worktop', material='Quartz', thickness='20mm', quantity=1, length_mm=2000, width_mm=600), dict(item_type='worktop', material='Quartz', thickness='20mm', quantity=1, length_mm=1800, width_mm=600)]
    if grouped:
        for item in items: item['slab_group'] = 'layout-1'
    items[1].update(overrides)
    return QuoteRequest(customer='Synthetic QA', items=items)

def test_two_pieces_share_one_area_estimate(calculator):
    result = calculator.calculate(None, request())
    assert result['slabs'] == 1
    assert result['price_before_vat'] == 1000
    assert sum(item['line_total'] for item in result['items']) == result['price_before_vat']
    assert result['items'][1]['catalogue_snapshot']['slab_allocation']['group'] == 'layout-1'

def test_ungrouped_legacy_quotes_are_unchanged(calculator):
    result = calculator.calculate(None, request(False))
    assert result['slabs'] == 2
    assert result['price_before_vat'] == 2000

def test_groups_do_not_mix_materials(calculator):
    with pytest.raises(ValueError, match='same material'):
        calculator.calculate(None, request(material='Different quartz'))

def test_groups_do_not_mix_thicknesses(calculator):
    with pytest.raises(ValueError, match='same material'):
        calculator.calculate(None, request(thickness='30mm'))

def test_shared_estimate_includes_quantity_and_type_surcharge(calculator):
    result = calculator.calculate(None, request(item_type='island', quantity=3, length_mm=3000, width_mm=1000))
    assert result['slabs'] == 3
    assert result['price_before_vat'] == 3000 + 3 * 450
    assert sum(i['line_total'] for i in result['items']) == result['price_before_vat']


def test_cent_allocations_reconcile_for_unequal_pieces(calculator, monkeypatch):
    monkeypatch.setattr('app.quotes.calculator.material_service.get_by_name_and_thickness', lambda db, name, thickness: SimpleNamespace(price=1000.01, slab_size='3200x1600'))
    result = calculator.calculate(None, request(length_mm=777))
    assert round(sum(row['line_total'] for row in result['items']), 2) == 1000.01
    assert result['total'] == 1200.01


def test_pdf_labels_the_shared_estimate(calculator):
    from app.quotes.pdf import build_line_items
    result = calculator.calculate(None, request())
    rows = [SimpleNamespace(**row, line_kind='stone') for row in result['items']]
    lines = build_line_items(SimpleNamespace(items=rows, currency='GBP'))
    assert all('shared material-area estimate (1 slabs across layout)' in line['description'] for line in lines)
