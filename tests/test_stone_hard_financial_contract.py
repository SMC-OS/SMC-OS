"""Net revenue and independently recorded actual costs, Stone-Hard DEF005/006."""
import pytest
from app.financials.service import build_contract_summary, build_cost_summary, build_profitability_summary


def test_vat_is_not_profit_when_contract_is_gross_and_costs_are_net():
    contract = build_contract_summary(4800, "approved_quote", 180, vat_amount=830)
    costs = build_cost_summary({"actual": 3300}, 1, "completed")
    result = build_profitability_summary(contract, costs)
    assert contract.current_contract_value == 4980
    assert contract.net_contract_value == 4150
    assert result.actual_gross_profit == 850
    assert result.actual_gross_margin_percent == pytest.approx(850 / 4150 * 100, abs=0.01)


def test_budget_entries_do_not_fabricate_zero_actual_cost_or_full_actual_profit():
    contract = build_contract_summary(1200, "approved_quote", 0)
    costs = build_cost_summary({"budgeted": 400}, 1, "lead")
    result = build_profitability_summary(contract, costs)
    assert result.forecast_gross_profit == 800
    assert result.actual_gross_profit is None
    assert result.actual_gross_margin_percent is None


def test_explicit_zero_actual_cost_is_distinct_from_missing_cost_data():
    contract = build_contract_summary(1200, "approved_quote", 0, vat_amount=200)
    costs = build_cost_summary({"actual": 0}, 1, "completed")
    assert build_profitability_summary(contract, costs).actual_gross_profit == 1000
