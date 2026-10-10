"""DEF017: currencies are independent units, never an implicit FX conversion."""
from decimal import Decimal
from app.money import totals_by_currency


def test_totals_never_add_different_currency_units():
    assert totals_by_currency([('GBP', 100), ('EUR', 200), ('GBP', 0.02), ('USD', None)]) == {
        'GBP': 100.02, 'EUR': 200.0, 'USD': 0.0,
    }


def test_currency_totals_preserve_pence_and_negative_variations():
    assert totals_by_currency([('GBP', Decimal('0.01')), ('GBP', Decimal('0.02')),
                               ('EUR', -10), ('EUR', 20)]) == {'GBP': 0.03, 'EUR': 10.0}


def test_empty_totals_remain_empty_without_fabricating_an_exchange_rate():
    assert totals_by_currency([]) == {}


def test_http_dashboard_ai_customer_and_contract_totals_keep_currencies_isolated(client):
    import uuid
    from sqlalchemy import delete, select
    from app.ai.context import build
    from app.database.database import SessionLocal
    from app.database.models import Tenant, Variation, VariationItem
    from tests.test_command_centre import _signup, _cleanup_tenant

    headers, tenant_id = _signup(client, 'mixed-currency')
    other_headers, other_tenant_id = _signup(client, 'other-currency')
    try:
        customer = client.post('/api/v1/customers', headers=headers, json={'name': 'Currency regression synthetic only'})
        assert customer.status_code == 201
        customer_id = customer.json()['id']
        for currency, amount in [('GBP', 100), ('EUR', 200), ('USD', 0.02)]:
            with SessionLocal() as db:
                db.get(Tenant, tenant_id).currency = currency
                db.commit()
            quote = client.post('/api/v1/quotes', headers=headers, json={
                'customer_id': customer_id, 'title': f'{currency} synthetic', 'vat_rate': 0,
                'lines': [{'line_kind': 'labour', 'description': 'Synthetic work', 'quantity': 1, 'unit': 'job', 'unit_price': amount}],
            })
            assert quote.status_code == 201
            assert quote.json()['currency'] == currency
            quote_id = quote.json()['id']
            assert client.post(f'/api/v1/quotes/{quote_id}/approve', headers=headers).status_code == 200
            project = client.post(f'/api/v1/quotes/{quote_id}/handoff', headers=headers)
            assert project.status_code == 200
            variation = client.post(f"/api/v1/projects/{project.json()['id']}/variations", headers=headers,
                json={'title': 'Synthetic addition', 'vat_rate': 0, 'items': [{'description': 'Addition', 'unit_price': 10}]})
            assert variation.status_code == 201
            assert client.post(f"/api/v1/variations/{variation.json()['id']}/approve", headers=headers).status_code == 200
        # Current workspace EUR must not re-denominate GBP/USD contracts.
        with SessionLocal() as db:
            db.get(Tenant, tenant_id).currency = 'EUR'
            db.commit()
        unrelated = client.post('/api/v1/quotes', headers=other_headers, json={
            'title': 'Other tenant', 'vat_rate': 0,
            'lines': [{'line_kind': 'labour', 'description': 'Other work', 'quantity': 1, 'unit': 'job', 'unit_price': 9999}],
        })
        assert unrelated.status_code == 201
        totals = {'GBP': 100.0, 'EUR': 200.0, 'USD': 0.02}
        dashboard = client.get('/api/v1/dashboard', headers=headers)
        assert dashboard.status_code == 200
        assert dashboard.json()['currency'] == 'EUR'
        assert dashboard.json()['quoted_value'] == 200
        assert dashboard.json()['quoted_value_by_currency'] == totals
        centre = client.get('/api/v1/dashboard/command-centre', headers=headers)
        assert centre.status_code == 200
        assert centre.json()['value']['quoted_value_by_currency'] == totals
        assert centre.json()['value']['approved_quoted_value_by_currency'] == totals
        assert centre.json()['financials']['approved_contract_value_by_currency'] == {'GBP': 110.0, 'EUR': 210.0, 'USD': 10.02}
        assert centre.json()['financials']['approved_variations_value_by_currency'] == {'GBP': 10.0, 'EUR': 10.0, 'USD': 10.0}
        assert centre.json()['financials']['approved_contract_value'] == 210
        customer_context = client.get(f'/api/v1/customers/{customer_id}/context', headers=headers)
        assert customer_context.status_code == 200
        assert customer_context.json()['quoted_value_by_currency'] == totals
        assert customer_context.json()['approved_value_by_currency'] == totals
        with SessionLocal() as db:
            context = build(db, tenant_id)
        assert context['quotes']['quoted_value_recent'] == 200
        assert context['quotes']['quoted_value_recent_by_currency'] == totals
    finally:
        for cleanup_id in [tenant_id, other_tenant_id]:
            with SessionLocal() as db:
                ids = select(Variation.id).where(Variation.tenant_id == cleanup_id)
                db.execute(delete(VariationItem).where(VariationItem.variation_id.in_(ids)))
                db.execute(delete(Variation).where(Variation.tenant_id == cleanup_id))
                db.commit()
            _cleanup_tenant(cleanup_id)
