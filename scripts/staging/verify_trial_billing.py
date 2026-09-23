"""Phase B — Stripe TEST-MODE verification of the no-card trial on staging.

Runs INSIDE the staging API container, which already has the staging
DATABASE_URL and Stripe TEST keys (nothing is copied out, no secret is
printed). The API image ships only app/, so pipe this file in:

    cat scripts/staging/verify_trial_billing.py | \\
      railway ssh --service simo-api-staging --environment staging -- python - setup --confirm-staging

Refuses to run unless STRIPE_SECRET_KEY is a TEST key (sk_test_...) and
--confirm-staging is given. Never contacts live Stripe.

Stages
------
setup    Creates three synthetic workspaces (names start "PhaseB Verify"):
         * TIMELINE — signs up on Starter monthly: asserts the trial started
           with no Stripe objects, day-1 access, then moves it to day 5,
           attaches a Stripe TEST CLOCK customer (so the charge can be
           fast-forwarded), and creates a real Checkout for Business annual.
           Prints the Checkout URL: open it and pay with card 4242 4242 4242
           4242, any future expiry, any CVC.
         * EXPIRY — never subscribes; its trial is moved past trial_end and
           access must be refused.
         * ELIGIBILITY — paid / cancelled / past-due / previously-trialled
           states must never start a second trial.
verify   (after paying) The Stripe subscription must: have collected a card;
         be `trialing` with trial_end equal to GeoCore's trial_end (remaining
         days preserved, no new 14-day trial); be the customer's ONLY
         subscription; and preview its first invoice at trial_end for the
         Business annual price. GeoCore's row must have been synced by the
         real webhook.
advance  Advances the test clock past trial_end: the first invoice must be
         paid then (not before), the subscription must be `active`, GeoCore
         must follow via webhook, and a new trial must still be refused.
cleanup  Deletes the test clocks (which removes their Stripe customers and
         subscriptions) and every synthetic workspace row.

Each stage prints PASS/FAIL per check and exits non-zero on any failure.
State between stages is kept in the workspaces themselves (found by name),
so no file needs to survive between `railway ssh` sessions.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.auth.dependencies import has_active_billing_access
from app.auth.models import SignupRequest
from app.auth.service import auth_service
from app.billing.plans import PRICING_GBP, price_id_for
from app.billing.service import billing_service
from app.billing.trial import start_trial_if_eligible
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailVerificationToken,
    Subscription,
    Tenant,
    User,
)

PREFIX = "PhaseB Verify"
PASSWORD = "PhaseB-Verify-Password-1!"
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {label}{f' — {detail}' if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


def stripe_module():
    key = settings.stripe_secret_key or ""
    if not key.startswith("sk_test_"):
        sys.exit("Refusing to run: STRIPE_SECRET_KEY is not a Stripe TEST key (sk_test_...).")
    return billing_service._get_stripe()


def workspace(db, role: str) -> Tenant | None:
    return db.scalars(select(Tenant).where(Tenant.name.like(f"{PREFIX} {role} %"))).first()


def signup(db, role: str, plan: str | None = None) -> Tenant:
    run = uuid.uuid4().hex[:8]
    tenant, user = auth_service.signup(
        db,
        SignupRequest(
            company_name=f"{PREFIX} {role} {run}",
            name="PhaseB Verify Owner",
            email=f"phaseb-verify-{role.lower()}-{run}@example.invalid",
            password=PASSWORD,
            plan=plan,
            billing_period="monthly",
        ),
    )
    crud.set_user_email_verified_at(db, user.id, datetime.now(timezone.utc))
    return tenant


def move_trial(db, tenant_id, *, days_elapsed: float) -> Subscription:
    row = crud.get_subscription_by_tenant_id(db, tenant_id)
    row.trial_start = datetime.now(timezone.utc) - timedelta(days=days_elapsed)
    row.trial_end = row.trial_start + timedelta(days=14)
    db.commit()
    db.refresh(row)
    return row


# --- Stages -------------------------------------------------------------------------------


def setup(db, stripe) -> None:
    # TIMELINE
    tenant = signup(db, "TIMELINE", plan="starter")
    sub = crud.get_subscription_by_tenant_id(db, tenant.id)
    check("signup starts a trial", sub is not None and sub.status == "trialing")
    check("no Stripe customer or subscription at signup", not sub.stripe_customer_id and not sub.stripe_subscription_id)
    check("trial is 14 days", sub.trial_end - sub.trial_start == timedelta(days=14))
    check("carried plan is Starter monthly", (sub.plan, sub.billing_period) == ("starter", "monthly"))
    sub = move_trial(db, tenant.id, days_elapsed=1)
    check("day-1 trial user can enter the app", has_active_billing_access(sub))

    sub = move_trial(db, tenant.id, days_elapsed=5)
    clock = stripe.test_helpers.TestClock.create(frozen_time=int(time.time()), name=f"{PREFIX} {tenant.id}")
    customer = stripe.Customer.create(test_clock=clock.id, name=tenant.name, metadata={"tenant_id": str(tenant.id)})
    sub.stripe_customer_id = customer.id  # Checkout reuses it, so the test clock governs billing
    db.commit()
    url = billing_service.create_checkout_session(db, tenant, "business", "annual")
    check("Checkout session created in TEST mode", url.startswith("https://checkout.stripe.com/"))
    print(f"\nTIMELINE workspace: {tenant.id}")
    print(f"GeoCore trial_end:  {sub.trial_end.isoformat()}")
    print(f"Open and pay with 4242 4242 4242 4242:\n{url}\n")

    # EXPIRY
    expiry = signup(db, "EXPIRY")
    expired = move_trial(db, expiry.id, days_elapsed=14)
    check("trial is refused exactly at trial_end", not has_active_billing_access(expired))
    check("expired workspace cannot restart a trial", start_trial_if_eligible(db, expiry.id).trial_end == expired.trial_end)

    # ELIGIBILITY
    for status_, grandfathered in (("active", False), ("cancelled", False), ("past_due", False), ("active", True)):
        t = signup(db, "ELIGIBILITY")
        crud.upsert_subscription(
            db, tenant_id=t.id, plan="business", billing_period="annual", status=status_,
            legacy_grandfathered=grandfathered,
            stripe_customer_id=None if grandfathered else f"cus_fake_{uuid.uuid4().hex[:8]}",
            stripe_subscription_id=None if grandfathered else f"sub_fake_{uuid.uuid4().hex[:8]}",
        )
        before = crud.get_subscription_by_tenant_id(db, t.id)
        snapshot = (before.status, before.plan, before.trial_end)
        after = start_trial_if_eligible(db, t.id, plan="starter")
        check(f"{'grandfathered' if grandfathered else status_} workspace gets no new trial",
              (after.status, after.plan, after.trial_end) == snapshot)


def _timeline(db):
    tenant = workspace(db, "TIMELINE")
    if tenant is None:
        sys.exit("Run `setup` first.")
    return tenant, crud.get_subscription_by_tenant_id(db, tenant.id)


def _preview_invoice(stripe, sub_id: str, customer_id: str):
    # Stripe renamed "upcoming invoice" to "create preview" in newer API
    # versions; try the current call first.
    try:
        return stripe.Invoice.create_preview(customer=customer_id, subscription=sub_id)
    except AttributeError:
        return stripe.Invoice.upcoming(customer=customer_id, subscription=sub_id)


def verify(db, stripe) -> None:
    tenant, row = _timeline(db)
    subs = stripe.Subscription.list(customer=row.stripe_customer_id, status="all")
    check("exactly one Stripe subscription for the customer", len(subs.data) == 1, f"found {len(subs.data)}")
    if not subs.data:
        return
    s = subs.data[0]
    customer = stripe.Customer.retrieve(row.stripe_customer_id)
    has_card = bool(s.get("default_payment_method") or (customer.get("invoice_settings") or {}).get("default_payment_method"))
    check("Checkout collected a payment method", has_card)
    check("Stripe subscription is trialing", s.status == "trialing", s.status)
    check("remaining trial preserved (Stripe trial_end == GeoCore trial_end)",
          abs(s.trial_end - int(row.trial_end.timestamp())) <= 1, f"{s.trial_end} vs {int(row.trial_end.timestamp())}")
    check("no fresh 14-day trial from Stripe",
          s.trial_end < int((datetime.now(timezone.utc) + timedelta(days=13)).timestamp()))
    check("subscribed to the Business annual price", s["items"]["data"][0]["price"]["id"] == price_id_for("business", "annual"))
    invoice = _preview_invoice(stripe, s.id, row.stripe_customer_id)
    first_charge = invoice.get("next_payment_attempt") or invoice.get("period_end") or invoice.get("created")
    check("first charge scheduled at trial_end", abs(first_charge - s.trial_end) <= 3600, f"{first_charge} vs {s.trial_end}")
    expected_pence = PRICING_GBP["business"]["annual"] * 100
    check("first charge amount is the Business annual price", invoice.amount_due == expected_pence, f"{invoice.amount_due}")
    db.refresh(row)
    check("webhook synced GeoCore (stripe ids, plan, status)",
          row.stripe_subscription_id == s.id and (row.plan, row.billing_period, row.status) == ("business", "annual", "trialing"))
    check("workspace still has access", has_active_billing_access(row))


def advance(db, stripe) -> None:
    tenant, row = _timeline(db)
    s = stripe.Subscription.list(customer=row.stripe_customer_id, status="all").data[0]
    clock_id = stripe.Customer.retrieve(row.stripe_customer_id).test_clock
    stripe.test_helpers.TestClock.advance(clock_id, frozen_time=s.trial_end + 3600)
    for _ in range(60):
        if stripe.test_helpers.TestClock.retrieve(clock_id).status == "ready":
            break
        time.sleep(5)
    s = stripe.Subscription.retrieve(s.id)
    check("subscription active after trial_end", s.status == "active", s.status)
    paid = [i for i in stripe.Invoice.list(subscription=s.id).data if i.amount_paid > 0]
    check("first real charge happened", len(paid) == 1, f"{len(paid)} paid invoices")
    if paid:
        check("charged at trial_end, not before", paid[0].created >= s.trial_start and paid[0].created >= row.trial_end.timestamp() - 3600)
    for _ in range(24):  # the webhook arrives asynchronously
        db.refresh(row)
        if row.status == "active":
            break
        time.sleep(5)
    check("GeoCore followed to active via webhook", row.status == "active", row.status)
    check("paid workspace gets no new trial", start_trial_if_eligible(db, tenant.id).status == "active")


def cleanup(db, stripe) -> None:
    tenants = db.scalars(select(Tenant).where(Tenant.name.like(f"{PREFIX} %"))).all()
    for tenant in tenants:
        row = crud.get_subscription_by_tenant_id(db, tenant.id)
        if row and row.stripe_customer_id and not row.stripe_customer_id.startswith("cus_fake_"):
            clock_id = stripe.Customer.retrieve(row.stripe_customer_id).get("test_clock")
            if clock_id:
                stripe.test_helpers.TestClock.delete(clock_id)
        user_ids = [u.id for u in db.scalars(select(User).where(User.tenant_id == tenant.id))]
        if user_ids:
            db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(user_ids)))
        for model in (Communication, Subscription, ActivityLog, User):
            db.execute(delete(model).where(model.tenant_id == tenant.id))
        db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()
    print(f"Removed {len(tenants)} synthetic workspaces and their Stripe test clocks.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("stage", choices=["setup", "verify", "advance", "cleanup"])
    parser.add_argument("--confirm-staging", action="store_true", help="required: this writes synthetic staging data")
    args = parser.parse_args(argv)
    if not args.confirm_staging:
        print("Refusing to run without --confirm-staging.")
        return 2
    stripe = stripe_module()
    with SessionLocal() as db:
        {"setup": setup, "verify": verify, "advance": advance, "cleanup": cleanup}[args.stage](db, stripe)
    print(f"\n{len(FAILURES)} check(s) failed." if FAILURES else "\nAll checks passed.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
