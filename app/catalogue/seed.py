"""Controlled catalogue seed pipeline (Sprint 042, Task 11/12).

Deliberately NOT wired into application startup (unlike app/materials/
seed.py's old SEED_DATA_ENABLED-guarded auto-seed) — the Master Spec is
explicit that no import pipeline may silently auto-publish to
production. This module is only ever invoked explicitly:

    python -m app.catalogue.seed

It is idempotent (safe to run more than once — every row is looked up
by its own slug before being created) and every surface records real
provenance (`source_name`, `source_verified_at`) rather than pretending
to be first-party data it isn't.

Data policy (the Master Spec's own rule, reproduced here): only public,
factual reference data — supplier/manufacturer/brand/collection/
surface/material-family/thickness/finish/slab-size names. No pricing is
ever seeded (the schema has nowhere to put a global price — see
CatalogueSurface's own docstring), no proprietary descriptions, no
photos, no copied marketing copy. This is a small, representative seed
proving the architecture and UX across multiple material families and
manufacturers — not an attempt to populate the whole industry in one
sprint.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import crud
from app.database.models import CatalogueBrand, CatalogueManufacturer, CatalogueSupplier, CatalogueSurface

_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731

# --- Manufacturers (real, publicly known company names) -------------------

_MANUFACTURERS = [
    {"name": "Cosentino", "slug": "cosentino", "country": "Spain", "website": "https://www.cosentino.com"},
    {"name": "Caesarstone", "slug": "caesarstone", "country": "Israel", "website": "https://www.caesarstone.com"},
    {"name": "Cambria", "slug": "cambria", "country": "United States", "website": "https://www.cambriausa.com"},
    {"name": "TheSize (Neolith)", "slug": "thesize-neolith", "country": "Spain", "website": "https://neolith.com"},
]

# --- Brands (Cosentino's own consumer-facing brand names) ------------------

_BRANDS = [
    {"name": "Silestone", "slug": "silestone", "manufacturer_slug": "cosentino"},
    {"name": "Dekton", "slug": "dekton", "manufacturer_slug": "cosentino"},
]

# --- A UK stone distributor, for provenance/supplier-vs-manufacturer -------

_SUPPLIERS = [
    {"name": "Example UK Stone Distributor", "slug": "example-uk-stone-distributor", "country": "United Kingdom"},
]

# --- Surfaces: (canonical_name, family, manufacturer_slug, brand_slug,
# colour_family, variants: list of (thickness_mm, finish)) -----------------
# Names/families/thicknesses/finishes only — no pricing, no proprietary
# copy, no photos. Representative across families, not exhaustive.

_SURFACES = [
    ("Calacatta Gold", "quartz", "cosentino", "silestone", "white", [(20, "Polished"), (30, "Polished")]),
    ("Eternal Statuario", "quartz", "cosentino", "silestone", "white", [(20, "Polished")]),
    ("Kensho", "quartz", "cosentino", "silestone", "grey", [(20, "Suede")]),
    ("Sirocco", "sintered_stone", "cosentino", "dekton", "grey", [(12, "Matte"), (20, "Matte")]),
    ("Kelya", "sintered_stone", "cosentino", "dekton", "white", [(12, "Matte")]),
    ("Pure White", "quartz", "caesarstone", None, "white", [(20, "Polished"), (30, "Polished")]),
    ("Cosmic Black", "quartz", "caesarstone", None, "black", [(20, "Polished")]),
    ("Brittanicca", "quartz", "cambria", None, "white", [(20, "Polished")]),
    ("Ella", "quartz", "cambria", None, "white", [(30, "Polished")]),
    ("La Minerva", "sintered_stone", "thesize-neolith", None, "white", [(12, "Silk")]),
    ("Nero Marquina", "marble", None, None, "black", [(20, "Polished"), (30, "Honed")]),
    ("Carrara White", "marble", None, None, "white", [(20, "Polished")]),
    ("Absolute Black", "granite", None, None, "black", [(20, "Polished"), (30, "Leathered")]),
    ("Kashmir White", "granite", None, None, "white", [(30, "Polished")]),
    ("Grey Concrete", "porcelain", None, None, "grey", [(12, "Matte")]),
]


def _get_or_create_manufacturer(db: Session, data: dict) -> CatalogueManufacturer:
    existing = db.query(CatalogueManufacturer).filter(CatalogueManufacturer.slug == data["slug"]).first()
    if existing is not None:
        return existing
    return crud.create_catalogue_manufacturer(
        db,
        name=data["name"],
        slug=data["slug"],
        website=data.get("website"),
        country=data.get("country"),
        active=True,
        source_url=data.get("website"),
        source_verified_at=_NOW(),
    )


def _get_or_create_brand(db: Session, data: dict, manufacturer_id) -> CatalogueBrand:
    existing = db.query(CatalogueBrand).filter(CatalogueBrand.slug == data["slug"]).first()
    if existing is not None:
        return existing
    return crud.create_catalogue_brand(
        db, manufacturer_id=manufacturer_id, name=data["name"], slug=data["slug"], website=None, active=True
    )


def _get_or_create_supplier(db: Session, data: dict) -> CatalogueSupplier:
    existing = db.query(CatalogueSupplier).filter(CatalogueSupplier.slug == data["slug"]).first()
    if existing is not None:
        return existing
    return crud.create_catalogue_supplier(
        db,
        name=data["name"],
        slug=data["slug"],
        website=None,
        country=data.get("country"),
        active=True,
        source_url=None,
        source_verified_at=_NOW(),
    )


def seed_catalogue(db: Session) -> dict:
    """Idempotent — looked up by slug, never duplicated on re-run.
    Returns a small summary dict for the caller (the CLI entry point
    below, or a test) to report."""

    manufacturers = {}
    for data in _MANUFACTURERS:
        manufacturers[data["slug"]] = _get_or_create_manufacturer(db, data)

    brands = {}
    for data in _BRANDS:
        brands[data["slug"]] = _get_or_create_brand(db, data, manufacturers[data["manufacturer_slug"]].id)

    for data in _SUPPLIERS:
        _get_or_create_supplier(db, data)

    created_surfaces = 0
    created_variants = 0
    for name, family, mfr_slug, brand_slug, colour, variants in _SURFACES:
        slug = f"{mfr_slug or 'generic'}-{name.lower().replace(' ', '-')}"
        existing = db.query(CatalogueSurface).filter(CatalogueSurface.slug == slug).first()
        if existing is not None:
            surface = existing
        else:
            surface = crud.create_catalogue_surface(
                db,
                tenant_id=None,
                supplier_id=None,
                manufacturer_id=manufacturers[mfr_slug].id if mfr_slug else None,
                brand_id=brands[brand_slug].id if brand_slug else None,
                collection_id=None,
                canonical_name=name,
                slug=slug,
                supplier_sku=None,
                manufacturer_sku=None,
                material_family=family,
                colour_family=colour,
                pattern_family=None,
                origin_country=None,
                active=True,
                discontinued=False,
                source_url=manufacturers[mfr_slug].website if mfr_slug else None,
                source_name="public manufacturer reference",
                source_verified_at=_NOW(),
            )
            created_surfaces += 1

        existing_variants = crud.list_catalogue_surface_variants(db, surface.id)
        existing_keys = {(v.thickness_mm, v.finish) for v in existing_variants}
        for thickness_mm, finish in variants:
            if (float(thickness_mm), finish) in existing_keys:
                continue
            crud.create_catalogue_surface_variant(
                db,
                surface_id=surface.id,
                thickness_mm=float(thickness_mm),
                finish=finish,
                slab_length_mm=3200,
                slab_width_mm=1600,
                supplier_variant_sku=None,
                active=True,
            )
            created_variants += 1

    return {
        "manufacturers": len(manufacturers),
        "brands": len(brands),
        "suppliers": len(_SUPPLIERS),
        "surfaces_created": created_surfaces,
        "surfaces_total": len(_SURFACES),
        "variants_created": created_variants,
    }


if __name__ == "__main__":
    from app.database.database import SessionLocal

    session = SessionLocal()
    try:
        summary = seed_catalogue(session)
        session.commit()
        print(f"Catalogue seed complete: {summary}")
    finally:
        session.close()
