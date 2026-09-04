from sqlalchemy.orm import Session

from app.materials.service import material_service
from app.quotes.slab_calculator import calculate_slabs
from app.quotes.validator import validate_dimensions

# Sprint 033 — small flat installation surcharges preserved from Sprint
# 032's per-quote flags, now applied per matching item instead (island/
# waterfall_panel/splashback/upstand each carried one in the old single-
# job model; worktop/sill/other never did). Multiplied by the item's own
# quantity — each physical unit gets its own install fee.
_ITEM_TYPE_SURCHARGES = {
    "island": 450,
    "waterfall_panel": 350,
    "splashback": 300,
    "upstand": 120,
}


def summarize_items(item_results: list[dict]) -> dict:
    """Best-effort single-item summary of a multi-item quote — used both
    for the API response's top-level fields (backward compatible with
    every pre-Sprint-033 caller that only ever knew one material per
    quote) and for the Quote row's own summary columns (see
    app/quotes/service.py). `items` itself is always the source of truth.
    """
    if not item_results:
        return {"material": None, "thickness": None, "price_per_slab": None, "slabs": 0}

    first = item_results[0]
    same_material = all(
        (i["material"], i["thickness"]) == (first["material"], first["thickness"])
        for i in item_results
    )

    return {
        "material": first["material"] if same_material else "Multiple materials",
        "thickness": first["thickness"] if same_material else "Mixed",
        "price_per_slab": first["price_per_slab"] if same_material else None,
        "slabs": sum(i["slabs"] for i in item_results),
    }


class QuoteCalculator:

    def calculate(self, db: Session, quote):
        validate_dimensions(quote)

        item_results = []
        price_before_vat = 0.0

        for item in quote.items:
            material = material_service.get_by_name_and_thickness(db, item.material, item.thickness)
            if material is None:
                # Sprint 003's global KeyError -> 400 handler (app/core/errors.py)
                # already exists for exactly this "unrecognised value" case, so
                # this reuses that seam rather than introducing a new one.
                raise KeyError(f"{item.material} ({item.thickness})")

            slabs = calculate_slabs(item, material)
            material_price = material.price * slabs
            surcharge = _ITEM_TYPE_SURCHARGES.get(item.item_type, 0) * item.quantity
            line_total = round(material_price + surcharge, 2)
            price_before_vat += line_total

            item_results.append(
                {
                    "item_type": item.item_type,
                    "material": item.material,
                    "thickness": item.thickness,
                    "quantity": item.quantity,
                    "length_mm": item.length_mm,
                    "width_mm": item.width_mm,
                    "thickness_mm": item.thickness_mm,
                    "unit_input": item.unit_input,
                    "notes": item.notes,
                    "price_per_slab": material.price,
                    "slabs": slabs,
                    "line_total": line_total,
                }
            )

        price_before_vat = round(price_before_vat, 2)
        vat = round(price_before_vat * 0.20, 2)
        summary = summarize_items(item_results)

        return {
            "customer": quote.customer,
            "material": summary["material"],
            "thickness": summary["thickness"],
            "price_per_slab": summary["price_per_slab"],
            "slabs": summary["slabs"],
            "items": item_results,
            "price_before_vat": price_before_vat,
            "vat": vat,
            "total": round(price_before_vat + vat, 2),
        }
