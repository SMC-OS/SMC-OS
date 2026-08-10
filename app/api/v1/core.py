"""The original main.py routes (/process, /quote, /estimate, /quote/pdf,
/dashboard), moved under /api/v1 for Sprint 003 (ADR-012). Route bodies are
unchanged from main.py — only their location and mount prefix changed.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.assistant.estimator import EstimatorAssistant
from app.brain.manager import BrainManager
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
def process(prompt: Prompt):
    return manager.process(prompt.text)


@router.post("/quote")
def create_quote(request: QuoteRequest):
    return calculator.calculate(request)


@router.post("/estimate")
def estimate(prompt: Prompt):
    request = estimator.parse(prompt.text)
    quote = QuoteRequest(**request)
    return calculator.calculate(quote)


@router.post("/quote/pdf")
def create_pdf(request: QuoteRequest):
    quote = QuoteGenerator().generate(request)
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
