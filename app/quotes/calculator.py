from sqlalchemy.orm import Session

from app.materials.service import material_service
from app.quotes.slab_calculator import SlabCalculator


class QuoteCalculator:

    def calculate(self, db: Session, quote):

        material = material_service.get_by_name_and_thickness(
            db, quote.material, quote.thickness
        )
        if material is None:
            # Sprint 003's global KeyError -> 400 handler (app/core/errors.py)
            # already exists for exactly this "unrecognised value" case, so
            # this reuses that seam rather than introducing a new one.
            raise KeyError(f"{quote.material} ({quote.thickness})")

        base_price = material.price

        slabs = SlabCalculator().calculate(quote, material)

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
