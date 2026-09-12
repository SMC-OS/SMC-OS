"""Server-side entitlement enforcement — Sprint 032, Workstream A.

The one rule that matters: a plan limit is enforced here, in a FastAPI
dependency the router attaches, never left to the frontend to police on
its own. A tenant with no subscription yet (pre-billing signup, or an
existing tenant from before this sprint) is treated as unmetered/legacy —
enforcement begins once a tenant actually has an active/trialing
Subscription row, so shipping billing never silently locks out an
existing production tenant that hasn't chosen a plan yet.

Sprint 039 Production Readiness Defect Gate, Blocker 3 — every new
signup now starts a real trialing Subscription (app/billing/trial.py),
so this module also has to answer "what happens once that trial's
trial_end passes with no conversion to a paid plan." An expired trial is
deliberately NOT treated as "no subscription" (which would fail open to
unmetered/unlimited — the opposite of the brief's "must not accidentally
receive permanent paid access"): once expired, seat enforcement treats
the tenant as already at its limit, blocking any *new* seat rather than
removing or disabling anyone already there (the same "handle safely,
never delete/disable" principle the brief applies to a tenant that
exceeds a newly-assigned tier).
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.billing.plans import ACTIVE_SUBSCRIPTION_STATUSES, entitlements_for
from app.billing.service import billing_service
from app.database import crud
from app.database.database import get_db
from app.database.models import Subscription, User


def is_trial_expired(subscription: Subscription) -> bool:
    return (
        subscription.status == "trialing"
        and subscription.trial_end is not None
        and subscription.trial_end < datetime.now(timezone.utc)
    )


def require_seat_available(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Attach to any route that adds a seat to a tenant (today: creating
    a staff invitation) to enforce the plan's seat limit server-side."""
    subscription = billing_service.get_subscription(db, current_user.tenant_id)
    if subscription is None or subscription.status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return  # no active plan yet — unmetered/legacy, see module docstring

    if is_trial_expired(subscription):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your 14-day trial has ended. Upgrade to add more team members.",
        )

    entitlements = entitlements_for(subscription.plan)
    if entitlements is None or entitlements.seats is None:
        return  # unknown plan (fail open) or unlimited seats (Enterprise)

    # Counts real users plus already-pending invitations — an invitation
    # is a seat commitment even before it's accepted, so a burst of
    # invitations can't blow past the limit between creation and accept.
    seat_count = len(crud.list_users_by_tenant(db, current_user.tenant_id)) + len(
        crud.list_invitations(db, current_user.tenant_id, status="pending")
    )
    if seat_count >= entitlements.seats:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Seat limit ({entitlements.seats}) reached for the {subscription.plan} plan. "
                "Upgrade to add more team members."
            ),
        )
