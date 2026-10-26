import uuid
import json
import math
from decimal import Decimal, ROUND_DOWN
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.catalogue.service import resolve_price_per_slab
from app.database import crud
from app.materials.service import material_service
from app.quotes.slab_calculator import calculate_slabs, _parse_slab_size, WASTAGE_FACTOR
from app.quotes.validator import validate_dimensions, DimensionError


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
        "slabs": None if any(i["slabs"] is None for i in item_results) else sum(i["slabs"] for i in item_results),
    }


class QuoteCalculator:

    def calculate(self, db: Session, quote, tenant_id: uuid.UUID | None = None):
        validate_dimensions(quote)

        item_results = []
        slab_groups = {}
        price_before_vat = 0.0

        for item in quote.items:
            unpriced = bool(getattr(quote, "allow_unpriced", False) and tenant_id is not None)
            custom = getattr(item, "custom_material", None)
            if custom is not None:
                if tenant_id is None:
                    raise KeyError("Quote-only custom materials require an authenticated workspace")
                price_per_slab = resolve_price_per_slab(SimpleNamespace(
                    selling_price_per_slab=custom.selling_price_per_slab,
                    buy_cost_per_slab=custom.buy_cost_per_slab,
                    default_markup_percent=custom.default_markup_percent,
                    target_margin_percent=None,
                ))
                if price_per_slab is None and not unpriced:
                    raise CataloguePriceMissingError(custom.canonical_name)
                variant = custom.variant
                slab_size = f"{variant.slab_length_mm:g}x{variant.slab_width_mm:g}" if variant.slab_length_mm and variant.slab_width_mm else None
                adapter = SimpleNamespace(slab_size=slab_size)
                snapshot = {
                    "source": "quote_custom", "canonical_name": custom.canonical_name,
                    "supplier_name": custom.supplier_name, "manufacturer_name": custom.manufacturer_name,
                    "material_family": custom.material_family, "thickness_mm": variant.thickness_mm,
                    "finish": variant.finish, "slab_size": slab_size,
                    "buy_cost_per_slab": custom.buy_cost_per_slab,
                    "selling_price_per_slab": price_per_slab,
                    "default_markup_percent": custom.default_markup_percent,
                }
            elif getattr(item, "catalogue_surface_id", None) is not None:
                try:
                    price_per_slab, snapshot = self._resolve_catalogue_item(db, item, tenant_id)
                except CataloguePriceMissingError:
                    if not unpriced:
                        raise
                    price_per_slab, snapshot = None, {"source": "catalogue", "pricing_pending": True}
                adapter = SimpleNamespace(slab_size=snapshot.get("slab_size"))
            else:
                material = material_service.get_by_name_and_thickness(db, item.material, item.thickness)
                if material is None and not unpriced:
                    # Sprint 003's global KeyError -> 400 handler
                    # (app/core/errors.py) already exists for exactly this
                    # "unrecognised value" case, so this reuses that seam
                    # rather than introducing a new one.
                    raise KeyError(f"{item.material} ({item.thickness})")
                price_per_slab = material.price if material is not None else None
                adapter = material or SimpleNamespace(slab_size=None)
                snapshot = None

            slabs = calculate_slabs(item, adapter) if price_per_slab is not None else None
            material_price = price_per_slab * slabs if price_per_slab is not None else None
            surcharge = _ITEM_TYPE_SURCHARGES.get(item.item_type, 0) * item.quantity
            line_total = round(material_price + surcharge, 2) if material_price is not None else None

            group = getattr(item, "slab_group", None)
            if group and price_per_slab is not None:
                signature = (item.material.strip().casefold(), item.thickness, str(getattr(item, "catalogue_surface_id", None)), str(getattr(item, "catalogue_variant_id", None)), price_per_slab, json.dumps(snapshot, sort_keys=True), adapter.slab_size)
                slab_groups.setdefault(group, []).append((len(item_results), item, signature))

            item_results.append(
                {
                    "item_type": item.item_type,
                    "material": custom.canonical_name if custom is not None else item.material,
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
                    "catalogue_snapshot": {**(snapshot or {}), "pricing_pending": True} if price_per_slab is None else snapshot,
                }
            )

        # Pool only explicitly grouped, identically resolved materials. This is an
        # area-and-waste estimate, not a cutting/nesting or grain-matching promise.
        for group, entries in slab_groups.items():
            if any(entry[2] != entries[0][2] for entry in entries[1:]):
                raise DimensionError("Shared slab pieces must use the same material, thickness, variant and price.")
            slab_length, slab_width = _parse_slab_size(entries[0][2][-1])
            areas = [entry[1].length_mm * entry[1].width_mm * entry[1].quantity / 1_000_000 for entry in entries]
            total_area = sum(areas)
            shared_slabs = max(1, math.ceil(total_area * WASTAGE_FACTOR / (slab_length * slab_width)))
            price = entries[0][2][4]
            total_pence = int(round(price * shared_slabs * 100))
            allocated_pence = 0
            for offset, (index, item, _) in enumerate(entries):
                # Allocate whole pennies and put the rounding remainder on the last
                # line so displayed line totals always reconcile to the quote total.
                pence = total_pence - allocated_pence if offset == len(entries) - 1 else int((Decimal(total_pence) * Decimal(str(areas[offset])) / Decimal(str(total_area))).quantize(Decimal("1"), rounding=ROUND_DOWN))
                allocated_pence += pence
                row = item_results[index]
                row["slabs"] = shared_slabs if offset == 0 else 0
                row["line_total"] = round(pence / 100 + _ITEM_TYPE_SURCHARGES.get(item.item_type, 0) * item.quantity, 2)
                allocation = {"group": group, "group_slabs": shared_slabs, "method": "area_with_15_percent_waste", "material_allocation": pence / 100}
                row["slab_allocation"] = allocation
                row["catalogue_snapshot"] = {**(row["catalogue_snapshot"] or {}), "slab_allocation": allocation}

        pricing_pending = any(row["line_total"] is None for row in item_results)
        price_before_vat = None if pricing_pending else round(sum(row["line_total"] for row in item_results), 2)
        vat = None if pricing_pending else round(price_before_vat * 0.20, 2)
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
            "total": None if pricing_pending else round(price_before_vat + vat, 2),
            "pricing_pending": pricing_pending,
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
            # A tenant commonly prices a surface once, not per variant
            # (TenantCatalogueOverride.surface_variant_id=None — see its
            # own docstring, and app/catalogue/service.py's
            # create_custom_material, which always writes at surface
            # level). A quote against a specific variant still finds
            # that price rather than treating it as unset.
            if override is None and item.catalogue_variant_id is not None:
                override = crud.get_tenant_catalogue_override(db, tenant_id, surface.id, None)
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
