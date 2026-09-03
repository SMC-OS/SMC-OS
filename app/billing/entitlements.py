"""Server-side entitlement enforcement — Sprint 032, Workstream A.

The one rule that matters: a plan limit is enforced here, in a FastAPI
dependency the router attaches, never left to the frontend to police on
its own. A tenant with no subscription yet (pre-billing signup, or an
existing tenant from before this sprint) is treated as unmetered/legacy —
enforcement begins once a tenant actually has an active/trialing
Subscription row, so shipping billing never silently locks out an
existing production tenant that hasn't chosen a plan yet.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.billing.plans import ACTIVE_SUBSCRIPTION_STATUSES, entitlements_for
from app.billing.service import billing_service
from app.database import crud
from app.database.database import get_db
from app.database.models import User


def require_seat_available(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Attach to any route that adds a seat to a tenant (today: creating
    a staff invitation) to enforce the plan's seat limit server-side."""
    subscription = billing_service.get_subscription(db, current_user.tenant_id)
    if subscription is None or subscription.status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return  # no active plan yet — unmetered/legacy, see module docstring

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
