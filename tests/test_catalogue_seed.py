"""Task 11/12 — the controlled catalogue seed pipeline is idempotent,
records provenance, and never seeds a global price (the schema has
nowhere to put one)."""

from sqlalchemy import delete

from app.catalogue.seed import seed_catalogue
from app.database.database import SessionLocal
from app.database.models import (
    CatalogueBrand,
    CatalogueManufacturer,
    CatalogueSupplier,
    CatalogueSurface,
    CatalogueSurfaceVariant,
    TenantCatalogueOverride,
)


def _cleanup():
    db = SessionLocal()
    try:
        surface_ids = [row[0] for row in db.query(CatalogueSurface.id).filter(CatalogueSurface.tenant_id.is_(None)).all()]
        if surface_ids:
            db.execute(delete(TenantCatalogueOverride).where(TenantCatalogueOverride.surface_id.in_(surface_ids)))
            db.execute(delete(CatalogueSurfaceVariant).where(CatalogueSurfaceVariant.surface_id.in_(surface_ids)))
            db.execute(delete(CatalogueSurface).where(CatalogueSurface.id.in_(surface_ids)))
        db.execute(delete(CatalogueBrand))
        db.execute(delete(CatalogueManufacturer))
        db.execute(delete(CatalogueSupplier))
        db.commit()
    finally:
        db.close()


def test_seed_catalogue_is_idempotent_and_never_seeds_a_price():
    db = SessionLocal()
    try:
        _cleanup()
        first = seed_catalogue(db)
        db.commit()
        assert first["surfaces_created"] > 0
        assert first["manufacturers"] > 0

        surfaces_after_first = db.query(CatalogueSurface).filter(CatalogueSurface.tenant_id.is_(None)).count()

        second = seed_catalogue(db)
        db.commit()
        assert second["surfaces_created"] == 0  # nothing new — already seeded
        assert second["variants_created"] == 0

        surfaces_after_second = db.query(CatalogueSurface).filter(CatalogueSurface.tenant_id.is_(None)).count()
        assert surfaces_after_first == surfaces_after_second

        for surface in db.query(CatalogueSurface).filter(CatalogueSurface.tenant_id.is_(None)).all():
            assert surface.source_name is not None
            assert surface.source_verified_at is not None
    finally:
        _cleanup()
        db.close()
