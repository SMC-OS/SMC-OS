"""add tenant workspace configuration (currency, trades, onboarding, logo file)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9

Sprint 036, Workstreams I and J.

`currency` (NOT NULL, default 'GBP') is the answer to "GBP must not be
hard-coded forever" without pretending GeoCore is multi-currency today.
It is the single source of truth for how a workspace's money is displayed,
and it is mirrored onto each quote at creation (quotes.currency, added in
b3c4d5e6f7a8) so a document a customer already holds never silently
re-denominates if the workspace later changes it. The default is a fact:
every tenant on this platform today is a UK business.

`trades` is a comma-separated list of trade keys selected during
onboarding. Deliberately a delimited String rather than JSON or ARRAY: it
is read whole, never queried into, and introducing a third storage shape
for a list of twelve short constants would be architecture for its own
sake. NULL means "never asked" (every tenant that existed before this
migration), which is a different state from "" ("asked, chose nothing") —
and that distinction is what stops the onboarding flow from re-prompting
someone who deliberately skipped it.

`onboarding_completed_at` is NULL for every existing tenant. Those tenants
are already using the product, so the onboarding flow treats a tenant that
has customers, quotes or projects as complete regardless — see
app/tenants/onboarding.py. Nobody who is already working gets sent back to
a setup wizard.

`logo_storage_filename` holds the generated UUID-based filename of an
uploaded logo under UPLOAD_DIR. It is never a user-supplied path (the same
path-traversal-safe-by-construction rule as documents, ADR-032). It is
separate from the existing `logo_url`, which stays the
externally-hosted-URL escape hatch, so a tenant that pasted a URL before
this sprint keeps exactly the logo it had.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("currency", sa.String(), nullable=False, server_default="GBP"),
    )
    op.add_column("tenants", sa.Column("trades", sa.String(), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants", sa.Column("logo_storage_filename", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tenants", "logo_storage_filename")
    op.drop_column("tenants", "onboarding_completed_at")
    op.drop_column("tenants", "trades")
    op.drop_column("tenants", "currency")
