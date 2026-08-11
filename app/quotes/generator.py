from sqlalchemy.orm import Session

from app.quotes.calculator import QuoteCalculator

class QuoteGenerator:

    def generate(self, db: Session, request):

        calculator = QuoteCalculator()

        quote = calculator.calculate(db, request)

        return quote