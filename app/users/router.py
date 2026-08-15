"""Sprint 015 (docs/DECISIONS.md ADR-031). Both routes require
require_role(UserRole.OWNER), applied per-route (same style
app/invitations/router.py uses) rather than a router-level dependency —
this module has no public route, but matching the one existing exemplar
keeps the auth-gating style consistent across the codebase rather than
introducing a second pattern for it.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.auth.dependencies import require_role
from app.auth.models import UserRole
from app.database.database import get_db
from app.database.models import User
from app.users.models import TeamMemberOut
from app.users.service import CannotDeactivateSelfError, UserNotFoundError, user_management_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[TeamMemberOut])
def list_users(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    return user_management_service.list_users(db, current_user.tenant_id)


@router.post("/{user_id}/deactivate", response_model=TeamMemberOut)
def deactivate_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    try:
        row = user_management_service.deactivate_user(
            db, tenant_id=current_user.tenant_id, user_id=user_id, acting_user_id=current_user.id
        )
    except CannotDeactivateSelfError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot deactivate your own account.",
        )
    except UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    activity_service.log(
        ActivityEventCreate(
            type=ActivityType.TEAM_MEMBER_DEACTIVATED,
            title="Team member deactivated",
            description=row.name,
        ),
        tenant_id=current_user.tenant_id,
    )
    return row
