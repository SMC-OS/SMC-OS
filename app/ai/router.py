"""GeoCore AI API (Sprint 036, Workstream H).

Replaces the developer-facing `POST /api/v1/process` as the product
surface. `/process` itself is untouched and still reachable — it is used
by existing callers and by this service's own fallback path — but the
product now talks to `/ai/*`, whose responses carry no endpoint names, no
class names and no sprint numbers.

Any authenticated member may use it. There is no write capability to gate:
the service has no tools and cannot modify a single record.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.drafting import (
    DraftRequest,
    DraftResult,
    DraftingUnavailableError,
    EntityNotFoundError,
    RewriteRequest,
    ai_drafting_service,
)
from app.ai.models import AICapabilities, ChatRequest, ChatResponse
from app.ai.service import ai_service
from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.database.models import User

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(get_current_user)])


@router.get("/capabilities", response_model=AICapabilities)
def capabilities():
    """What GeoCore AI can genuinely do in this deployment.

    The UI reads this instead of assuming. A workspace with no AI provider
    connected is told so plainly, and the interface offers the built-in
    catalogue assistant rather than advertising capabilities that would
    silently do nothing.
    """
    return ai_service.capabilities()


@router.post("/chat", response_model=ChatResponse)
def chat(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One conversational turn, grounded in a bounded, tenant-scoped
    summary of this workspace (see app/ai/context.py for exactly what is
    and is not included — no customer contact details ever leave the
    database through this path).

    Never returns a provider error to the user: if the AI provider is
    unreachable, the deterministic built-in assistant answers instead and
    the response says which engine replied.
    """
    return ai_service.chat(db, current_user.tenant_id, data.messages)


# --- Drafting (Sprint 039, Workstream C) ---------------------------------
#
# These endpoints produce *text*. Neither of them sends anything, and
# `DraftResult` has no field that could hold a delivery outcome — see
# app/ai/drafting.py's module docstring for why that is structural rather
# than a promise. Sending a reviewed draft is a separate, human action:
# POST /communications/send.
#
# Any authenticated member may draft. There is no write capability to
# gate — a draft changes no record, and the person who sends it is gated
# by the send endpoint instead.


@router.post("/draft", response_model=DraftResult)
def draft_message(
    data: DraftRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Draft a customer message, grounded in this workspace's own records.

    Every entity referenced is re-fetched with the caller's `tenant_id`,
    so an id belonging to another tenant produces a 404 and is never read
    — let alone put into a prompt.
    """
    try:
        return ai_drafting_service.draft(
            db, tenant_id=current_user.tenant_id, request=data
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{exc} not found"
        )
    except DraftingUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No AI provider is connected to this workspace, so GeoCore AI "
                "can't draft messages yet. You can still write and send one "
                "yourself."
            ),
        )


@router.post("/rewrite", response_model=DraftResult)
def rewrite_message(
    data: RewriteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Shorten, expand or re-tone a draft the user already has.

    Works on the supplied text rather than regenerating from context, so a
    person's own edits survive a "make it shorter".
    """
    try:
        return ai_drafting_service.rewrite(
            db, tenant_id=current_user.tenant_id, request=data
        )
    except DraftingUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No AI provider is connected to this workspace, so GeoCore AI "
                "can't rewrite messages yet."
            ),
        )
