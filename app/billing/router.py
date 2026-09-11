"""Billing/subscriptions HTTP surface — Sprint 032, Workstream A.

Mutating routes (checkout/portal/cancel/resume) are Owner-only: a
subscription is a tenant-wide commercial decision, not something any
Staff member should be able to change (same reasoning as
app/invitations/router.py's Owner-only invite creation). The webhook route
is deliberately public — Stripe calls it directly and authenticates via
signature verification instead of a bearer token.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.models import UserRole
from app.billing.models import (
    CheckoutSessionOut,
    CheckoutSessionRequest,
    PlanEntitlementsOut,
    PlanOut,
    PortalSessionOut,
    SubscriptionOut,
)
from app.billing.plans import (
    BILLING_ANNUAL,
    BILLING_MONTHLY,
    ENTITLEMENTS,
    PLAN_BUSINESS,
    PLAN_ENTERPRISE,
    PLAN_PRO,
    PLAN_STARTER,
    PLAN_TEAM,
    PLANS,
    PRICING_GBP,
    SELF_SERVICE_PLANS,
)
from app.billing.service import BillingError, BillingUnavailable, WebhookSignatureError, billing_service
from app.database import crud
from app.database.database import get_db
from app.database.models import User

router = APIRouter(prefix="/billing", tags=["billing"])

_PLAN_DISPLAY_NAMES = {
    PLAN_STARTER: "GeoCore Starter",
    PLAN_TEAM: "GeoCore Team",
    PLAN_PRO: "GeoCore Pro",
    PLAN_BUSINESS: "GeoCore Business",
    PLAN_ENTERPRISE: "Enterprise",
}


@router.get("/plans", response_model=list[PlanOut])
def list_plans():
    """Public — powers the pricing page. No auth required."""
    plans = []
    for plan in PLANS:
        pricing = PRICING_GBP.get(plan, {})
        entitlements = ENTITLEMENTS[plan]
        plans.append(
            PlanOut(
                plan=plan,
                name=_PLAN_DISPLAY_NAMES[plan],
                self_service=plan in SELF_SERVICE_PLANS,
                monthly_price_gbp=pricing.get(BILLING_MONTHLY),
                annual_price_gbp=pricing.get(BILLING_ANNUAL),
                # Annual is always the recommended/best-value option for
                # every self-service plan (~2 months free vs. monthly).
                annual_recommended=plan in SELF_SERVICE_PLANS,
                entitlements=PlanEntitlementsOut(
                    seats=entitlements.seats,
                    ai_usage_per_month=entitlements.ai_usage_per_month,
                    automations=entitlements.automations,
                    integrations=entitlements.integrations,
                    advanced_analytics=entitlements.advanced_analytics,
                ),
            )
        )
    return plans


@router.get("/subscription", response_model=SubscriptionOut | None)
def get_subscription(
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    subscription = billing_service.get_subscription(db, current_user.tenant_id)
    return SubscriptionOut.model_validate(subscription) if subscription else None


@router.post("/checkout", response_model=CheckoutSessionOut)
def create_checkout_session(
    data: CheckoutSessionRequest,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    tenant = crud.get_tenant_by_id(db, current_user.tenant_id)
    try:
        url = billing_service.create_checkout_session(db, tenant, data.plan, data.billing_period)
    except BillingUnavailable:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured.")
    except BillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CheckoutSessionOut(checkout_url=url)


@router.post("/portal", response_model=PortalSessionOut)
def create_portal_session(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    tenant = crud.get_tenant_by_id(db, current_user.tenant_id)
    try:
        url = billing_service.create_portal_session(db, tenant)
    except BillingUnavailable:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured.")
    except BillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return PortalSessionOut(portal_url=url)


@router.post("/cancel", response_model=SubscriptionOut)
def cancel_at_period_end(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    tenant = crud.get_tenant_by_id(db, current_user.tenant_id)
    try:
        subscription = billing_service.set_cancel_at_period_end(db, tenant, cancel=True)
    except BillingUnavailable:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured.")
    except BillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return SubscriptionOut.model_validate(subscription)


@router.post("/resume", response_model=SubscriptionOut)
def resume_subscription(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    """Undoes a pending cancel-at-period-end before the period actually ends."""
    tenant = crud.get_tenant_by_id(db, current_user.tenant_id)
    try:
        subscription = billing_service.set_cancel_at_period_end(db, tenant, cancel=False)
    except BillingUnavailable:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured.")
    except BillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return SubscriptionOut.model_validate(subscription)


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Public — Stripe calls this directly and authenticates the request
    via its signature, not a bearer token. Never trust this payload
    without app.billing.service verifying that signature first."""
    payload = await request.body()
    signature_header = request.headers.get("stripe-signature")

    try:
        billing_service.handle_webhook(db, payload, signature_header)
    except BillingUnavailable:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured.")
    except WebhookSignatureError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature.")

    return {"received": True}
