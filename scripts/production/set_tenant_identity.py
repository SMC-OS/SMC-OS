"""Sprint 034 — set a tenant's customer-facing company identity from the CLI.

The Settings → Company Identity screen is the normal way to do this; an
Owner fills the form and is done. This script exists for the one case that
screen cannot cover: configuring an operating tenant *before* anyone has
logged in to correct it, immediately after the Sprint 034 deploy, so no
customer ever downloads an invoice with the wrong (or a missing)
letterhead.

Design constraints, matching scripts/production/cleanup_launch_qa.py:

- ORM/service-layer only. No raw SQL string is ever executed.
- Exact-identifier match only. A tenant is addressed by its uuid or its
  exact slug — there is no wildcard or prefix scan, so no input can widen
  scope to a tenant the operator didn't name.
- Dry-run by default. Nothing is written unless --confirm is passed.
- Prints the field names it would change and the tenant's own name; it
  never prints DATABASE_URL or any credential.
- Idempotent. Re-running with the same values is a no-op that reports an
  empty plan cleanly, not an error.
- Partial by design. Only the flags actually passed are written, so a
  second run correcting one field cannot blank the rest.

Statutory numbers (--company-number, --vat-number) are never defaulted or
guessed by this script. A wrong company registration or VAT number on a UK
invoice is a legal defect, not a formatting one — if the operator doesn't
pass them, they stay unset and the invoice simply omits those lines.

Usage:

    python -m scripts.production.set_tenant_identity --list
    python -m scripts.production.set_tenant_identity \\
        --slug default-workspace \\
        --legal-name "Simo Marble & Construction Ltd" \\
        --company-number 12345678 --vat-number GB123456789
    # ... then re-run the same command with --confirm
"""

from __future__ import annotations

import argparse
import sys
import uuid

from app.database.database import SessionLocal
from app.database.models import Tenant
from app.tenants.models import TenantProfileUpdate
from app.tenants.service import tenant_service

# CLI flag -> model field. Kept explicit rather than derived so adding a
# column to the model is a deliberate decision here, not an automatic one.
_FIELD_FLAGS = {
    "--name": "name",
    "--legal-name": "legal_name",
    "--trading-name": "trading_name",
    "--address-line1": "address_line1",
    "--address-line2": "address_line2",
    "--city": "city",
    "--postcode": "postcode",
    "--country": "country",
    "--contact-email": "contact_email",
    "--contact-phone": "contact_phone",
    "--website": "website",
    "--company-number": "company_number",
    "--vat-number": "vat_number",
    "--logo-url": "logo_url",
    "--document-footer": "document_footer",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--tenant-id", help="Tenant uuid (exact match).")
    target.add_argument("--slug", help="Tenant slug (exact match).")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List tenants (id, slug, name, whether an identity is configured) and exit.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually write. Without it this is a dry run and nothing is changed.",
    )
    for flag, field in _FIELD_FLAGS.items():
        parser.add_argument(flag, dest=field, help=f"Set {field}. Pass '' to clear it.")
    return parser


def _resolve(db, args) -> Tenant | None:
    if args.tenant_id:
        try:
            parsed = uuid.UUID(args.tenant_id)
        except ValueError:
            print(f"Not a valid uuid: {args.tenant_id}", file=sys.stderr)
            return None
        return tenant_service.get(db, parsed)
    return db.query(Tenant).filter(Tenant.slug == args.slug).one_or_none()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    db = SessionLocal()
    try:
        if args.list:
            for tenant in db.query(Tenant).order_by(Tenant.created_at).all():
                configured = "configured" if tenant.legal_name or tenant.trading_name else "UNSET"
                print(f"{tenant.id}  {tenant.slug:<28}  {tenant.name}  [{configured}]")
            return 0

        if not (args.tenant_id or args.slug):
            print("Specify --tenant-id or --slug (or --list).", file=sys.stderr)
            return 2

        tenant = _resolve(db, args)
        if tenant is None:
            print("No tenant matched.", file=sys.stderr)
            return 1

        changes = {
            field: getattr(args, field)
            for field in _FIELD_FLAGS.values()
            if getattr(args, field) is not None
            and (getattr(args, field).strip() or None) != getattr(tenant, field)
        }
        if not changes:
            print(f"Tenant '{tenant.name}' already matches — nothing to do.")
            return 0

        print(f"Tenant: {tenant.name} ({tenant.slug})")
        print(f"Fields to set: {', '.join(sorted(changes))}")

        if not args.confirm:
            print("Dry run — nothing written. Re-run with --confirm to apply.")
            return 0

        tenant_service.update_identity(
            db, tenant.id, TenantProfileUpdate(**changes)
        )
        print("Applied.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
