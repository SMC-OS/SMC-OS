"""Sprint 017 (docs/DECISIONS.md ADR-033). No require_role — any
authenticated tenant user may send/list messages, matching the customer/
project/portal-link/document creation precedent (routine work, not a
tenant-control decision). The public, customer-facing side of this thread
(list/post via a portal token) lives on the existing app/portal/router.py,
not here — see app/portal/service.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access
from app.database.database import get_db
from app.database.models import User
from app.messages.models import MessageCreate, MessageOut
from app.messages.service import CustomerNotFoundError, message_service

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def post_message(
    customer_id: uuid.UUID,
    data: MessageCreate,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    try:
        return message_service.post_message(
            db,
            tenant_id=current_user.tenant_id,
            sender_user_id=current_user.id,
            customer_id=customer_id,
            body=data.body,
        )
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")


@router.get("", response_model=list[MessageOut])
def list_messages(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    try:
        return message_service.list_messages(db, current_user.tenant_id, customer_id)
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
