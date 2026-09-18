import uuid
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.catalogue.service import resolve_price_per_slab
from app.database import crud
from app.materials.service import material_service
from app.quotes.slab_calculator import calculate_slabs
from app.quotes.validator import validate_dimensions


class CataloguePriceMissingError(Exception):
    """Task 8 — raised instead of fabricating a price when a catalogue-
    selected surface has no resolvable tenant price (no selling price,
    no cost+markup, no cost+margin set). Registered in
    app/core/errors.py -> a clear 400, never a silent £0 or a 500."""

    def __init__(self, surface_name: str):
        self.surface_name = surface_name
        super().__init__(
            f"No price is set for '{surface_name}'. Set a buy cost or selling price for this "
            "material in the Catalogue before adding it to a quote."
        )

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

    def calculate(self, db: Session, quote, tenant_id: uuid.UUID | None = None):
        validate_dimensions(quote)

        item_results = []
        price_before_vat = 0.0

        for item in quote.items:
            if getattr(item, "catalogue_surface_id", None) is not None:
                price_per_slab, snapshot = self._resolve_catalogue_item(db, item, tenant_id)
                adapter = SimpleNamespace(slab_size=snapshot["slab_size"])
            else:
                material = material_service.get_by_name_and_thickness(db, item.material, item.thickness)
                if material is None:
                    # Sprint 003's global KeyError -> 400 handler
                    # (app/core/errors.py) already exists for exactly this
                    # "unrecognised value" case, so this reuses that seam
                    # rather than introducing a new one.
                    raise KeyError(f"{item.material} ({item.thickness})")
                price_per_slab = material.price
                adapter = material
                snapshot = None

            slabs = calculate_slabs(item, adapter)
            material_price = price_per_slab * slabs
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
                    "price_per_slab": price_per_slab,
                    "slabs": slabs,
                    "line_total": line_total,
                    "catalogue_surface_id": getattr(item, "catalogue_surface_id", None),
                    "catalogue_variant_id": getattr(item, "catalogue_variant_id", None),
                    "catalogue_snapshot": snapshot,
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

    def _resolve_catalogue_item(self, db: Session, item, tenant_id: uuid.UUID | None) -> tuple[float, dict]:
        """Sprint 042 (Plan 03) — the catalogue-selected path. Builds the
        immutable snapshot at the moment of creation and resolves the
        price from the caller's own tenant_catalogue_overrides row
        (never the free-text `materials` table, never another
        tenant's). Raises CataloguePriceMissingError rather than ever
        fabricating a price (Task 8)."""
        surface = crud.get_catalogue_surface_by_id(db, item.catalogue_surface_id, tenant_id)
        if surface is None:
            raise KeyError(f"catalogue surface {item.catalogue_surface_id}")

        variant = None
        if item.catalogue_variant_id is not None:
            variant = db.get(crud.CatalogueSurfaceVariant, item.catalogue_variant_id)
            if variant is None or variant.surface_id != surface.id:
                raise KeyError(f"catalogue variant {item.catalogue_variant_id}")

        override = None
        if tenant_id is not None:
            override = crud.get_tenant_catalogue_override(
                db, tenant_id, surface.id, item.catalogue_variant_id
            )
        price_per_slab = resolve_price_per_slab(override)
        if price_per_slab is None:
            raise CataloguePriceMissingError(surface.canonical_name)

        supplier = db.get(crud.CatalogueSupplier, surface.supplier_id) if surface.supplier_id else None
        manufacturer = (
            db.get(crud.CatalogueManufacturer, surface.manufacturer_id) if surface.manufacturer_id else None
        )
        brand = db.get(crud.CatalogueBrand, surface.brand_id) if surface.brand_id else None
        collection = db.get(crud.CatalogueCollection, surface.collection_id) if surface.collection_id else None

        slab_size = None
        if variant is not None and variant.slab_length_mm and variant.slab_width_mm:
            slab_size = f"{int(variant.slab_length_mm)}x{int(variant.slab_width_mm)}"

        margin_basis = (
            "selling_price"
            if override.selling_price_per_slab is not None
            else "markup"
            if override.default_markup_percent is not None
            else "margin"
        )

        snapshot = {
            "surface_name": surface.canonical_name,
            "supplier": supplier.name if supplier else None,
            "manufacturer": manufacturer.name if manufacturer else None,
            "brand": brand.name if brand else None,
            "collection": collection.name if collection else None,
            "material_family": surface.material_family,
            "thickness_mm": variant.thickness_mm if variant else None,
            "finish": variant.finish if variant else None,
            "slab_length_mm": variant.slab_length_mm if variant else None,
            "slab_width_mm": variant.slab_width_mm if variant else None,
            "slab_size": slab_size,
            "cost_used": override.buy_cost_per_slab,
            "selling_price_used": price_per_slab,
            "margin_basis": margin_basis,
        }
        return price_per_slab, snapshot
