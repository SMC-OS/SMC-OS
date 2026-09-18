"""GeoCore AI's read-only view of the Master Catalogue (Sprint 042, Task
17). AI may search the tenant-authorised catalogue; it never invents
pricing, availability, stock or a supplier relationship. Every result
says explicitly whether a tenant price exists rather than omitting or
guessing one — same "never fabricate" discipline app/materials/
search.py's found/multiple/not_found contract already established in
this codebase.
"""

import uuid

from sqlalchemy.orm import Session

from app.catalogue.service import catalogue_service, resolve_price_per_slab
from app.database import crud


def search_for_ai(db: Session, tenant_id: uuid.UUID, query: str, limit: int = 5) -> list[dict]:
    """Bounded (default 5, same discipline as app/ai/context.py's
    _HEADLINE_LIMIT), tenant-scoped by construction — never another
    tenant's private surfaces or pricing."""
    surfaces = catalogue_service.search(db, tenant_id, query=query, limit=limit)

    results = []
    for surface in surfaces:
        override = crud.get_tenant_catalogue_override(db, tenant_id, surface.id, None)
        price = resolve_price_per_slab(override)
        results.append(
            {
                "surface_id": str(surface.id),
                "canonical_name": surface.canonical_name,
                "material_family": surface.material_family,
                "active": surface.active,
                "discontinued": surface.discontinued,
                # Explicit, never omitted: the AI prompt must never treat
                # a missing key as "no price" vs "price not checked."
                "price_available": price is not None,
                "price_per_slab": price,
            }
        )
    return results
