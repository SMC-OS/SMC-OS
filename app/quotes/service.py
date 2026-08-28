"""QuoteService — the persistence seam Sprint 007 adds on top of the
existing pure QuoteCalculator/SlabCalculator. Every caller of a calculated
quote (POST /quote, POST /estimate) goes through here now, so persistence
and activity-logging happen once, not duplicated per route. Route-level
pattern (get_db() directly), same as app/customers/, app/projects/,
app/materials/ (ADR-019) — no repository interface, that pattern was for
the pre-database era (ADR-001).
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.database import crud
from app.quotes.calculator import QuoteCalculator
from app.quotes.models import QuoteRequest


class CustomerNotFoundError(Exception):
    """Raised by create() when quote.customer_id is set, the caller is
    authenticated (tenant_id is not None), and that customer doesn't
    belong to the caller's own tenant (Sprint 012, ADR-029) — otherwise a
    quote could be linked to another tenant's customer by guessing/knowing
    its id. Anonymous calls (tenant_id=None, ADR-023's public /quote and
    /estimate) skip this check: there's no tenant to validate ownership
    against, and the resulting quote is itself tenant_id=None — invisible
    to every tenant's authenticated browsing routes either way."""

class QuoteNotFoundError(Exception):
    pass


class QuoteApprovalStateError(Exception):
    pass

class QuoteService:
    def __init__(self) -> None:
        self.calculator = QuoteCalculator()
    def approve(
        self,
        db: Session,
        quote_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ):
        quote = crud.get_quote_by_id(db, quote_id, tenant_id)
        if quote is None:
            raise QuoteNotFoundError(quote_id)

        if quote.status != "draft":
            raise QuoteApprovalStateError(quote.status)

        quote.status = "approved"
        quote.approved_at = datetime.now(timezone.utc)
        quote.approved_by_user_id = actor_user_id
        db.commit()
        db.refresh(quote)

        # Same backend-logs-its-own-ActivityEvent pattern as create() above.
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.QUOTE_APPROVED,
                title="Quote approved",
                description=f"Quote {quote.id}",
            ),
            tenant_id=tenant_id,
        )

        return quote
    def create(self, db: Session, quote: QuoteRequest, tenant_id: uuid.UUID | None = None) -> dict:
        if (
            quote.customer_id is not None
            and tenant_id is not None
            and crud.get_customer_by_id(db, quote.customer_id, tenant_id) is None
        ):
            raise CustomerNotFoundError(quote.customer_id)

        result = self.calculator.calculate(db, quote)

        row = crud.create_quote(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            customer_id=quote.customer_id,
            material=quote.material,
            thickness=quote.thickness,
            kitchen_length=quote.kitchen_length,
            island=quote.island,
            waterfall=quote.waterfall,
            splashback=quote.splashback,
            upstands=quote.upstands,
            postcode=quote.postcode,
            price_per_slab=result["price_per_slab"],
            price_before_vat=result["price_before_vat"],
            vat=result["vat"],
            total=result["total"],
        )

        # Sprint 004/006 established this pattern: the backend logs its own
        # ActivityEvent, replacing a standalone frontend call.
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.QUOTE_CREATED,
                title="New quote created",
                description=f"{quote.customer} — {quote.material}, £{result['total']:,.2f}",
            ),
            tenant_id=tenant_id,
        )

        return {
            **result,
            "id": row.id,
            "customer_id": row.customer_id,
            "created_at": row.created_at,
        }


quote_service = QuoteService()
