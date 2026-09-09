"""Communication history API (Sprint 038).

Read-only this phase — every write path goes through
app/communications/service.py's DeliveryService, called from the module
that owns the trigger (app/invitations today; app/quotes/app/automations
in Phase 3), never through a router here. No require_role: viewing a
customer/quote/project's communication history is routine day-to-day work,
the same posture as app/tasks/router.py.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.communications.models import CommunicationOut
from app.communications.service import delivery_service
from app.database.database import get_db
from app.database.models import User

router = APIRouter(
    prefix="/communications", tags=["communications"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[CommunicationOut])
def list_communications(
    customer_id: uuid.UUID | None = Query(default=None),
    quote_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    invitation_id: uuid.UUID | None = Query(default=None),
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delivery_service.list_history(
        db,
        current_user.tenant_id,
        customer_id=customer_id,
        quote_id=quote_id,
        project_id=project_id,
        invitation_id=invitation_id,
        limit=min(limit, 200),
    )
