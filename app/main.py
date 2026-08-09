from fastapi import FastAPI
from pydantic import BaseModel
from app.brain.manager import BrainManager
from app.quotes.calculator import QuoteCalculator
from app.quotes.generator import QuoteGenerator
from app.quotes.models import QuoteRequest
from app.assistant.estimator import EstimatorAssistant
from app.quotes.pdf import PDFGenerator
from fastapi.middleware.cors import CORSMiddleware

# Sprint 001: Recent Activity + Notifications for the dashboard shell.
# Both are additive — no existing route below is modified.
from app.activity.router import router as activity_router
from app.activity.seed import seed_activity
from app.notifications.router import router as notifications_router
from app.notifications.seed import seed_notifications

estimator = EstimatorAssistant()

app = FastAPI(
    title="Simo OS",
    version="0.1.0",
    description="AI Operating System"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(activity_router)
app.include_router(notifications_router)

seed_activity()
seed_notifications()

manager = BrainManager()

calculator = QuoteCalculator()


@app.get("/")
def root():
    return {
        "message": "Welcome to Simo OS",
        "status": "running"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }
class Prompt(BaseModel):
    text: str


@app.post("/process")
def process(prompt: Prompt):
    return manager.process(prompt.text)

@app.post("/quote")
def create_quote(request: QuoteRequest):
    return calculator.calculate(request)

@app.post("/estimate")
def estimate(prompt: Prompt):

    request = estimator.parse(prompt.text)

    quote = QuoteRequest(**request)

    return calculator.calculate(quote)

@app.post("/quote/pdf")
def create_pdf(request: QuoteRequest):

    quote = QuoteGenerator().generate(request)

    pdf = PDFGenerator().create(quote)

    return {
        "pdf": pdf,
        "quote": quote
    }

@app.get("/dashboard")
def dashboard():

    return {
        "quotes_today": 12,
        "revenue": 8420,
        "customers": 327,
        "projects": 18
    }
   

