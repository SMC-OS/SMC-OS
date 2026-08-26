import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.auth.dependencies import get_current_user, require_role
from app.auth.models import UserRole
from app.quotes.service import (
    QuoteApprovalStateError,
    QuoteNotFoundError,
    quote_service,
)
from app.customers.service import customer_service
from app.database import crud
from app.database.database import get_db
from app.database.models import User
from app.quotes.ai_draft import AIDraftError, AIDraftUnavailable, ai_draft_service
from app.quotes.ai_models import AIDraftRequest, AIQuoteDraft
from app.quotes.pdf import PDFGenerator

router = APIRouter(
    prefix="/quotes", tags=["quotes"], dependencies=[Depends(get_current_user)]
)


def _serialize(quote) -> dict:
    return {
        "id": quote.id,
        "customer_id": quote.customer_id,
        "material": quote.material,
        "thickness": quote.thickness,
        "kitchen_length": quote.kitchen_length,
        "island": quote.island,
        "waterfall": quote.waterfall,
        "splashback": quote.splashback,
        "upstands": quote.upstands,
        "postcode": quote.postcode,
        "price_per_slab": quote.price_per_slab,
        "price_before_vat": quote.price_before_vat,
        "vat": quote.vat,
        "total": quote.total,
        "status": quote.status,
        "approved_at": quote.approved_at,
        "approved_by_user_id": quote.approved_by_user_id,
        "created_at": quote.created_at,
    }


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

    return _serialize(quote)


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
            "material": quote.material,
            "thickness": quote.thickness,
            "price_before_vat": quote.price_before_vat,
            "vat": quote.vat,
            "total": quote.total,
            "created_at": quote.created_at,
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
