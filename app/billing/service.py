"""BillingService — Stripe Checkout/Customer Portal/webhook integration
(Sprint 032, Workstream A).

Stripe is optional configuration, same "ships dark until configured"
pattern as app/quotes/ai_draft.py's OpenAI integration: every method that
actually needs Stripe raises BillingUnavailable if stripe_secret_key isn't
set, turned into a 503 by the router. Nothing at import/startup time
touches the Stripe API.

Webhook signature verification (stripe.Webhook.construct_event) is the
only thing standing between "a real event from Stripe" and "anyone POSTing
a fake payload" — every webhook request goes through it before any side
effect. Idempotency (app/database/crud.py's mark_stripe_event_processed)
guards against Stripe's documented at-least-once delivery retrying the
same event.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.billing.plans import plan_and_period_for_price_id, price_id_for
from app.core.config import settings
from app.database import crud
from app.database.models import Subscription, Tenant


class BillingUnavailable(Exception):
    """Raised when Stripe isn't configured. Turned into a 503 by the router."""


class BillingError(Exception):
    """Raised on a Stripe API failure or a request Stripe itself rejects."""


class WebhookSignatureError(Exception):
    """Raised when signature verification fails. Turned into a 400."""


class BillingService:
    def __init__(self, stripe_module=None) -> None:
        self._stripe = stripe_module

    def _get_stripe(self):
        if self._stripe is not None:
            return self._stripe
        if not settings.stripe_secret_key:
            raise BillingUnavailable("Billing is not configured.")

        import stripe  # imported lazily, mirrors ai_draft.py's OpenAI pattern

        stripe.api_key = settings.stripe_secret_key
        self._stripe = stripe
        return self._stripe

    def get_subscription(self, db: Session, tenant_id: uuid.UUID) -> Subscription | None:
        return crud.get_subscription_by_tenant_id(db, tenant_id)

    def create_checkout_session(
        self, db: Session, tenant: Tenant, plan: str, billing_period: str
    ) -> str:
        stripe = self._get_stripe()

        price_id = price_id_for(plan, billing_period)
        if price_id is None:
            raise BillingError(
                f"No Stripe Price ID configured for {plan}/{billing_period} — "
                "set the corresponding STRIPE_PRICE_* environment variable."
            )

        existing = crud.get_subscription_by_tenant_id(db, tenant.id)
        customer_id = existing.stripe_customer_id if existing else None

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                customer=customer_id,
                client_reference_id=str(tenant.id),
                metadata={
                    "tenant_id": str(tenant.id),
                    "plan": plan,
                    "billing_period": billing_period,
                },
                subscription_data={
                    "metadata": {
                        "tenant_id": str(tenant.id),
                        "plan": plan,
                        "billing_period": billing_period,
                    }
                },
                success_url=f"{settings.frontend_base_url}/settings?billing=success",
                cancel_url=f"{settings.frontend_base_url}/settings?billing=cancelled",
            )
        except Exception as exc:
            raise BillingError(str(exc)) from exc

        return session.url

    def create_portal_session(self, db: Session, tenant: Tenant) -> str:
        stripe = self._get_stripe()

        subscription = crud.get_subscription_by_tenant_id(db, tenant.id)
        if subscription is None or subscription.stripe_customer_id is None:
            raise BillingError("No Stripe customer on file yet — start a checkout first.")

        try:
            session = stripe.billing_portal.Session.create(
                customer=subscription.stripe_customer_id,
                return_url=f"{settings.frontend_base_url}/settings",
            )
        except Exception as exc:
            raise BillingError(str(exc)) from exc

        return session.url

    def set_cancel_at_period_end(self, db: Session, tenant: Tenant, cancel: bool) -> Subscription:
        stripe = self._get_stripe()

        subscription = crud.get_subscription_by_tenant_id(db, tenant.id)
        if subscription is None or subscription.stripe_subscription_id is None:
            raise BillingError("No active Stripe subscription to update.")

        try:
            stripe.Subscription.modify(
                subscription.stripe_subscription_id, cancel_at_period_end=cancel
            )
        except Exception as exc:
            raise BillingError(str(exc)) from exc

        return crud.upsert_subscription(
            db,
            tenant_id=tenant.id,
            plan=subscription.plan,
            billing_period=subscription.billing_period,
            status=subscription.status,
            stripe_customer_id=subscription.stripe_customer_id,
            stripe_subscription_id=subscription.stripe_subscription_id,
            stripe_price_id=subscription.stripe_price_id,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=cancel,
        )

    # --- Webhook handling ---------------------------------------------

    def handle_webhook(self, db: Session, payload: bytes, signature_header: str | None) -> None:
        stripe = self._get_stripe()

        if not settings.stripe_webhook_secret:
            raise BillingUnavailable("Stripe webhook secret is not configured.")

        try:
            event = stripe.Webhook.construct_event(
                payload, signature_header, settings.stripe_webhook_secret
            )
        except Exception as exc:
            raise WebhookSignatureError(str(exc)) from exc

        if not crud.mark_stripe_event_processed(db, event["id"], event["type"]):
            return  # already processed — idempotent no-op on a retried delivery

        handler = self._EVENT_HANDLERS.get(event["type"])
        if handler is not None:
            event_object = event["data"]["object"]
            to_dict = getattr(event_object, "to_dict", None)
            if callable(to_dict):
                event_object = to_dict()
            handler(self, db, event_object)

    def _handle_checkout_completed(self, db: Session, session_obj: dict) -> None:
        tenant_id_raw = (session_obj.get("metadata") or {}).get("tenant_id") or session_obj.get(
            "client_reference_id"
        )
        if not tenant_id_raw:
            return
        tenant_id = uuid.UUID(tenant_id_raw)

        metadata = session_obj.get("metadata") or {}
        plan = metadata.get("plan")
        billing_period = metadata.get("billing_period")
        if not plan or not billing_period:
            return

        crud.upsert_subscription(
            db,
            tenant_id=tenant_id,
            plan=plan,
            billing_period=billing_period,
            status="active",
            stripe_customer_id=session_obj.get("customer"),
            stripe_subscription_id=session_obj.get("subscription"),
            cancel_at_period_end=False,
        )

    def _handle_subscription_updated(self, db: Session, subscription_obj: dict) -> None:
        stripe_subscription_id = subscription_obj.get("id")
        existing = crud.get_subscription_by_stripe_subscription_id(db, stripe_subscription_id)
        if existing is None:
            return

        items = (subscription_obj.get("items") or {}).get("data") or []
        price_id = items[0]["price"]["id"] if items else existing.stripe_price_id
        resolved = plan_and_period_for_price_id(price_id) if price_id else None
        plan, billing_period = resolved if resolved else (existing.plan, existing.billing_period)

        period_end_ts = subscription_obj.get("current_period_end")
        current_period_end = (
            datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None
        )

        crud.upsert_subscription(
            db,
            tenant_id=existing.tenant_id,
            plan=plan,
            billing_period=billing_period,
            status=subscription_obj.get("status", existing.status),
            stripe_customer_id=subscription_obj.get("customer") or existing.stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_price_id=price_id,
            current_period_end=current_period_end,
            cancel_at_period_end=bool(subscription_obj.get("cancel_at_period_end")),
        )

    def _handle_subscription_deleted(self, db: Session, subscription_obj: dict) -> None:
        existing = crud.get_subscription_by_stripe_subscription_id(db, subscription_obj.get("id"))
        if existing is None:
            return

        crud.upsert_subscription(
            db,
            tenant_id=existing.tenant_id,
            plan=existing.plan,
            billing_period=existing.billing_period,
            status="cancelled",
            stripe_customer_id=existing.stripe_customer_id,
            stripe_subscription_id=existing.stripe_subscription_id,
            stripe_price_id=existing.stripe_price_id,
            current_period_end=existing.current_period_end,
            cancel_at_period_end=existing.cancel_at_period_end,
        )

    def _handle_invoice_payment_failed(self, db: Session, invoice_obj: dict) -> None:
        stripe_subscription_id = invoice_obj.get("subscription")
        if not stripe_subscription_id:
            return
        existing = crud.get_subscription_by_stripe_subscription_id(db, stripe_subscription_id)
        if existing is None:
            return

        crud.upsert_subscription(
            db,
            tenant_id=existing.tenant_id,
            plan=existing.plan,
            billing_period=existing.billing_period,
            status="past_due",
            stripe_customer_id=existing.stripe_customer_id,
            stripe_subscription_id=existing.stripe_subscription_id,
            stripe_price_id=existing.stripe_price_id,
            current_period_end=existing.current_period_end,
            cancel_at_period_end=existing.cancel_at_period_end,
        )

    def _handle_invoice_paid(self, db: Session, invoice_obj: dict) -> None:
        stripe_subscription_id = invoice_obj.get("subscription")
        if not stripe_subscription_id:
            return
        existing = crud.get_subscription_by_stripe_subscription_id(db, stripe_subscription_id)
        if existing is None or existing.status not in {"past_due", "unpaid", "incomplete"}:
            return

        crud.upsert_subscription(
            db,
            tenant_id=existing.tenant_id,
            plan=existing.plan,
            billing_period=existing.billing_period,
            status="active",
            stripe_customer_id=existing.stripe_customer_id,
            stripe_subscription_id=existing.stripe_subscription_id,
            stripe_price_id=existing.stripe_price_id,
            current_period_end=existing.current_period_end,
            cancel_at_period_end=existing.cancel_at_period_end,
        )

    _EVENT_HANDLERS = {
        "checkout.session.completed": _handle_checkout_completed,
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "invoice.payment_failed": _handle_invoice_payment_failed,
        "invoice.paid": _handle_invoice_paid,
    }


billing_service = BillingService()
