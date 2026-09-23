"""Global catalogue reference-data release gate (Phase A — catalogue
remediation).

Production shipped the catalogue feature without its reference data:
app/catalogue/seed.py is deliberately never run at startup, and nothing
in the release process noticed it had never been run. This module is the
missing check. It compares the database against the seed's own
definitions — the same lists and the same slug rule — and reports what
is present and what is missing.

Placeholder suppliers are the one thing the gate requires to be *absent*:
the approved dataset contains none (see seed.PLACEHOLDER_SUPPLIER_SLUGS).

It is strictly read-only: it only ever SELECTs, and the CLI never
commits. That makes it safe to run against production at any time, and
it doubles as the seed's dry run, because the seed is idempotent by slug
and creates exactly the rows reported missing here.

    python -m app.catalogue.reference_data           # human-readable report
    python -m app.catalogue.reference_data --json    # machine-readable report

Exit status is 0 when every expected row is present and 1 otherwise, so a
release pipeline can gate on it directly.
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogue.seed import _BRANDS, _MANUFACTURERS, _SURFACES, PLACEHOLDER_SUPPLIER_SLUGS, surface_slug
from app.database.models import (
    CatalogueBrand,
    CatalogueManufacturer,
    CatalogueSupplier,
    CatalogueSurface,
    CatalogueSurfaceVariant,
)


@dataclass(frozen=True)
class ExpectedReferenceData:
    manufacturers: int
    brands: int
    surfaces: int
    variants: int
    # The approved dataset holds no suppliers at all; this is the number
    # of placeholder supplier rows allowed to exist, which is always 0.
    placeholder_suppliers: int = 0


def expected_counts() -> ExpectedReferenceData:
    """What a fully seeded database holds, derived from the seed
    definitions themselves — never a separately maintained number."""
    return ExpectedReferenceData(
        manufacturers=len(_MANUFACTURERS),
        brands=len(_BRANDS),
        surfaces=len(_SURFACES),
        variants=sum(len(variants) for *_, variants in _SURFACES),
    )


@dataclass
class ReferenceDataReport:
    expected: ExpectedReferenceData
    present: dict[str, int]
    missing_manufacturers: list[str] = field(default_factory=list)
    missing_brands: list[str] = field(default_factory=list)
    # Placeholder suppliers that must NOT exist but do. Reported, never
    # deleted automatically: removing production rows is a separate,
    # explicitly approved operation.
    placeholder_suppliers_present: list[str] = field(default_factory=list)
    missing_surfaces: list[str] = field(default_factory=list)
    missing_variants: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.missing_manufacturers
            or self.missing_brands
            or self.placeholder_suppliers_present
            or self.missing_surfaces
            or self.missing_variants
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["ok"] = self.ok
        return data


def _existing_slugs(db: Session, model, slugs: list[str]) -> set[str]:
    if not slugs:
        return set()
    return set(db.scalars(select(model.slug).where(model.slug.in_(slugs))))


def check_reference_data(db: Session) -> ReferenceDataReport:
    """Read-only comparison of the database against the seed
    definitions. Only global rows count (tenant_id IS NULL for
    surfaces): a tenant's private material never satisfies the gate."""
    manufacturer_slugs = [m["slug"] for m in _MANUFACTURERS]
    brand_slugs = [b["slug"] for b in _BRANDS]

    present_manufacturers = _existing_slugs(db, CatalogueManufacturer, manufacturer_slugs)
    present_brands = _existing_slugs(db, CatalogueBrand, brand_slugs)
    placeholder_suppliers = _existing_slugs(db, CatalogueSupplier, list(PLACEHOLDER_SUPPLIER_SLUGS))

    surface_slugs = {surface_slug(name, mfr): (name, variants) for name, _, mfr, _, _, variants in _SURFACES}
    surfaces_by_slug = {
        row.slug: row
        for row in db.scalars(
            select(CatalogueSurface).where(
                CatalogueSurface.slug.in_(list(surface_slugs)),
                CatalogueSurface.tenant_id.is_(None),
            )
        )
    }

    variant_keys_by_surface: dict = {}
    if surfaces_by_slug:
        for variant in db.scalars(
            select(CatalogueSurfaceVariant).where(
                CatalogueSurfaceVariant.surface_id.in_([s.id for s in surfaces_by_slug.values()])
            )
        ):
            variant_keys_by_surface.setdefault(variant.surface_id, set()).add(
                (float(variant.thickness_mm) if variant.thickness_mm is not None else None, variant.finish)
            )

    missing_surfaces: list[str] = []
    missing_variants: list[str] = []
    present_variant_count = 0
    for slug, (name, variants) in surface_slugs.items():
        surface = surfaces_by_slug.get(slug)
        if surface is None:
            missing_surfaces.append(slug)
            missing_variants.extend(f"{slug} {t}mm {finish}" for t, finish in variants)
            continue
        existing = variant_keys_by_surface.get(surface.id, set())
        for thickness_mm, finish in variants:
            if (float(thickness_mm), finish) in existing:
                present_variant_count += 1
            else:
                missing_variants.append(f"{slug} {thickness_mm}mm {finish}")

    return ReferenceDataReport(
        expected=expected_counts(),
        present={
            "manufacturers": len(present_manufacturers),
            "brands": len(present_brands),
            "placeholder_suppliers": len(placeholder_suppliers),
            "surfaces": len(surfaces_by_slug),
            "variants": present_variant_count,
        },
        missing_manufacturers=sorted(set(manufacturer_slugs) - present_manufacturers),
        missing_brands=sorted(set(brand_slugs) - present_brands),
        placeholder_suppliers_present=sorted(placeholder_suppliers),
        missing_surfaces=sorted(missing_surfaces),
        missing_variants=sorted(missing_variants),
    )


def format_report(report: ReferenceDataReport, *, itemised: bool = False) -> str:
    """Human-readable report. `itemised=True` (the seed's dry run) also
    lists every individual row the seed would insert, by slug."""
    expected = asdict(report.expected)
    lines = ["Catalogue reference data", ""]
    for key in ("manufacturers", "brands", "surfaces", "variants", "placeholder_suppliers"):
        lines.append(f"  {key:<22} {report.present[key]:>3} / {expected[key]}")
    lines.append("")
    if report.ok:
        lines.append("PASS — every expected reference row is present and no placeholder supplier exists.")
    else:
        missing = {
            "manufacturers": report.missing_manufacturers,
            "brands": report.missing_brands,
            "surfaces": report.missing_surfaces,
            "variants": report.missing_variants,
        }
        if any(missing.values()):
            lines.append("FAIL — the seed would create:")
            for key, values in missing.items():
                if values:
                    lines.append(f"  {len(values)} {key}")
                    if itemised:
                        lines.extend(f"      + {value}" for value in values)
        if report.placeholder_suppliers_present:
            lines.append(
                "FAIL — placeholder suppliers are present and must be removed by a separately "
                "approved operation (the seed never deletes): "
                + ", ".join(report.placeholder_suppliers_present)
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only catalogue reference-data release gate.")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)

    from app.database.database import SessionLocal

    session = SessionLocal()
    try:
        report = check_reference_data(session)
    finally:
        # Never commit: this gate must be incapable of changing data.
        session.rollback()
        session.close()

    print(json.dumps(report.to_dict(), indent=2) if args.json else format_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
