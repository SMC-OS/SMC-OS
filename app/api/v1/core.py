"""The original main.py routes (/process, /quote, /estimate, /dashboard),
moved under /api/v1 for Sprint 003 (ADR-012). Sprint 005 added db: Session
= Depends(get_db) to reach the database-backed material catalogue. Sprint
007: /quote and /estimate now persist via quote_service (not the bare
calculator), /quote/pdf is removed (replaced by GET /api/v1/quotes/{id}/
invoice, which downloads a real PDF for an already-persisted quote — see
app/quotes/router.py), and /dashboard computes real numbers instead of
returning hardcoded ones.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.assistant.estimator import EstimatorAssistant
from app.brain.manager import BrainManager
from app.database import crud
from app.database.database import get_db
from app.quotes.models import QuoteRequest
from app.quotes.service import quote_service

router = APIRouter(tags=["core"])

manager = BrainManager()
estimator = EstimatorAssistant()


class Prompt(BaseModel):
    text: str


@router.post("/process")
def process(prompt: Prompt, db: Session = Depends(get_db)):
    return manager.process(db, prompt.text)


@router.post("/quote")
def create_quote(request: QuoteRequest, db: Session = Depends(get_db)):
    return quote_service.create(db, request)


@router.post("/estimate")
def estimate(prompt: Prompt, db: Session = Depends(get_db)):
    request = estimator.parse(prompt.text)
    quote = QuoteRequest(**request)
    return quote_service.create(db, quote)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return {
        "quotes_today": crud.count_quotes_today(db),
        "revenue": crud.sum_quotes_revenue(db),
        "customers": crud.count_customers(db),
        "projects": crud.count_projects(db),
    }
