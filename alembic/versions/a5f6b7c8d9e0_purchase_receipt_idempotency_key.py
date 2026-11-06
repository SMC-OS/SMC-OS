"""Optional per-delivery idempotency key on purchase receipts. Additive only:
existing rows keep NULL and are not rewritten."""
from alembic import op
import sqlalchemy as sa

revision = "a5f6b7c8d9e0"
down_revision = "94e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("purchase_receipts", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_index(
        "uq_purchase_receipts_tenant_idempotency_key",
        "purchase_receipts",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade():
    op.drop_index("uq_purchase_receipts_tenant_idempotency_key", table_name="purchase_receipts")
    op.drop_column("purchase_receipts", "idempotency_key")
