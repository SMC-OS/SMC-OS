"""The original main.py routes (/process, /quote, /estimate, /quote/pdf,
/dashboard), moved under /api/v1 for Sprint 003 (ADR-012). Sprint 005 adds
db: Session = Depends(get_db) to every route that reaches the now
database-backed material catalogue (everything except /dashboard, which
stays hardcoded).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.assistant.estimator import EstimatorAssistant
from app.brain.manager import BrainManager
from app.database.database import get_db
from app.quotes.calculator import QuoteCalculator
from app.quotes.generator import QuoteGenerator
from app.quotes.models import QuoteRequest
from app.quotes.pdf import PDFGenerator

router = APIRouter(tags=["core"])

manager = BrainManager()
calculator = QuoteCalculator()
estimator = EstimatorAssistant()


class Prompt(BaseModel):
    text: str


@router.post("/process")
def process(prompt: Prompt, db: Session = Depends(get_db)):
    return manager.process(db, prompt.text)


@router.post("/quote")
def create_quote(request: QuoteRequest, db: Session = Depends(get_db)):
    return calculator.calculate(db, request)


@router.post("/estimate")
def estimate(prompt: Prompt, db: Session = Depends(get_db)):
    request = estimator.parse(prompt.text)
    quote = QuoteRequest(**request)
    return calculator.calculate(db, quote)


@router.post("/quote/pdf")
def create_pdf(request: QuoteRequest, db: Session = Depends(get_db)):
    quote = QuoteGenerator().generate(db, request)
    pdf = PDFGenerator().create(quote)
    return {"pdf": pdf, "quote": quote}


@router.get("/dashboard")
def dashboard():
    return {
        "quotes_today": 12,
        "revenue": 8420,
        "customers": 327,
        "projects": 18,
    }
