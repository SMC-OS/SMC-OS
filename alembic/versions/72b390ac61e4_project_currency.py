"""Capture immutable project currency for contracts, variations and costs.

Existing linked quotes provide historical denomination. For standalone
legacy projects no past currency was recorded; the current tenant default
is the only available backfill, and is not an inferred FX conversion.
"""
from alembic import op
import sqlalchemy as sa

revision = "72b390ac61e4"
down_revision = "6f0e42a9c731"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("currency", sa.String(), nullable=True))
    op.execute("""
        UPDATE projects p SET currency = q.currency
        FROM quotes q WHERE p.quote_id = q.id AND p.tenant_id = q.tenant_id
    """)
    op.execute("""
        UPDATE projects p SET currency = t.currency
        FROM tenants t WHERE p.tenant_id = t.id AND p.currency IS NULL
    """)
    op.execute("UPDATE projects SET currency = 'GBP' WHERE currency IS NULL")
    op.alter_column("projects", "currency", nullable=False, server_default="GBP")


def downgrade():
    op.drop_column("projects", "currency")
