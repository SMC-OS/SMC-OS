from app.quotes.slab_calculator import SlabCalculator
from app.data.pricing import PRICES


class QuoteCalculator:

    def calculate(self, quote):

        base_price = PRICES[quote.material.lower()]

        slabs = SlabCalculator().calculate(quote)

        material_price = base_price * slabs

        total = material_price

        if quote.island:
            total += 450

        total += quote.waterfall * 350

        if quote.splashback:
            total += 300

        if quote.upstands:
            total += 120

        vat = total * 0.20

        return {
            "customer": quote.customer,
            "material": quote.material,
            "slabs": slabs,
            "price_per_slab": base_price,
            "price_before_vat": round(total, 2),
            "vat": round(vat, 2),
            "total": round(total + vat, 2)
        }