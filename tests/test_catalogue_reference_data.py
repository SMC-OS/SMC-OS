"""Phase A — the catalogue reference-data release gate, the seed's dry
run and production guard, and the status endpoint that separates an
empty catalogue from a search with no results."""

from sqlalchemy import delete, func, select

from app.catalogue import reference_data, seed
from app.catalogue.reference_data import check_reference_data, expected_counts
from app.core.config import AppEnvironment, settings
from app.database.database import SessionLocal
from app.database.models import (
    CatalogueBrand,
    CatalogueManufacturer,
    CatalogueSupplier,
    CatalogueSurface,
    CatalogueSurfaceVariant,
    TenantCatalogueOverride,
)


def _wipe_global_catalogue():
    """Same reset tests/test_catalogue_seed.py uses — global reference
    rows only, never a tenant-private surface."""
    db = SessionLocal()
    try:
        ids = [r[0] for r in db.query(CatalogueSurface.id).filter(CatalogueSurface.tenant_id.is_(None)).all()]
        if ids:
            db.execute(delete(TenantCatalogueOverride).where(TenantCatalogueOverride.surface_id.in_(ids)))
            db.execute(delete(CatalogueSurfaceVariant).where(CatalogueSurfaceVariant.surface_id.in_(ids)))
            db.execute(delete(CatalogueSurface).where(CatalogueSurface.id.in_(ids)))
        db.execute(delete(CatalogueBrand))
        db.execute(delete(CatalogueManufacturer))
        db.execute(delete(CatalogueSupplier))
        db.commit()
    finally:
        db.close()


def _global_surface_count() -> int:
    db = SessionLocal()
    try:
        return db.scalar(select(func.count(CatalogueSurface.id)).where(CatalogueSurface.tenant_id.is_(None)))
    finally:
        db.close()


def test_expected_counts_match_the_approved_production_remediation():
    """Locks the figures the production remediation was approved
    against. Changing the seed definitions must change this test on
    purpose, never silently."""
    expected = expected_counts()
    assert expected.surfaces == 38
    assert expected.variants == 47
    assert expected.manufacturers == 7
    assert expected.brands == 3
    assert expected.placeholder_suppliers == 0


def test_gate_fails_on_an_empty_catalogue_and_passes_once_seeded():
    _wipe_global_catalogue()
    try:
        db = SessionLocal()
        try:
            empty = check_reference_data(db)
            assert not empty.ok
            assert empty.present == {"manufacturers": 0, "brands": 0, "placeholder_suppliers": 0, "surfaces": 0, "variants": 0}
            assert len(empty.missing_surfaces) == 38
            assert len(empty.missing_variants) == 47

            seed.seed_catalogue(db)
            db.commit()

            full = check_reference_data(db)
            assert full.ok
            assert full.present == {"manufacturers": 7, "brands": 3, "placeholder_suppliers": 0, "surfaces": 38, "variants": 47}
        finally:
            db.close()
    finally:
        _wipe_global_catalogue()


def test_gate_reports_a_single_missing_variant():
    _wipe_global_catalogue()
    try:
        db = SessionLocal()
        try:
            seed.seed_catalogue(db)
            db.commit()
            surface = db.scalars(
                select(CatalogueSurface).where(CatalogueSurface.slug == seed.surface_slug("Calacatta Gold", "cosentino"))
            ).one()
            db.execute(
                delete(CatalogueSurfaceVariant).where(
                    CatalogueSurfaceVariant.surface_id == surface.id, CatalogueSurfaceVariant.thickness_mm == 30
                )
            )
            db.commit()

            report = check_reference_data(db)
            assert not report.ok
            assert report.missing_surfaces == []
            assert report.missing_variants == ["cosentino-calacatta-gold 30mm Polished"]
        finally:
            db.close()
    finally:
        _wipe_global_catalogue()


def test_gate_cli_exit_status_tracks_the_result(capsys):
    _wipe_global_catalogue()
    try:
        assert reference_data.main([]) == 1
        assert "FAIL" in capsys.readouterr().out
        assert _global_surface_count() == 0  # the gate never writes

        assert seed.main([]) == 0
        assert reference_data.main(["--json"]) == 0
        assert '"ok": true' in capsys.readouterr().out
    finally:
        _wipe_global_catalogue()


def test_seed_dry_run_writes_nothing(capsys):
    _wipe_global_catalogue()
    try:
        assert seed.main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "38 surfaces" in out
        assert "+ cosentino-calacatta-gold" in out  # itemised, not just totals
        assert "supplier" not in out.split("FAIL")[1]  # never proposes a supplier
        assert _global_surface_count() == 0
    finally:
        _wipe_global_catalogue()


def test_seed_refuses_production_without_explicit_confirmation(monkeypatch, capsys):
    _wipe_global_catalogue()
    monkeypatch.setattr(settings, "app_env", AppEnvironment.PRODUCTION)
    try:
        assert seed.main([]) == 2
        assert "--confirm-production" in capsys.readouterr().out
        assert _global_surface_count() == 0

        assert seed.main(["--confirm-production"]) == 0
        assert _global_surface_count() == 38
    finally:
        _wipe_global_catalogue()


def test_status_endpoint_separates_empty_catalogue_from_no_results(client, auth_headers):
    _wipe_global_catalogue()
    try:
        empty = client.get("/api/v1/catalogue/meta/status", headers=auth_headers)
        assert empty.status_code == 200, empty.text
        assert empty.json()["global_surfaces"] == 0
        assert empty.json()["reference_data_loaded"] is False

        db = SessionLocal()
        try:
            seed.seed_catalogue(db)
            db.commit()
        finally:
            db.close()

        loaded = client.get("/api/v1/catalogue/meta/status", headers=auth_headers)
        assert loaded.json()["global_surfaces"] == 38
        assert loaded.json()["reference_data_loaded"] is True

        no_match = client.get("/api/v1/catalogue/surfaces?q=zzzz-no-such-surface", headers=auth_headers)
        assert no_match.status_code == 200
        assert no_match.json() == []

        quartz = client.get("/api/v1/catalogue/surfaces?q=white%20quartz&limit=50", headers=auth_headers)
        names = {s["canonical_name"] for s in quartz.json()}
        assert "Calacatta Gold" in names
        assert all(s["material_family"] == "quartz" and s["colour_family"] == "white" for s in quartz.json())
    finally:
        _wipe_global_catalogue()


def test_status_endpoint_requires_authentication(client):
    assert client.get("/api/v1/catalogue/meta/status").status_code == 401


def test_seed_never_creates_a_supplier():
    """The approved production dataset contains zero suppliers — the two
    former placeholder distributors must never be inserted."""
    _wipe_global_catalogue()
    try:
        db = SessionLocal()
        try:
            summary = seed.seed_catalogue(db)
            db.commit()
            assert "suppliers" not in summary
            assert db.scalar(select(func.count(CatalogueSupplier.id))) == 0
            names = {s.name for s in db.scalars(select(CatalogueSupplier))}
            assert not any(name.startswith("Example") for name in names)
            assert all(
                surface.supplier_id is None
                for surface in db.scalars(select(CatalogueSurface).where(CatalogueSurface.tenant_id.is_(None)))
            )
        finally:
            db.close()
    finally:
        _wipe_global_catalogue()


def test_gate_fails_when_a_placeholder_supplier_exists_and_never_deletes_it():
    _wipe_global_catalogue()
    try:
        db = SessionLocal()
        try:
            seed.seed_catalogue(db)
            db.add(
                CatalogueSupplier(
                    name="Example UK Stone Distributor", slug="example-uk-stone-distributor", active=True
                )
            )
            db.commit()

            report = check_reference_data(db)
            assert not report.ok
            assert report.missing_surfaces == []
            assert report.placeholder_suppliers_present == ["example-uk-stone-distributor"]
            assert "placeholder suppliers are present" in reference_data.format_report(report)
            # Reported only: the gate is read-only.
            assert db.scalar(select(func.count(CatalogueSupplier.id))) == 1
        finally:
            db.close()
    finally:
        _wipe_global_catalogue()


def test_supplier_filter_still_works_with_zero_seeded_suppliers(client, auth_headers):
    """With the seed contributing no suppliers, supplier search must still
    work for a supplier a tenant actually configures as preferred."""
    import uuid as _uuid

    from app.database import crud

    _wipe_global_catalogue()
    db = SessionLocal()
    try:
        seed.seed_catalogue(db)
        db.commit()
        me = client.get("/api/v1/auth/me", headers=auth_headers).json()
        tenant_id = _uuid.UUID(me["tenant_id"])
        supplier = crud.create_catalogue_supplier(
            db, name="Tenant Real Merchant Pytest", slug=f"tenant-merchant-{_uuid.uuid4().hex[:8]}", active=True
        )
        surface = db.scalars(
            select(CatalogueSurface).where(CatalogueSurface.slug == seed.surface_slug("Absolute Black", None))
        ).one()
        crud.upsert_tenant_catalogue_override(
            db, tenant_id=tenant_id, surface_id=surface.id, surface_variant_id=None, preferred_supplier_id=supplier.id
        )

        by_filter = client.get(f"/api/v1/catalogue/surfaces?supplier_id={supplier.id}", headers=auth_headers).json()
        assert [s["canonical_name"] for s in by_filter] == ["Absolute Black"]
        by_text = client.get("/api/v1/catalogue/surfaces?q=Tenant%20Real%20Merchant", headers=auth_headers).json()
        assert [s["canonical_name"] for s in by_text] == ["Absolute Black"]
    finally:
        db.close()
        _wipe_global_catalogue()
