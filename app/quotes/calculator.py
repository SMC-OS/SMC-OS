from sqlalchemy.orm import Session

from app.materials.service import material_service
from app.quotes.slab_calculator import SlabCalculator
from app.quotes.validator import validate_dimensions


class QuoteCalculator:

    def calculate(self, db: Session, quote):
        validate_dimensions(quote)

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
            "total": round(total + vat, 2),
            # Interpreted dimensions echoed back verbatim — the caller
            # (manual form or AI draft flow) must be able to show these to
            # the user before/at quote creation (Sprint 032, Workstream C).
            "dimensions": {
                "quantity": quote.quantity,
                "length_mm": quote.length_mm,
                "width_mm": quote.width_mm,
                "thickness_mm": quote.thickness_mm,
                "unit_input": quote.unit_input,
                "splashback_length_mm": quote.splashback_length_mm,
                "upstands_length_mm": quote.upstands_length_mm,
            },
        }
