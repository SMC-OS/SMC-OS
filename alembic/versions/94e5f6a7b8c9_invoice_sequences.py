"""Workspace invoice sequences; existing quotes are not renumbered."""
from alembic import op
import sqlalchemy as sa
revision = "94e5f6a7b8c9"
down_revision = "83d4e5f6a7b8"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("tenants", sa.Column("invoice_prefix", sa.String(40), nullable=False, server_default="Invoice"))
    op.add_column("tenants", sa.Column("invoice_next_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("quotes", sa.Column("invoice_number", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_quote_tenant_invoice_number", "quotes", ["tenant_id", "invoice_number"])

def downgrade():
    op.drop_constraint("uq_quote_tenant_invoice_number", "quotes", type_="unique")
    op.drop_column("quotes", "invoice_number")
    op.drop_column("tenants", "invoice_next_number")
    op.drop_column("tenants", "invoice_prefix")
