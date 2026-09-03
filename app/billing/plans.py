"""Subscription plan/entitlement configuration — Sprint 032, Workstream A.

Stripe Price IDs are never hardcoded here or anywhere else: every plan x
billing-period combination reads its Price ID from an environment
variable via app/core/config.py (see docs/SPRINTS/sprint-032.md's Stripe
setup section for the exact names/dashboard steps). Entitlements are a
static config map, not DB-driven — v1 billing is fixed recurring plans
only, no usage-metering tables (explicit sprint scope decision, YAGNI).
The map's shape is deliberately generic (seats/ai_usage/automations/
integrations/advanced_analytics) so a future sprint can wire real usage
tracking against the same keys without changing this shape.
"""

from dataclasses import dataclass

from app.core.config import settings

PLAN_PRO = "pro"
PLAN_BUSINESS = "business"
PLAN_ENTERPRISE = "enterprise"

BILLING_MONTHLY = "monthly"
BILLING_ANNUAL = "annual"

PLANS = (PLAN_PRO, PLAN_BUSINESS, PLAN_ENTERPRISE)
BILLING_PERIODS = (BILLING_MONTHLY, BILLING_ANNUAL)

# Enterprise is contact-sales only — no self-service Stripe Checkout path.
SELF_SERVICE_PLANS = (PLAN_PRO, PLAN_BUSINESS)

# Display pricing (GBP). Annual is presented as the recommended/best-value
# option — roughly 2 months free vs. paying monthly for a year.
PRICING_GBP: dict[str, dict[str, int]] = {
    PLAN_PRO: {BILLING_MONTHLY: 79, BILLING_ANNUAL: 790},
    PLAN_BUSINESS: {BILLING_MONTHLY: 149, BILLING_ANNUAL: 1490},
}

ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


@dataclass(frozen=True)
class PlanEntitlements:
    seats: int | None  # None = unlimited
    ai_usage_per_month: int | None
    automations: int | None
    integrations: int | None
    advanced_analytics: bool


ENTITLEMENTS: dict[str, PlanEntitlements] = {
    PLAN_PRO: PlanEntitlements(
        seats=5, ai_usage_per_month=500, automations=10, integrations=3, advanced_analytics=False
    ),
    PLAN_BUSINESS: PlanEntitlements(
        seats=25, ai_usage_per_month=5000, automations=100, integrations=15, advanced_analytics=True
    ),
    PLAN_ENTERPRISE: PlanEntitlements(
        seats=None, ai_usage_per_month=None, automations=None, integrations=None,
        advanced_analytics=True,
    ),
}

_PRICE_ID_SETTINGS = {
    (PLAN_PRO, BILLING_MONTHLY): "stripe_price_pro_monthly",
    (PLAN_PRO, BILLING_ANNUAL): "stripe_price_pro_annual",
    (PLAN_BUSINESS, BILLING_MONTHLY): "stripe_price_business_monthly",
    (PLAN_BUSINESS, BILLING_ANNUAL): "stripe_price_business_annual",
}


def price_id_for(plan: str, billing_period: str) -> str | None:
    setting_name = _PRICE_ID_SETTINGS.get((plan, billing_period))
    if setting_name is None:
        return None
    return getattr(settings, setting_name)


def plan_and_period_for_price_id(price_id: str) -> tuple[str, str] | None:
    """Reverse lookup used when a Stripe webhook reports a price id —
    never trusts a plan name Stripe might send, only the configured
    mapping this deployment actually owns."""
    for (plan, period), setting_name in _PRICE_ID_SETTINGS.items():
        if getattr(settings, setting_name) == price_id:
            return plan, period
    return None


def entitlements_for(plan: str | None) -> PlanEntitlements | None:
    if plan is None:
        return None
    return ENTITLEMENTS.get(plan)
