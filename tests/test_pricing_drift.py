"""Phase B — pricing drift guard.

The public marketing site renders plan names, prices, seats and the
trial length from apps/marketing/lib/plans.json, so its pricing page is
server-rendered and never empty when the API is unreachable. The billing
code (app/billing/plans.py, surfaced by GET /billing/plans) stays the one
authority. This test fails the moment the two disagree, and also locks
the officially approved figures so neither side can drift alone.

To update after an approved pricing change, regenerate the file from the
API's own output:

    python -c "import json; from app.billing.router import list_plans; \
open('apps/marketing/lib/plans.json','w').write(json.dumps([p.model_dump() for p in list_plans()], indent=2) + '\\n')"
"""

import json
from pathlib import Path

from app.billing.router import list_plans

PLANS_JSON = Path(__file__).resolve().parents[1] / "apps" / "marketing" / "lib" / "plans.json"


def test_marketing_plans_file_matches_the_billing_api_exactly():
    marketing = json.loads(PLANS_JSON.read_text())
    api = [plan.model_dump() for plan in list_plans()]
    assert marketing == api


def test_official_pricing_is_locked():
    plans = {p["plan"]: p for p in json.loads(PLANS_JSON.read_text())}
    expected = {
        "starter": (29, 1),
        "team": (59, 3),
        "pro": (99, 10),
        "business": (199, 25),
    }
    for plan, (monthly, seats) in expected.items():
        assert plans[plan]["monthly_price_gbp"] == monthly
        assert plans[plan]["annual_price_gbp"] == monthly * 10
        assert plans[plan]["entitlements"]["seats"] == seats
        assert plans[plan]["self_service"] is True
        assert plans[plan]["trial_days"] == 14
    enterprise = plans["enterprise"]
    assert enterprise["self_service"] is False
    assert enterprise["monthly_price_gbp"] is None
    assert enterprise["trial_days"] is None
    assert list(plans) == ["starter", "team", "pro", "business", "enterprise"]
