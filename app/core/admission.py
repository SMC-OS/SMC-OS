"""Release-freeze admission gate (Issue #67, P0).

While the owner's HOLD applies, no new workspace may be created and no
workspace without an existing Stripe subscription may start a trial or a
paid checkout. Existing users, existing workspaces and existing paying
subscriptions are untouched: sign-in, invitations, portals, the billing
portal, cancel and resume all keep working.

Server-side on purpose: hiding a button does not close an endpoint.
Reversible on purpose: one setting, NEW_ACCOUNT_ADMISSION=open|closed,
with no data change either way. The default is `open` so that deploying
this code changes nothing until the owner chooses to close admission.
"""

from fastapi import HTTPException, status

from app.core.config import settings

ADMISSION_CLOSED_DETAIL = (
    "GeoCore is not accepting new accounts or new subscriptions yet. "
    "Request a demo and we will contact you when places open."
)


def admission_open() -> bool:
    return settings.new_account_admission == "open"


def require_admission_open() -> None:
    if not admission_open():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ADMISSION_CLOSED_DETAIL)
