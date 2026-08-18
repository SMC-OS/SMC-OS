"""MessageService — Sprint 017 (docs/DECISIONS.md ADR-033).

Staff side of client-portal messaging only. The customer/public side lives
in app/portal/service.py (list_customer_messages/post_customer_message),
which calls app/database/crud.py directly rather than through this
service — same split PortalService already uses for documents/quotes
(get_customer_document/get_customer_quote bypass DocumentService/
QuotesService and call crud directly).
"""

import uuid

from sqlalchemy.orm import Session

from app.database import crud
from app.database.models import Message


class CustomerNotFoundError(Exception):
    """customer_id doesn't resolve under the caller's own tenant — the
    same relationship-linkage-bypass check ADR-029 added elsewhere,
    reused from PortalService.create_link()/DocumentService.upload_document()."""


class MessageService:
    def post_message(
        self, db: Session, *, tenant_id: uuid.UUID, sender_user_id: uuid.UUID, customer_id: uuid.UUID, body: str
    ) -> Message:
        customer = crud.get_customer_by_id(db, customer_id, tenant_id)
        if customer is None:
            raise CustomerNotFoundError(customer_id)

        row = crud.create_message(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            sender_user_id=sender_user_id,
            sender_type="staff",
            body=body,
        )

        return row

    def list_messages(self, db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> list[Message]:
        if crud.get_customer_by_id(db, customer_id, tenant_id) is None:
            raise CustomerNotFoundError(customer_id)
        return crud.list_messages_by_customer(db, tenant_id, customer_id)


message_service = MessageService()
