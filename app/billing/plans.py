"""Subscription plan/entitlement configuration.

Sprint 032, Workstream A (original 2-tier version). Reworked in Sprint 039
Production Readiness Defect Gate, Blocker 3, to the product owner's locked
4-tier commercial structure (Starter/Team/Pro/Business, plus Enterprise)
replacing the old Pro/Business-only catalogue and its stale £79/£149
prices — see docs/SPRINTS/sprint-039.md §14.3 for the full locked pricing
table and the reasoning behind it. This module remains the single
authoritative plan catalogue: both the backend billing logic and the
frontend pricing page read from `GET /billing/plans`, which is built
entirely from this file — nothing hardcodes a price anywhere else.

Stripe Price IDs are never hardcoded here or anywhere else: every plan x
billing-period combination reads its Price ID from an environment
variable via app/core/config.py (see docs/SPRINTS/sprint-039.md §14.3's
Stripe setup section for the exact names/dashboard steps — this sprint
does not fabricate or create any real Stripe object). Entitlements are a
static config map, not DB-driven — v1 billing is fixed recurring plans
only, no usage-metering tables (explicit sprint scope decision, YAGNI).
"""

from dataclasses import dataclass

from app.core.config import settings

PLAN_STARTER = "starter"
PLAN_TEAM = "team"
PLAN_PRO = "pro"
PLAN_BUSINESS = "business"
PLAN_ENTERPRISE = "enterprise"

BILLING_MONTHLY = "monthly"
BILLING_ANNUAL = "annual"

PLANS = (PLAN_STARTER, PLAN_TEAM, PLAN_PRO, PLAN_BUSINESS, PLAN_ENTERPRISE)
BILLING_PERIODS = (BILLING_MONTHLY, BILLING_ANNUAL)

# Enterprise is contact-sales only — no self-service Stripe Checkout path.
SELF_SERVICE_PLANS = (PLAN_STARTER, PLAN_TEAM, PLAN_PRO, PLAN_BUSINESS)

# Sprint 039 Blocker 3 — the plan every new tenant's 14-day trial grants
# (see app/billing/trial.py). Pro is the most representative self-service
# tier to trial, matching the product owner's own framing of the trial as
# "try the real product," not the cheapest tier.
TRIAL_PLAN = PLAN_PRO
TRIAL_LENGTH_DAYS = 14

# Display pricing (GBP). Annual = 10x monthly (2 months free) for every
# self-service plan, exactly as locked — no plan invents a discount rate
# of its own. Locked, approved figures — do not substitute or "round"
# these, and do not restore the old £79/£149 2-tier pricing.
PRICING_GBP: dict[str, dict[str, int]] = {
    PLAN_STARTER: {BILLING_MONTHLY: 29, BILLING_ANNUAL: 290},
    PLAN_TEAM: {BILLING_MONTHLY: 59, BILLING_ANNUAL: 590},
    PLAN_PRO: {BILLING_MONTHLY: 99, BILLING_ANNUAL: 990},
    PLAN_BUSINESS: {BILLING_MONTHLY: 199, BILLING_ANNUAL: 1990},
}

ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


@dataclass(frozen=True)
class PlanEntitlements:
    seats: int | None  # None = unlimited
    ai_usage_per_month: int | None
    automations: int | None
    integrations: int | None
    advanced_analytics: bool


# Seat counts are the one entitlement this blocker's brief pins exactly
# (Starter 1 / Team 3 / Pro 10 / Business 25 / Enterprise custom); the
# other figures scale the same shape Sprint 032 already proved
# (seats/ai_usage/automations/integrations roughly co-scale) across four
# tiers instead of two, using only features that exist in the product
# today — no entitlement is invented that this codebase doesn't already
# enforce or at least display.
ENTITLEMENTS: dict[str, PlanEntitlements] = {
    PLAN_STARTER: PlanEntitlements(
        seats=1, ai_usage_per_month=100, automations=5, integrations=1, advanced_analytics=False
    ),
    PLAN_TEAM: PlanEntitlements(
        seats=3, ai_usage_per_month=500, automations=20, integrations=3, advanced_analytics=False
    ),
    PLAN_PRO: PlanEntitlements(
        seats=10, ai_usage_per_month=2000, automations=75, integrations=10, advanced_analytics=True
    ),
    PLAN_BUSINESS: PlanEntitlements(
        seats=25, ai_usage_per_month=5000, automations=150, integrations=15, advanced_analytics=True
    ),
    PLAN_ENTERPRISE: PlanEntitlements(
        seats=None, ai_usage_per_month=None, automations=None, integrations=None,
        advanced_analytics=True,
    ),
}

# Sprint 039 Blocker 3 — 8 settings, one per (plan, billing_period). The
# Starter/Team names are new; Pro/Business reuse Sprint 032's original
# setting names (STRIPE_PRICE_PRO_MONTHLY etc.) but must be repointed to
# NEW Stripe Price objects at the new £99/£199 amounts before this ships
# live — the old £79/£149 Price objects these variables used to point at
# are untouched in Stripe and keep serving any existing subscriber bound
# to them (a Stripe subscription references its Price by ID directly,
# independent of what this app's env vars point to today). See
# docs/SPRINTS/sprint-039.md §14.3 for the exact owner-gate spec.
_PRICE_ID_SETTINGS = {
    (PLAN_STARTER, BILLING_MONTHLY): "stripe_price_starter_monthly",
    (PLAN_STARTER, BILLING_ANNUAL): "stripe_price_starter_annual",
    (PLAN_TEAM, BILLING_MONTHLY): "stripe_price_team_monthly",
    (PLAN_TEAM, BILLING_ANNUAL): "stripe_price_team_annual",
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
