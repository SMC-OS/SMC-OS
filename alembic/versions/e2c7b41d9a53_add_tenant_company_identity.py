"""add tenant company identity (customer-facing business details)

Revision ID: e2c7b41d9a53
Revises: d1a4f9c8b632

Sprint 034 — product-correctness fix. Until now every invoice PDF this
platform generated carried one hardcoded letterhead ("SIMO MARBLE &
CONSTRUCTION LTD / Unit 4, Riverside Trade Park, London") baked into
app/quotes/pdf.py, regardless of which tenant the quote belonged to. That
is a genuine cross-tenant identity leak in customer-facing output: Tenant B
downloading their own invoice saw Tenant A's trading identity on it.

This migration adds the columns a tenant needs to own its own
customer-facing business identity. Every column is nullable — a tenant that
has configured nothing renders from `tenants.name`, never from another
tenant's details and never from the platform's own brand.

Backfill (preserving historical document behaviour):

Every existing invoice already renders the Simo letterhead, so leaving the
real operating tenant blank would silently change what its customers see.
Two conservative rules therefore backfill it, and nothing else:

  1. If the database holds exactly ONE tenant, that tenant *is* the
     operating business whose identity those PDFs have always shown — there
     is no second tenant that could wrongly inherit it. Backfill it.
  2. Otherwise, backfill only tenants whose name/slug identifies them as
     Simo Marble & Construction. A generically-named co-tenant is left
     alone rather than guessed at.

Only the two facts the letterhead already printed are backfilled (legal
name and address). `company_number` and `vat_number` are deliberately left
NULL: no accurate value for them exists anywhere in this repository, and a
fabricated company registration or VAT number on a UK invoice is a legal
defect, not a cosmetic one. The owner supplies those via Settings →
Company Identity (or scripts/set_tenant_identity.py).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2c7b41d9a53"
down_revision: Union[str, None] = "d1a4f9c8b632"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The exact strings app/quotes/pdf.py hardcoded before this sprint. Kept
# here verbatim so the backfilled tenant's PDF renders character-for-
# character what it rendered yesterday.
_LEGACY_LEGAL_NAME = "Simo Marble & Construction Ltd"
_LEGACY_ADDRESS_LINE1 = "Unit 4, Riverside Trade Park"
_LEGACY_CITY = "London"

_IDENTITY_COLUMNS = (
    "legal_name",
    "trading_name",
    "address_line1",
    "address_line2",
    "city",
    "postcode",
    "country",
    "contact_email",
    "contact_phone",
    "website",
    "company_number",
    "vat_number",
    "logo_url",
    "document_footer",
)


def _tenants_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "tenants",
        metadata,
        sa.Column("id", sa.UUID),
        sa.Column("name", sa.String),
        sa.Column("slug", sa.String),
        sa.Column("legal_name", sa.String),
        sa.Column("address_line1", sa.String),
        sa.Column("city", sa.String),
    )


def upgrade() -> None:
    for column in _IDENTITY_COLUMNS:
        op.add_column("tenants", sa.Column(column, sa.String(), nullable=True))

    bind = op.get_bind()
    tenants = _tenants_table()

    rows = bind.execute(sa.select(tenants.c.id, tenants.c.name, tenants.c.slug)).mappings().all()
    if not rows:
        return

    if len(rows) == 1:
        targets = [rows[0]["id"]]
    else:
        targets = [
            row["id"]
            for row in rows
            if "simo" in (row["name"] or "").lower() or (row["slug"] or "").lower().startswith("simo")
        ]

    if not targets:
        return

    bind.execute(
        sa.update(tenants)
        .where(tenants.c.id.in_(targets))
        .values(
            legal_name=_LEGACY_LEGAL_NAME,
            address_line1=_LEGACY_ADDRESS_LINE1,
            city=_LEGACY_CITY,
        )
    )


def downgrade() -> None:
    for column in reversed(_IDENTITY_COLUMNS):
        op.drop_column("tenants", column)
