"""Controlled catalogue seed pipeline (Sprint 042, Task 11/12).

Deliberately NOT wired into application startup (unlike app/materials/
seed.py's old SEED_DATA_ENABLED-guarded auto-seed) — the Master Spec is
explicit that no import pipeline may silently auto-publish to
production. This module is only ever invoked explicitly:

    python -m app.catalogue.seed --dry-run    # writes nothing
    python -m app.catalogue.seed              # dev / staging
    python -m app.catalogue.seed --confirm-production

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
from app.database.models import CatalogueBrand, CatalogueManufacturer, CatalogueSurface

_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731

# --- Manufacturers (real, publicly known company names) -------------------

_MANUFACTURERS = [
    {"name": "Cosentino", "slug": "cosentino", "country": "Spain", "website": "https://www.cosentino.com"},
    {"name": "Caesarstone", "slug": "caesarstone", "country": "Israel", "website": "https://www.caesarstone.com"},
    {"name": "Cambria", "slug": "cambria", "country": "United States", "website": "https://www.cambriausa.com"},
    {"name": "TheSize (Neolith)", "slug": "thesize-neolith", "country": "Spain", "website": "https://neolith.com"},
    {"name": "LX Hausys", "slug": "lx-hausys", "country": "South Korea", "website": "https://www.lxhausys.com"},
    {"name": "Technistone", "slug": "technistone", "country": "Czech Republic", "website": "https://www.technistone.com"},
    {"name": "Laminam", "slug": "laminam", "country": "Italy", "website": "https://www.laminam.com"},
]

# --- Brands (each manufacturer's own consumer-facing brand names) ----------

_BRANDS = [
    {"name": "Silestone", "slug": "silestone", "manufacturer_slug": "cosentino"},
    {"name": "Dekton", "slug": "dekton", "manufacturer_slug": "cosentino"},
    {"name": "Viatera", "slug": "viatera", "manufacturer_slug": "lx-hausys"},
]

# --- Suppliers: deliberately none ----------------------------------------
# Earlier versions seeded two clearly-labelled placeholder distributors
# ("Example UK Stone Distributor", "Example European Stone Importer").
# No seeded surface ever referenced them, and a placeholder company must
# never appear in a real workspace's supplier lists, so the approved
# production reference dataset contains zero suppliers. Suppliers are
# real businesses a tenant works with: they come from the tenant's own
# data (custom materials, preferred suppliers, procurement), never from
# this seed. app/catalogue/reference_data.py fails the release gate if
# either placeholder slug is ever present.

PLACEHOLDER_SUPPLIER_SLUGS = ("example-uk-stone-distributor", "example-european-stone-importer")

# --- Surfaces: (canonical_name, family, manufacturer_slug, brand_slug,
# colour_family, variants: list of (thickness_mm, finish)) -----------------
# Names/families/thicknesses/finishes only — no pricing, no proprietary
# copy, no photos. Representative across families, not exhaustive.

_SURFACES = [
    # Post-release remediation §3 expanded this from 15 to 38 surfaces
    # across 3 more manufacturers and 1 more brand — a modest, still-
    # representative expansion, deliberately not chasing an unverified
    # "~96" figure that appears nowhere in this codebase's history.
    ("Calacatta Gold", "quartz", "cosentino", "silestone", "white", [(20, "Polished"), (30, "Polished")]),
    ("Eternal Statuario", "quartz", "cosentino", "silestone", "white", [(20, "Polished")]),
    ("Kensho", "quartz", "cosentino", "silestone", "grey", [(20, "Suede")]),
    ("Eternal Marquina", "quartz", "cosentino", "silestone", "black", [(20, "Polished")]),
    ("Pietra Grey", "quartz", "cosentino", "silestone", "grey", [(20, "Polished"), (30, "Polished")]),
    ("Arctic Fantasy", "quartz", "cosentino", "silestone", "white", [(20, "Suede")]),
    ("Sirocco", "sintered_stone", "cosentino", "dekton", "grey", [(12, "Matte"), (20, "Matte")]),
    ("Kelya", "sintered_stone", "cosentino", "dekton", "white", [(12, "Matte")]),
    ("Trilium", "sintered_stone", "cosentino", "dekton", "grey", [(12, "Matte")]),
    ("Laurent", "sintered_stone", "cosentino", "dekton", "white", [(20, "Polished")]),
    ("Pure White", "quartz", "caesarstone", None, "white", [(20, "Polished"), (30, "Polished")]),
    ("Cosmic Black", "quartz", "caesarstone", None, "black", [(20, "Polished")]),
    ("London Grey", "quartz", "caesarstone", None, "grey", [(20, "Polished")]),
    ("Vanilla Noir", "quartz", "caesarstone", None, "black", [(20, "Polished"), (30, "Polished")]),
    ("Frosty Carrina", "quartz", "caesarstone", None, "white", [(20, "Polished")]),
    ("Brittanicca", "quartz", "cambria", None, "white", [(20, "Polished")]),
    ("Ella", "quartz", "cambria", None, "white", [(30, "Polished")]),
    ("Torquay", "quartz", "cambria", None, "white", [(30, "Polished")]),
    ("Berwyn", "quartz", "cambria", None, "grey", [(20, "Polished")]),
    ("La Minerva", "sintered_stone", "thesize-neolith", None, "white", [(12, "Silk")]),
    ("Calacatta", "sintered_stone", "thesize-neolith", None, "white", [(12, "Polished"), (20, "Polished")]),
    ("Iron Moss", "sintered_stone", "thesize-neolith", None, "grey", [(12, "Silk")]),
    ("Basalt Grey", "sintered_stone", "thesize-neolith", None, "grey", [(20, "Matte")]),
    ("Minuet", "quartz", "lx-hausys", "viatera", "white", [(20, "Polished")]),
    ("Rolling Fog", "quartz", "lx-hausys", "viatera", "grey", [(20, "Polished")]),
    ("Pebble Beach", "quartz", "lx-hausys", "viatera", "beige", [(30, "Polished")]),
    ("Crystal Snow", "quartz", "technistone", None, "white", [(20, "Polished")]),
    ("Starlight", "quartz", "technistone", None, "black", [(20, "Polished")]),
    ("Nero Marquina", "marble", None, None, "black", [(20, "Polished"), (30, "Honed")]),
    ("Carrara White", "marble", None, None, "white", [(20, "Polished")]),
    ("Emperador Dark", "marble", None, None, "brown", [(20, "Polished")]),
    ("Bianco Statuario", "marble", None, None, "white", [(20, "Polished"), (30, "Honed")]),
    ("Absolute Black", "granite", None, None, "black", [(20, "Polished"), (30, "Leathered")]),
    ("Kashmir White", "granite", None, None, "white", [(30, "Polished")]),
    ("Steel Grey", "granite", None, None, "grey", [(30, "Flamed")]),
    ("Tan Brown", "granite", None, None, "brown", [(30, "Polished")]),
    ("Grey Concrete", "porcelain", None, None, "grey", [(12, "Matte")]),
    ("Basalt Black", "porcelain", None, None, "black", [(12, "Matte")]),
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


def surface_slug(canonical_name: str, manufacturer_slug: str | None) -> str:
    """The one slug rule for a seeded global surface. Shared with
    app/catalogue/reference_data.py so the release gate checks exactly
    the rows this seed creates, never a re-derived copy of the rule."""
    return f"{manufacturer_slug or 'generic'}-{canonical_name.lower().replace(' ', '-')}"


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

    created_surfaces = 0
    created_variants = 0
    for name, family, mfr_slug, brand_slug, colour, variants in _SURFACES:
        slug = surface_slug(name, mfr_slug)
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
        "surfaces_created": created_surfaces,
        "surfaces_total": len(_SURFACES),
        "variants_created": created_variants,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Phase A adds two safety rails:

    --dry-run              writes nothing; prints what the seed would
                           create (the read-only reference-data gate's
                           own "missing" report — exact, because the
                           seed is idempotent by slug).
    --confirm-production   required, in addition to running the command
                           at all, before this writes to a database
                           whose APP_ENV is production.

    After a real run it re-checks the gate and fails loudly if any
    expected row is still missing."""
    import argparse

    from app.catalogue.reference_data import check_reference_data, format_report
    from app.core.config import AppEnvironment, settings
    from app.database.database import SessionLocal

    parser = argparse.ArgumentParser(description="Seed global catalogue reference data (idempotent).")
    parser.add_argument("--dry-run", action="store_true", help="write nothing; report what would be created")
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="required to write when APP_ENV is production",
    )
    args = parser.parse_args(argv)

    session = SessionLocal()
    try:
        if args.dry_run:
            print("DRY RUN — nothing will be written.")
            print(format_report(check_reference_data(session), itemised=True))
            session.rollback()
            return 0

        if settings.app_env is AppEnvironment.PRODUCTION and not args.confirm_production:
            print(
                "Refusing to write catalogue reference data to production without "
                "--confirm-production. Run with --dry-run first."
            )
            return 2

        summary = seed_catalogue(session)
        session.commit()
        print(f"Catalogue seed complete: {summary}")

        report = check_reference_data(session)
        print(format_report(report))
        return 0 if report.ok else 1
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    sys.exit(main())
