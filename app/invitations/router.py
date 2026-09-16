"""Sprint 011 (docs/DECISIONS.md ADR-028).

Role scope: Staff-only invites. InvitationCreate has no `role` field —
create_invitation() always writes UserRole.STAFF. The `role` column exists
on the table so a future sprint can widen this without a migration, but
letting an Owner mint a second Owner via this flow is a materially bigger
decision than "Staff Invitations" implies — left to a future sprint.

No router-level `dependencies=[...]` (unlike tenants/customers/projects):
this router genuinely mixes Owner-only and fully public routes, the same
shape app/auth/router.py already has (public /signup+/login, gated /me).
Auth is applied per-route below.

This is also the first sprint where require_role(UserRole.OWNER) is
attached to a real route — see app/auth/dependencies.py's docstring and
docs/DECISIONS.md ADR-027.

Sprint 038 — create/list now also return `delivery_status`, the real
outcome of the invitation email DeliveryService attempts on creation
(app/invitations/service.py). The manual-link fallback (`token` in the
create response) is unchanged either way.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access, require_role_and_billing
from app.auth.models import TokenResponse, UserRole
from app.auth.security import create_access_token
from app.auth.service import auth_service
from app.billing.entitlements import require_seat_available
from app.database import crud
from app.database.database import get_db
from app.database.models import User
from app.invitations.models import (
    AcceptInvitationRequest,
    InvitationCreate,
    InvitationCreateOut,
    InvitationOut,
    InvitationPublicOut,
)
from app.invitations.service import (
    EmailAlreadyRegisteredError,
    InvitationNotFoundError,
    InvitationNotUsableError,
    PendingInvitationExistsError,
    invitation_service,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])

_UNUSABLE_MESSAGES = {
    "revoked": "This invitation has been revoked.",
    "accepted": "This invitation has already been used.",
    "expired": "This invitation link has expired.",
}


def _with_delivery_status(db: Session, tenant_id: uuid.UUID, item: InvitationOut) -> InvitationOut:
    """Sprint 038 — enrich an already-built InvitationOut with the real
    outcome of its invitation email, from the latest matching
    app.communications.Communication row. Never raises: a missing/absent
    communication (delivery not yet attempted, or this row predates Sprint
    038) just leaves delivery_status as None, which the frontend renders
    as "link only" rather than a failure."""
    communication = crud.get_latest_communication_for_invitation(db, tenant_id, item.id)
    if communication is not None:
        item.delivery_status = communication.status
        item.delivery_failure_detail = communication.failure_detail
    return item


@router.post(
    "",
    response_model=InvitationCreateOut,
    status_code=status.HTTP_201_CREATED,
    # Sprint 039 Production Readiness Defect Gate, Blocker 1 — inviting a
    # second user into a tenant is the concrete "user-management" boundary
    # this gate's require_billing_access enforcement applies to first;
    # other sensitive boundaries (billing, security settings) gain the
    # same guard as their own gate phases land, rather than all being
    # bolted on here at once.
    dependencies=[Depends(require_seat_available), Depends(require_billing_access)],
)
def create_invitation(
    data: InvitationCreate,
    current_user: User = Depends(require_role_and_billing(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    try:
        row, raw_token = invitation_service.create_invitation(
            db, tenant_id=current_user.tenant_id, invited_by_user_id=current_user.id, email=data.email
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A user with that email already exists."
        )
    except PendingInvitationExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invitation is already pending for this email.",
        )
    item = InvitationOut.model_validate(row)
    item = _with_delivery_status(db, current_user.tenant_id, item)
    return InvitationCreateOut(**item.model_dump(), token=raw_token)


@router.get("", response_model=list[InvitationOut])
def list_invitations(
    status_filter: str | None = None,
    current_user: User = Depends(require_role_and_billing(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    rows = invitation_service.list_invitations(db, current_user.tenant_id, status=status_filter)
    out = []
    for row in rows:
        item = InvitationOut.model_validate(row)
        item.status = invitation_service.derive_status(row)
        item = _with_delivery_status(db, current_user.tenant_id, item)
        out.append(item)
    return out


@router.delete("/{invitation_id}", response_model=InvitationOut)
def revoke_invitation(
    invitation_id: uuid.UUID,
    current_user: User = Depends(require_role_and_billing(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    try:
        return invitation_service.revoke_invitation(db, current_user.tenant_id, invitation_id)
    except InvitationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")


@router.get("/token/{token}", response_model=InvitationPublicOut)
def get_invitation_by_token(token: str, db: Session = Depends(get_db)):
    row = invitation_service.get_invitation_by_token(db, token)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    tenant = crud.get_tenant_by_id(db, row.tenant_id)
    return InvitationPublicOut(
        email=row.email,
        role=row.role,
        tenant_name=tenant.name if tenant is not None else "",
        status=invitation_service.derive_status(row),
        expires_at=row.expires_at,
    )


@router.post("/token/{token}/accept", response_model=TokenResponse)
def accept_invitation(token: str, data: AcceptInvitationRequest, db: Session = Depends(get_db)):
    try:
        tenant, user = invitation_service.accept_invitation(
            db, token, name=data.name, password=data.password
        )
    except InvitationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    except InvitationNotUsableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_UNUSABLE_MESSAGES.get(exc.reason, "This invitation can no longer be used."),
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A user with that email already exists."
        )
    access_token = create_access_token(
        subject=str(user.id), tenant_id=str(tenant.id), token_version=user.token_version
    )
    return TokenResponse(access_token=access_token, user=auth_service.build_user_out(db, user))
