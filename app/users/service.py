"""UserManagementService — Sprint 015 (docs/DECISIONS.md ADR-031).

Second real attachment point for require_role(UserRole.OWNER) after
app/invitations/ (Sprint 011/ADR-028). Deactivation is soft: users.is_active
flips to false rather than deleting the row, since Invitation.
invited_by_user_id and PortalLink.created_by_user_id are both NOT NULL FKs
to users.id — a hard delete would break those historical rows. Matches
Invitation.status/PortalLink.status's established "status field, not row
deletion" pattern.

No "last owner" guard beyond self-deactivation: signup() always creates
exactly one Owner per tenant and invitations only ever create Staff (see
app/auth/service.py, app/invitations/service.py) — there is no code path to
a second Owner today, so "deactivate the tenant's only other Owner" cannot
occur. Not building speculative handling for a state the system cannot
reach.
"""

import uuid

from sqlalchemy.orm import Session

from app.database import crud
from app.database.models import User


class UserNotFoundError(Exception):
    """Unknown id, or an id that belongs to a different tenant. Deliberately
    the same error for both cases — a cross-tenant lookup must never confirm
    another tenant's user exists (ADR-028 precedent)."""


class CannotDeactivateSelfError(Exception):
    """An Owner cannot deactivate their own account through this route."""


class UserManagementService:
    def list_users(self, db: Session, tenant_id: uuid.UUID) -> list[User]:
        return crud.list_users_by_tenant(db, tenant_id)

    def deactivate_user(
        self, db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, acting_user_id: uuid.UUID
    ) -> User:
        if user_id == acting_user_id:
            raise CannotDeactivateSelfError(user_id)
        row = crud.get_user_by_id(db, user_id)
        if row is None or row.tenant_id != tenant_id:
            raise UserNotFoundError(user_id)
        return crud.update_user_active(db, user_id, is_active=False)


user_management_service = UserManagementService()
