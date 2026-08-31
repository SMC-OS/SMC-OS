"""The original main.py routes (/process, /quote, /estimate, /dashboard),
moved under /api/v1 for Sprint 003 (ADR-012). Sprint 005 added db: Session
= Depends(get_db) to reach the database-backed material catalogue. Sprint
007: /quote and /estimate now persist via quote_service (not the bare
calculator), /quote/pdf is removed (replaced by GET /api/v1/quotes/{id}/
invoice, which downloads a real PDF for an already-persisted quote — see
app/quotes/router.py), and /dashboard computes real numbers instead of
returning hardcoded ones.

Sprint 012 (ADR-029) — /quote and /estimate stay deliberately public
(ADR-023), but now use get_current_user_optional to opportunistically tag
the created Quote with the caller's tenant when a valid token is present;
called with no token, the quote is still created, just with no tenant
(visible to nobody's authenticated /quotes browsing). /dashboard now
requires auth and returns only the caller's tenant's counts — it had no
auth at all before this sprint (see docs/USER_ROLES.md §1's now-resolved
"still true" list). /process is untouched: it only ever reads the shared,
tenant-agnostic materials catalogue (app/assistant/sales.py, search.py).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.assistant.estimator import EstimatorAssistant
from app.auth.dependencies import get_current_user_optional, require_role
from app.auth.models import UserRole
from app.brain.manager import BrainManager
from app.database import crud
from app.database.database import get_db
from app.database.models import User
from app.quotes.models import QuoteRequest
from app.quotes.service import CustomerNotFoundError, quote_service

router = APIRouter(tags=["core"])

manager = BrainManager()
estimator = EstimatorAssistant()


class Prompt(BaseModel):
    text: str


@router.post("/process")
def process(prompt: Prompt, db: Session = Depends(get_db)):
    return manager.process(db, prompt.text)


@router.post("/quote")
def create_quote(
    request: QuoteRequest,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    tenant_id = current_user.tenant_id if current_user is not None else None
    try:
        return quote_service.create(db, request, tenant_id=tenant_id)
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")


@router.post("/estimate")
def estimate(
    prompt: Prompt,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    request = estimator.parse(prompt.text)
    quote = QuoteRequest(**request)
    tenant_id = current_user.tenant_id if current_user is not None else None
    try:
        return quote_service.create(db, quote, tenant_id=tenant_id)
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")


@router.get("/dashboard")
def dashboard(
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    tenant_id = current_user.tenant_id
    return {
        "quotes_today": crud.count_quotes_today(db, tenant_id),
        "revenue": crud.sum_quotes_revenue(db, tenant_id),
        "customers": crud.count_customers(db, tenant_id),
        "projects": crud.count_projects(db, tenant_id),
    }
