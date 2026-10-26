import pytest
from sqlalchemy import select, func
from app.catalogue.import_supplier_references import REFERENCES, reference_slug, import_references
from app.catalogue.models import MATERIAL_FAMILIES
from app.database.models import CatalogueSurface, CatalogueSurfaceVariant, CatalogueSupplier, TenantCatalogueOverride


def test_supplier_dataset_is_unique_sourced_and_has_no_invented_commercial_data():
    assert len(REFERENCES) >= 570
    assert len({reference_slug(row) for row in REFERENCES}) == len(REFERENCES)
    assert {"quartz", "granite", "marble", "onyx", "sintered_stone"} <= {r["family"] for r in REFERENCES}
    for row in REFERENCES:
        assert row["source_url"].startswith("https://")
        assert row["family"] in MATERIAL_FAMILIES
        assert set(row) <= {"name", "family", "company", "supplier", "manufacturer", "brand", "source_url", "sku"}
        assert row.get("supplier") not in {"yands", "yands-marble", "wns-marble"}
    assert any("Carrara" in row["name"] for row in REFERENCES if row.get("supplier") == "noblestone")


def test_reference_import_is_atomic_idempotent_and_never_creates_prices_or_variants(db):
    # Roll back our entire import: do not disturb other tests' global data.
    try:
        before = (db.scalar(select(func.count()).select_from(CatalogueSurfaceVariant)), db.scalar(select(func.count()).select_from(TenantCatalogueOverride)))
        first = import_references(db)
        second = import_references(db)
        assert second["created"] == 0
        assert import_references(db, dry_run=True)["missing_materials"] == 0
        slugs = [reference_slug(row) for row in REFERENCES]
        imported = list(db.scalars(select(CatalogueSurface).where(CatalogueSurface.slug.in_(slugs))))
        assert len(imported) == len(REFERENCES)
        assert all(row.source_url and row.source_verified_at for row in imported)
        # Import does not commit: the caller controls publication as one transaction.
        assert db.in_transaction()
        assert before == (db.scalar(select(func.count()).select_from(CatalogueSurfaceVariant)), db.scalar(select(func.count()).select_from(TenantCatalogueOverride)))
    finally:
        db.rollback()
