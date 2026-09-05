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
from app.quotes.general import (
    GeneralQuoteLineRequest,
    GeneralQuoteRequest,
    GeneralQuoteUpdate,
    price as price_general_quote,
)
from app.quotes.models import QuoteRequest
from app.tenants.service import tenant_service
from app.trades.catalogue import default_quote_kind


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


class QuoteKindError(Exception):
    """Raised when an operation is attempted against the wrong kind of
    quote — updating a stone quote through the general-quote endpoint, or
    vice versa. Sprint 036: the two kinds are priced by completely
    different code, and quietly applying one's rules to the other would
    silently corrupt a customer-facing price."""


class QuoteEditStateError(Exception):
    """Raised when a quote is edited after it has left draft. A quote that
    has been sent to a customer or approved is a document someone else is
    holding a copy of; changing its prices underneath them is a
    substitution, not an edit."""

# Sprint 036. A tuple, not a set literal inline at the call site, so the
# lifecycle is stated in one readable place.
_APPROVABLE_STATUSES = frozenset({"draft", "sent"})


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

        # Sprint 036 — "sent" joins "draft" as an approvable state. This
        # is a widening: everything approvable before this sprint is still
        # approvable, and a quote the customer has actually received is
        # the one most likely to be approved next.
        if quote.status not in _APPROVABLE_STATUSES:
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
            # Sprint 036 (Workstream F) — carry what the quote already
            # knows onto the project it becomes, rather than making
            # someone retype the site address and the value of a job they
            # just approved. All five are None for a quote that didn't
            # capture them (every quote created before this sprint), so
            # the resulting project is exactly what it was before.
            #
            # `name` is deliberately still the customer's name, unchanged:
            # existing tests and the projects list both depend on that,
            # and a quote title is a description of work rather than a
            # project label.
            project_type=quote.trade,
            site_address_line1=quote.site_address_line1,
            site_address_line2=quote.site_address_line2,
            site_city=quote.site_city,
            site_postcode=quote.site_postcode,
            estimated_value=quote.total,
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
            # Sprint 036 — denominate the document in the issuing
            # workspace's own currency, captured now rather than read
            # live, so changing a workspace's currency later never
            # re-prices a quote a customer already holds. An anonymous
            # quote (ADR-023, tenant_id=None) has no workspace to ask,
            # and falls back to the column default.
            currency=self._tenant_currency(db, tenant_id),
            subtotal=result["price_before_vat"],
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


    # ------------------------------------------------------------------
    # Sprint 036, Workstream E — general construction quoting.
    #
    # Everything below is the general path. It shares this service (and
    # therefore the approve/handoff/activity behaviour) with the stone
    # path deliberately: a quote's *lifecycle* is identical whatever trade
    # it is for, and only its *pricing* differs. What is NOT shared is the
    # pricing itself — a general quote never touches QuoteCalculator, the
    # material catalogue or the slab maths.
    # ------------------------------------------------------------------

    def _tenant_currency(self, db: Session, tenant_id: uuid.UUID | None) -> str:
        """The issuing workspace's currency, or GBP when there is no
        workspace to ask (an anonymous quote, ADR-023). Never another
        tenant's currency, and never a value read at render time — the
        caller stores the result on the quote row."""
        if tenant_id is None:
            return "GBP"
        tenant = tenant_service.get(db, tenant_id)
        return getattr(tenant, "currency", None) or "GBP"

    @staticmethod
    def _line_rows(
        lines: list[GeneralQuoteLineRequest], line_totals: list[float]
    ) -> list[dict]:
        """Map validated request lines onto QuoteItem column values.

        Every slab column is left None: a general line has no material,
        thickness or dimensions, and writing a placeholder into one would
        make it indistinguishable from a real stone line to every reader
        downstream (the PDF, the portal, the dashboard).

        `item_type` is pinned to "other" rather than mirroring line_kind.
        ITEM_TYPES is the stone vocabulary (worktop/island/splashback/...)
        and a labour line is none of them; "other" is the honest answer
        and keeps the column's existing NOT NULL contract intact.
        """
        return [
            {
                "line_kind": line.line_kind,
                "item_type": "other",
                "description": line.description,
                "unit": line.unit,
                "unit_price": line.unit_price,
                "quantity": line.quantity,
                "notes": line.notes,
                "line_total": line_total,
                "material": None,
                "thickness": None,
                "length_mm": None,
                "width_mm": None,
                "thickness_mm": None,
            }
            for line, line_total in zip(lines, line_totals, strict=True)
        ]

    def create_general(
        self,
        db: Session,
        data: GeneralQuoteRequest,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ):
        if data.customer_id is not None and crud.get_customer_by_id(
            db, data.customer_id, tenant_id
        ) is None:
            raise CustomerNotFoundError(data.customer_id)

        totals = price_general_quote(
            data.lines, vat_rate=data.vat_rate, discount_amount=data.discount_amount
        )

        fields = data.model_dump(exclude={"lines", "customer_id"})
        fields.update(
            {
                "subtotal": totals.subtotal,
                "discount_amount": totals.discount_amount,
                "price_before_vat": totals.price_before_vat,
                "vat": totals.vat,
                "total": totals.total,
                # The quote's own postcode column predates this sprint and
                # is what the dashboard and portal already read; mirror the
                # site postcode into it so a general quote is not invisible
                # to them.
                "postcode": data.site_postcode,
            }
        )

        row = crud.create_general_quote(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            customer_id=data.customer_id,
            currency=self._tenant_currency(db, tenant_id),
            fields=fields,
        )
        crud.replace_quote_items(db, row, self._line_rows(data.lines, totals.line_totals))

        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.QUOTE_CREATED,
                title="New quote created",
                description=f"{data.title} — {row.currency} {totals.total:,.2f}",
            ),
            tenant_id=tenant_id,
        )
        return row

    def update_general(
        self,
        db: Session,
        quote_id: uuid.UUID,
        tenant_id: uuid.UUID,
        data: GeneralQuoteUpdate,
    ):
        quote = crud.get_quote_by_id(db, quote_id, tenant_id)
        if quote is None:
            raise QuoteNotFoundError(quote_id)
        if quote.quote_kind != "general":
            raise QuoteKindError(quote.quote_kind)
        if quote.status != "draft":
            raise QuoteEditStateError(quote.status)

        changes = data.model_dump(exclude_unset=True)
        new_lines = changes.pop("lines", None)

        if changes.get("customer_id") is not None and crud.get_customer_by_id(
            db, changes["customer_id"], tenant_id
        ) is None:
            raise CustomerNotFoundError(changes["customer_id"])

        # Re-price against the values that will be stored, not the ones
        # that were: an update that changes only the VAT rate or only the
        # discount must still produce a correct total.
        lines = (
            [GeneralQuoteLineRequest(**line) for line in new_lines]
            if new_lines is not None
            else [
                GeneralQuoteLineRequest(
                    line_kind=item.line_kind if item.line_kind in {"labour", "material", "other"} else "other",
                    description=item.description or "Line item",
                    quantity=item.quantity,
                    unit=item.unit or "item",
                    unit_price=item.unit_price or 0.0,
                    notes=item.notes,
                )
                for item in quote.items
            ]
        )
        vat_rate = changes.get("vat_rate", quote.vat_rate)
        discount = (
            changes["discount_amount"]
            if "discount_amount" in changes
            else quote.discount_amount
        )
        totals = price_general_quote(lines, vat_rate=vat_rate, discount_amount=discount)

        changes.update(
            {
                "vat_rate": vat_rate,
                "subtotal": totals.subtotal,
                "discount_amount": totals.discount_amount,
                "price_before_vat": totals.price_before_vat,
                "vat": totals.vat,
                "total": totals.total,
            }
        )
        if "site_postcode" in changes:
            changes["postcode"] = changes["site_postcode"]

        updated = crud.update_general_quote(db, quote_id, tenant_id, changes)
        if new_lines is not None:
            crud.replace_quote_items(
                db, updated, self._line_rows(lines, totals.line_totals)
            )
        return updated

    def mark_sent(self, db: Session, quote_id: uuid.UUID, tenant_id: uuid.UUID):
        """Record that this quote has been given to the customer.

        GeoCore has no outbound email, SMS or messaging infrastructure, so
        this endpoint does NOT transmit anything — the user sends the PDF
        or the portal link themselves and marks it here. That is stated in
        the UI copy too. What it buys is real: a "sent" quote is the one
        worth chasing, and it is what the quote.sent automation trigger and
        the unanswered-quote follow-up template key off.

        Idempotent — marking an already-sent quote as sent is a no-op
        rather than an error, so a double-click cannot produce a spurious
        second automation run.
        """
        quote = crud.get_quote_by_id(db, quote_id, tenant_id)
        if quote is None:
            raise QuoteNotFoundError(quote_id)
        if quote.status == "sent":
            return quote
        if quote.status != "draft":
            raise QuoteApprovalStateError(quote.status)
        return crud.mark_quote_sent(db, quote_id, tenant_id, datetime.now(timezone.utc))


quote_service = QuoteService()
