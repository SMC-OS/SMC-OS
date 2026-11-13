"""Release defaults: delegated financial approval authority, quote revisions, approval amount snapshots,
workspace invoice supplier settings and issued-invoice snapshots. Additive only: every new column is nullable or has
a server default, so existing rows keep working unchanged."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b6c7d8e9f0a1"
down_revision = "a5f6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("can_approve_financials", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("quotes", sa.Column("revision_of_quote_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quotes.id"), nullable=True))
    op.add_column("quotes", sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("quotes", sa.Column("approved_amount", sa.Float(), nullable=True))
    op.add_column("quotes", sa.Column("invoice_issued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quotes", sa.Column("invoice_due_date", sa.Date(), nullable=True))
    op.add_column("quotes", sa.Column("invoice_snapshot", postgresql.JSONB(), nullable=True))
    op.create_index("ix_quotes_revision_of_quote_id", "quotes", ["revision_of_quote_id"])
    op.add_column("variations", sa.Column("approved_amount", sa.Float(), nullable=True))
    op.add_column("purchase_orders", sa.Column("approved_amount", sa.Float(), nullable=True))
    op.add_column("tenants", sa.Column("vat_registered", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tenants", sa.Column("bank_account_name", sa.String(), nullable=True))
    op.add_column("tenants", sa.Column("bank_sort_code", sa.String(), nullable=True))
    op.add_column("tenants", sa.Column("bank_account_number", sa.String(), nullable=True))
    op.add_column("tenants", sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("tenants", sa.Column("payment_instructions", sa.Text(), nullable=True))
    # A workspace that already stores a VAT number has told us it is registered; nothing else is inferred.
    op.execute("UPDATE tenants SET vat_registered = true WHERE vat_number IS NOT NULL AND btrim(vat_number) <> ''")


def downgrade():
    for col in ("payment_instructions", "payment_terms_days", "bank_account_number", "bank_sort_code", "bank_account_name", "vat_registered"):
        op.drop_column("tenants", col)
    op.drop_column("purchase_orders", "approved_amount")
    op.drop_column("variations", "approved_amount")
    op.drop_index("ix_quotes_revision_of_quote_id", table_name="quotes")
    for col in ("invoice_snapshot", "invoice_due_date", "invoice_issued_at", "approved_amount", "revision_number", "revision_of_quote_id"):
        op.drop_column("quotes", col)
    op.drop_column("users", "can_approve_financials")
