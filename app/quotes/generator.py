# Superseded by app/quotes/service.py (Sprint 007) — no longer imported
# anywhere. QuoteGenerator only ever wrapped POST /quote/pdf, which was
# removed this sprint in favour of GET /api/v1/quotes/{id}/invoice against
# an already-persisted quote. Kept in place rather than deleted, per
# ADR-008 ("archive, don't delete without separate approval").

from sqlalchemy.orm import Session

from app.quotes.calculator import QuoteCalculator

class QuoteGenerator:

    def generate(self, db: Session, request):

        calculator = QuoteCalculator()

        quote = calculator.calculate(db, request)

        return quote