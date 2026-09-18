"""job financials + variations

Revision ID: 1a2b3c4d5e6f
Revises: 709c9ed313cc
Create Date: 2026-09-18 14:00:00.000000

GeoCore Premium OS, Plan 04 (Job Financials + Variations). Purely
additive: two new tables (project_cost_entries, variations) plus one
child table (variation_items). No existing table is rewritten, no
historical project or quote row is touched, and no cost is fabricated
for a project that has none — a pre-Plan-04 project simply has zero
cost_entries/variations rows, exactly as if the feature had always
existed and nobody had used it yet.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = '709c9ed313cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_cost_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("supplier_or_payee", sa.String(), nullable=True),
        sa.Column("reference", sa.String(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("unit_cost", sa.Float(), nullable=True),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("cost_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_project_cost_entries_tenant_id", "project_cost_entries", ["tenant_id"])
    op.create_index("ix_project_cost_entries_project_id", "project_cost_entries", ["project_id"])

    op.create_table(
        "variations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("vat_rate", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("subtotal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("vat", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "reference", name="uq_variations_project_reference"),
    )
    op.create_index("ix_variations_tenant_id", "variations", ["tenant_id"])
    op.create_index("ix_variations_project_id", "variations", ["project_id"])

    op.create_table(
        "variation_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("variation_id", UUID(as_uuid=True), sa.ForeignKey("variations.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("unit", sa.String(), nullable=False, server_default="item"),
        sa.Column("unit_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_variation_items_variation_id", "variation_items", ["variation_id"])


def downgrade() -> None:
    op.drop_index("ix_variation_items_variation_id", table_name="variation_items")
    op.drop_table("variation_items")

    op.drop_index("ix_variations_project_id", table_name="variations")
    op.drop_index("ix_variations_tenant_id", table_name="variations")
    op.drop_table("variations")

    op.drop_index("ix_project_cost_entries_project_id", table_name="project_cost_entries")
    op.drop_index("ix_project_cost_entries_tenant_id", table_name="project_cost_entries")
    op.drop_table("project_cost_entries")
