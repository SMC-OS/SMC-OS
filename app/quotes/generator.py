from app.quotes.calculator import QuoteCalculator

class QuoteGenerator:

    def generate(self, request):

        calculator = QuoteCalculator()

        quote = calculator.calculate(request)

        return quote