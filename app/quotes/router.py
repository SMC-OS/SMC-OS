import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.auth.dependencies import get_current_user, require_role
from app.auth.models import UserRole
from app.automations.dispatcher import automation_dispatcher
from app.quotes.general import GeneralQuoteRequest, GeneralQuoteUpdate
from app.quotes.service import (
    CustomerNotFoundError,
    QuoteApprovalStateError,
    QuoteEditStateError,
    QuoteKindError,
    QuoteNotFoundError,
    quote_service,
)
from app.trades.catalogue import TRADES
from app.trades.units import UNITS
from app.customers.service import customer_service
from app.database import crud
from app.database.database import get_db
from app.database.models import User
from app.projects.models import ProjectOut
from app.quotes.ai_draft import AIDraftError, AIDraftUnavailable, ai_draft_service
from app.quotes.ai_models import AIDraftRequest, AIQuoteDraft
from app.quotes.pdf import PDFGenerator, build_line_items
from app.tenants import identity as tenant_identity
from app.tenants.service import tenant_service

router = APIRouter(
    prefix="/quotes", tags=["quotes"], dependencies=[Depends(get_current_user)]
)


def _serialize_item(item) -> dict:
    return {
        "id": item.id,
        "position": item.position,
        # Sprint 036 — which pricing model this line uses. Every line that
        # predates this sprint is "stone", by column default.
        "line_kind": item.line_kind,
        "description": item.description,
        "unit": item.unit,
        "unit_price": item.unit_price,
        "item_type": item.item_type,
        "material": item.material,
        "thickness": item.thickness,
        "quantity": item.quantity,
        "length_mm": item.length_mm,
        "width_mm": item.width_mm,
        "thickness_mm": item.thickness_mm,
        "unit_input": item.unit_input,
        "notes": item.notes,
        "price_per_slab": item.price_per_slab,
        "slabs": item.slabs,
        "line_total": item.line_total,
    }


def _serialize(quote) -> dict:
    return {
        "id": quote.id,
        "customer_id": quote.customer_id,
        # --- Sprint 036 (Workstream E) — the universal quote envelope. ---
        # Added to the existing dict rather than replacing it: every key
        # that existed before this sprint is still present and still means
        # exactly what it meant, so no existing reader breaks.
        "quote_kind": quote.quote_kind,
        "title": quote.title,
        "trade": quote.trade,
        "site_address_line1": quote.site_address_line1,
        "site_address_line2": quote.site_address_line2,
        "site_city": quote.site_city,
        "site_postcode": quote.site_postcode,
        "scope_of_works": quote.scope_of_works,
        "notes": quote.notes,
        "exclusions": quote.exclusions,
        "terms": quote.terms,
        "valid_until": quote.valid_until,
        "currency": quote.currency,
        "vat_rate": quote.vat_rate,
        "subtotal": quote.subtotal,
        "discount_amount": quote.discount_amount,
        "sent_at": quote.sent_at,
        # Sprint 033 — these remain a best-effort single-item summary;
        # `items` is the source of truth (see app/database/models.py's
        # Quote docstring).
        "material": quote.material,
        "thickness": quote.thickness,
        "kitchen_length": quote.kitchen_length,
        "quantity": quote.quantity,
        "length_mm": quote.length_mm,
        "width_mm": quote.width_mm,
        "thickness_mm": quote.thickness_mm,
        "unit_input": quote.unit_input,
        "island": quote.island,
        "waterfall": quote.waterfall,
        "splashback": quote.splashback,
        "splashback_length_mm": quote.splashback_length_mm,
        "upstands": quote.upstands,
        "upstands_length_mm": quote.upstands_length_mm,
        "postcode": quote.postcode,
        "price_per_slab": quote.price_per_slab,
        "price_before_vat": quote.price_before_vat,
        "vat": quote.vat,
        "total": quote.total,
        "status": quote.status,
        "approved_at": quote.approved_at,
        "approved_by_user_id": quote.approved_by_user_id,
        "created_at": quote.created_at,
        "items": [_serialize_item(item) for item in quote.items],
    }


# Sprint 036 — declared before /{quote_id} so these literal segments win
# over the uuid path parameter (same ordering rule app/tenants/router.py
# documents). Both are static vocabularies with no tenant data in them,
# so they need no role gate beyond the router-level get_current_user.
@router.get("/meta/trades")
def list_trades():
    """The trades a quote or project can be for. Served from the backend
    rather than duplicated as a frontend constant so the quote form, the
    project form and the onboarding trade picker cannot drift apart."""
    return [
        {
            "key": trade.key,
            "label": trade.label,
            "default_quote_kind": trade.default_quote_kind,
        }
        for trade in TRADES
    ]


@router.get("/meta/units")
def list_units():
    """Units a general quote line can be priced in. Curated rather than
    free text so four quotes from the same company don't say "sqm",
    "sq m", "m2" and "m²"."""
    return [{"key": unit.key, "label": unit.label} for unit in UNITS]


@router.get("")
def list_quotes(
    limit: int = 20, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return [_serialize(q) for q in crud.list_quotes(db, current_user.tenant_id, limit=limit)]


@router.get("/{quote_id}")
def get_quote(
    quote_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quote = crud.get_quote_by_id(db, quote_id, current_user.tenant_id)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    return _serialize(quote)

@router.post("", status_code=status.HTTP_201_CREATED)
def create_general_quote(
    data: GeneralQuoteRequest,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    """Create a general construction quote (Sprint 036, Workstream E).

    Deliberately a different endpoint from the pre-existing
    `POST /api/v1/quote`, which is the public, unauthenticated stone
    calculator (ADR-023) and stays exactly as it was. This one is
    authenticated and Owner/Staff-gated, matching approve/handoff: it
    writes a priced, tenant-owned document.

    Nothing here touches the material catalogue or the slab maths. The
    price is the sum of the lines the quoter entered — GeoCore arranges,
    totals and presents it; it does not invent it.
    """
    try:
        quote = quote_service.create_general(
            db, data, tenant_id=current_user.tenant_id, actor_user_id=current_user.id
        )
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    automation_dispatcher.dispatch_quote_created(db, quote)
    return _serialize(quote)


@router.patch("/{quote_id}")
def update_general_quote(
    quote_id: uuid.UUID,
    data: GeneralQuoteUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    """Edit a *draft* general quote. Three refusals, each with its own
    status code so the UI can say something specific:

      404 — unknown quote, or one belonging to another tenant (ADR-028:
            confirming another tenant's id exists is itself a leak).
      409 — a stone quote (priced by a completely different code path;
            applying general-quote rules to it would corrupt its price).
      409 — a quote that has been sent or approved. That document is in
            someone else's hands; changing its prices underneath them is a
            substitution, not an edit.
    """
    try:
        quote = quote_service.update_general(
            db, quote_id, current_user.tenant_id, data
        )
    except QuoteNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    except QuoteKindError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only general quotes can be edited here",
        )
    except QuoteEditStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft quotes can be edited",
        )
    return _serialize(quote)


@router.post("/{quote_id}/send")
def send_quote(
    quote_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    """Mark a quote as sent to the customer.

    This transmits NOTHING. GeoCore has no outbound email, SMS or
    messaging infrastructure — the user sends the PDF or the portal link
    themselves and records it here, and the UI says so in as many words.
    What it buys is a real pipeline state: a sent quote is the one worth
    chasing, and it drives the quote.sent automation trigger and the
    unanswered-quote follow-up.

    Idempotent: sending an already-sent quote returns it unchanged rather
    than erroring, so a double-click cannot fire the automation twice.
    """
    try:
        quote = quote_service.mark_sent(db, quote_id, current_user.tenant_id)
    except QuoteNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    except QuoteApprovalStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a draft quote can be marked as sent",
        )

    automation_dispatcher.dispatch_quote_sent(db, quote)
    return _serialize(quote)


@router.post("/{quote_id}/approve")
def approve_quote(
    quote_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        quote = quote_service.approve(
            db,
            quote_id,
            current_user.tenant_id,
            current_user.id,
        )
    except QuoteNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )
    except QuoteApprovalStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quote cannot be approved in its current state",
        )

    # Sprint 036 (Workstream G) — automation dispatch happens after the
    # approval has committed, and can never fail this request: a broken
    # automation records a failed run and is swallowed (see
    # AutomationDispatcher). Approving a quote must not depend on the
    # health of a user-authored rule.
    automation_dispatcher.dispatch_quote_approved(db, quote, actor_user_id=current_user.id)
    return _serialize(quote)


@router.post("/{quote_id}/handoff", response_model=ProjectOut)
def handoff_quote(
    quote_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return quote_service.handoff(db, quote_id, current_user.tenant_id)
    except QuoteNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )
    except QuoteApprovalStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quote must be approved before handoff",
        )


@router.get("/{quote_id}/invoice")
def download_invoice(
    quote_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quote = crud.get_quote_by_id(db, quote_id, current_user.tenant_id)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")

    customer_name = "No customer linked"
    if quote.customer_id is not None:
        customer = customer_service.get(db, quote.customer_id, tenant_id=current_user.tenant_id)
        if customer is not None:
            customer_name = customer.name

    pdf_bytes = PDFGenerator().create(
        {
            "id": quote.id,
            "customer": customer_name,
            # Sprint 034 — the letterhead is this tenant's own business
            # identity, resolved from its profile, never a global default.
            "company": tenant_identity.resolve(
                tenant_service.get(db, current_user.tenant_id)
            ),
            "line_items": build_line_items(quote),
            "price_before_vat": quote.price_before_vat,
            "vat": quote.vat,
            "total": quote.total,
            "created_at": quote.created_at,
            # Sprint 036 — a general quote's own job title, currency,
            # applied VAT rate and any discount. All absent on a quote
            # created before this sprint, in which case the PDF renders
            # exactly as it always has.
            "title": quote.title,
            "currency": quote.currency,
            "vat_rate": quote.vat_rate,
            "discount_amount": quote.discount_amount,
        }
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice-{str(quote.id)[:8]}.pdf"'
        },
    )


@router.post("/ai-draft", response_model=AIQuoteDraft)
def generate_ai_draft(
    data: AIDraftRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    """AI Quotation Generator v1 — extraction only, never pricing (see
    app/quotes/ai_draft.py's docstring). Persists nothing to `quotes`; the
    only side effect is one ActivityEvent, same as the seed data has
    previewed since Sprint 001."""
    try:
        draft = ai_draft_service.generate(db, data.text)
    except AIDraftUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except AIDraftError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider request failed. Try again or fill the form manually.",
        )

    activity_service.log(
        ActivityEventCreate(
            type=ActivityType.AI_REQUEST,
            title="AI Estimator request processed",
            description=data.text[:200],
        ),
        tenant_id=current_user.tenant_id,
    )

    return draft
