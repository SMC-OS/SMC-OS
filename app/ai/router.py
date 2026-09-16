"""GeoCore AI API (Sprint 036, Workstream H).

Replaces the developer-facing `POST /api/v1/process` as the product
surface. `/process` itself is untouched and still reachable — it is used
by existing callers and by this service's own fallback path — but the
product now talks to `/ai/*`, whose responses carry no endpoint names, no
class names and no sprint numbers.

Any authenticated member may use it. There is no write capability to gate:
the service has no tools and cannot modify a single record.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.models import AICapabilities, ChatRequest, ChatResponse
from app.ai.service import ai_service
from app.auth.dependencies import require_verified_email
from app.database.database import get_db
from app.database.models import User

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(require_verified_email)])


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
    current_user: User = Depends(require_verified_email),
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
