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
from app.database.models import Project
from app.projects.models import ProjectStatus
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

    def handoff(
        self,
        db: Session,
        quote_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Project:
        quote = crud.get_quote_by_id(db, quote_id, tenant_id)
        if quote is None:
            raise QuoteNotFoundError(quote_id)

        if quote.status != "approved":
            raise QuoteApprovalStateError(quote.status)

        existing = crud.get_project_by_quote_id(db, quote.id, tenant_id)
        if existing is not None:
            return existing

        customer = (
            crud.get_customer_by_id(db, quote.customer_id, tenant_id)
            if quote.customer_id is not None
            else None
        )
        name = customer.name if customer is not None else f"Quote {quote.id}"

        project = crud.create_project(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            customer_id=quote.customer_id,
            notes=None,
            status=ProjectStatus.BOOKED.value,
            quote_id=quote.id,
        )

        # Same backend-logs-its-own-ActivityEvent pattern as approve() above.
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.QUOTE_HANDED_OFF,
                title="Quote handed off",
                description=f"Quote {quote.id} to project {project.id}",
            ),
            tenant_id=tenant_id,
        )

        return project

    def create(self, db: Session, quote: QuoteRequest, tenant_id: uuid.UUID | None = None) -> dict:
        if (
            quote.customer_id is not None
            and tenant_id is not None
            and crud.get_customer_by_id(db, quote.customer_id, tenant_id) is None
        ):
            raise CustomerNotFoundError(quote.customer_id)

        result = self.calculator.calculate(db, quote)
        first_item = result["items"][0]

        row = crud.create_quote(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            customer_id=quote.customer_id,
            # Sprint 033 (Workstream C) — these columns are now a
            # best-effort single-item *summary* of `items` below, kept
            # for every reader that predates multi-item quotes (see
            # app/database/models.py's Quote docstring and
            # QuoteCalculator.summarize_items()). `items` is the source
            # of truth.
            material=result["material"],
            thickness=result["thickness"],
            kitchen_length=first_item["length_mm"] / 1000,
            quantity=first_item["quantity"],
            length_mm=first_item["length_mm"],
            width_mm=first_item["width_mm"],
            thickness_mm=first_item["thickness_mm"],
            unit_input=first_item["unit_input"],
            # The old per-quote flags are frozen at their Sprint-032
            # meaning — a new quote's real extras are independent items
            # (see QuoteItem), never these columns.
            island=False,
            waterfall=0,
            splashback=False,
            splashback_length_mm=None,
            upstands=False,
            upstands_length_mm=None,
            postcode=quote.postcode,
            price_per_slab=result["price_per_slab"],
            price_before_vat=result["price_before_vat"],
            vat=result["vat"],
            total=result["total"],
        )

        crud.create_quote_items(
            db,
            [
                {
                    "quote_id": row.id,
                    "position": index,
                    "item_type": item["item_type"],
                    "material": item["material"],
                    "thickness": item["thickness"],
                    "quantity": item["quantity"],
                    "length_mm": item["length_mm"],
                    "width_mm": item["width_mm"],
                    "thickness_mm": item["thickness_mm"],
                    "unit_input": item["unit_input"],
                    "notes": item["notes"],
                    "price_per_slab": item["price_per_slab"],
                    "slabs": item["slabs"],
                    "line_total": item["line_total"],
                }
                for index, item in enumerate(result["items"])
            ],
        )
        db.refresh(row)

        # Sprint 004/006 established this pattern: the backend logs its own
        # ActivityEvent, replacing a standalone frontend call.
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.QUOTE_CREATED,
                title="New quote created",
                description=f"{quote.customer} — {result['material']}, £{result['total']:,.2f}",
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
