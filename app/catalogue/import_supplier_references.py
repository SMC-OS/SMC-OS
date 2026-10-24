"""Controlled, idempotent reference import; never run on application startup.

Names/families/company relationships only. No prices, photos, slab sizes,
stock claims or inferred variants. Y&S is provenance, never a supplier.
Run --dry-run, import explicitly, then --check in each target environment.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogue.seed import _MANUFACTURERS, _BRANDS
from app.database import crud
from app.database.models import CatalogueSupplier, CatalogueManufacturer, CatalogueBrand, CatalogueSurface

VERIFIED_AT = datetime(2026, 10, 22, tzinfo=timezone.utc)
REFERENCES = json.loads(Path(__file__).with_name("supplier_references.json").read_text())


def reference_slug(row: dict) -> str:
    namespace = row.get("supplier") or row.get("manufacturer") or "generic"
    # Match the existing manufacturer's seed identity; preserve its IDs/prices.
    suffix = "-" + row["sku"].lower() if row.get("sku") else ""
    return f"{namespace}-{re.sub(r'[^a-z0-9]+', '-', row['name'].casefold()).strip('-')}{suffix}"


def import_references(db: Session, *, dry_run: bool = False) -> dict:
    existing = set(db.scalars(select(CatalogueSurface.slug).where(CatalogueSurface.tenant_id.is_(None))))
    missing = [row for row in REFERENCES if reference_slug(row) not in existing]
    report = {"reference_materials": len(REFERENCES), "missing_materials": len(missing), "created": 0}
    if dry_run:
        return report
    manufacturers = {}
    brands = {}
    for data in _MANUFACTURERS:
        row = db.scalar(select(CatalogueManufacturer).where(CatalogueManufacturer.slug == data["slug"]))
        if row is None:
            row = CatalogueManufacturer(**data, active=True, source_url=data["website"], source_verified_at=VERIFIED_AT)
            db.add(row); db.flush()
        manufacturers[data["slug"]] = row
    for data in _BRANDS:
        row = db.scalar(select(CatalogueBrand).where(CatalogueBrand.slug == data["slug"]))
        if row is None:
            row = CatalogueBrand(name=data["name"], slug=data["slug"], manufacturer_id=manufacturers[data["manufacturer_slug"]].id, active=True)
            db.add(row); db.flush()
        brands[data["slug"]] = row
    suppliers = {}
    for data in REFERENCES:
        slug = data.get("supplier")
        if slug and slug not in suppliers:
            row = db.scalar(select(CatalogueSupplier).where(CatalogueSupplier.slug == slug))
            if row is None:
                row = CatalogueSupplier(name=data["company"], slug=slug, active=True, source_url=data["source_url"], source_verified_at=VERIFIED_AT)
                db.add(row); db.flush()
            suppliers[slug] = row
    for data in missing:
        db.add(CatalogueSurface(
            tenant_id=None, supplier_id=suppliers[data["supplier"]].id if data.get("supplier") else None,
            manufacturer_id=manufacturers[data["manufacturer"]].id if data.get("manufacturer") else None,
            brand_id=brands[data["brand"]].id if data.get("brand") else None,
            canonical_name=data["name"], slug=reference_slug(data), supplier_sku=data.get("sku"),
            material_family=data["family"], active=True, discontinued=False,
            source_url=data["source_url"], source_name="Public supplier collection reference", source_verified_at=VERIFIED_AT,
        ))
    db.flush()
    report["created"] = len(missing)
    return report


def main(argv=None) -> int:
    from app.core.config import AppEnvironment, settings
    from app.database.database import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    args = parser.parse_args(argv)
    read_only = args.dry_run or args.check
    if settings.app_env == AppEnvironment.PRODUCTION and not read_only and not args.confirm_production:
        parser.error("Production imports require --confirm-production")
    with SessionLocal() as db:
        report = import_references(db, dry_run=read_only)
        if not read_only:
            db.commit()
        print(json.dumps(report))
    return 1 if args.check and report["missing_materials"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
