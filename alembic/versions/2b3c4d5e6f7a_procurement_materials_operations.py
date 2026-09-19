"""procurement + materials operations

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-09-18 15:30:00.000000

GeoCore Premium OS, Plan 05 (Job Financials + Variations' sibling for the
operational side). Purely additive: five new tables
(project_material_requirements, tenant_supplier_accounts, purchase_orders,
purchase_order_items, purchase_receipts, purchase_receipt_items,
project_material_allocations — seven, not five) plus two nullable FK
columns on the existing project_cost_entries table. No existing table is
rewritten, no historical project/quote/cost row is touched, and no
procurement history is invented for a project that has none — a
pre-Plan-05 project simply has zero requirements/POs, exactly as if the
feature had always existed and nobody had used it yet.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '2b3c4d5e6f7a'
down_revision: Union[str, None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_material_requirements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("catalogue_surface_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_surfaces.id"), nullable=True),
        sa.Column(
            "catalogue_variant_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_surface_variants.id"), nullable=True
        ),
        sa.Column("custom_material_name", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("material_family", sa.String(), nullable=True),
        sa.Column("required_quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("required_by_date", sa.Date(), nullable=True),
        sa.Column("preferred_supplier_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_suppliers.id"), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="required"),
        sa.Column("notes", sa.Text(), nullable=True),
        # Polymorphic origin, same source_type/source_id convention as
        # `tasks` — records a deliberate conversion (Task 2), never an
        # automatic one.
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("source_id", UUID(as_uuid=True), nullable=True),
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
    op.create_index(
        "ix_project_material_requirements_tenant_id", "project_material_requirements", ["tenant_id"]
    )
    op.create_index(
        "ix_project_material_requirements_project_id", "project_material_requirements", ["project_id"]
    )
    op.create_index("ix_project_material_requirements_status", "project_material_requirements", ["status"])

    op.create_table(
        "tenant_supplier_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_suppliers.id"), nullable=False),
        sa.Column("account_reference", sa.String(), nullable=True),
        sa.Column("contact_name", sa.String(), nullable=True),
        sa.Column("contact_email", sa.String(), nullable=True),
        sa.Column("contact_phone", sa.String(), nullable=True),
        sa.Column("payment_terms", sa.String(), nullable=True),
        sa.Column("delivery_notes", sa.Text(), nullable=True),
        sa.Column("private_notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "supplier_id", name="uq_tenant_supplier_accounts_tenant_supplier"),
    )
    op.create_index("ix_tenant_supplier_accounts_tenant_id", "tenant_supplier_accounts", ["tenant_id"])
    op.create_index("ix_tenant_supplier_accounts_supplier_id", "tenant_supplier_accounts", ["supplier_id"])

    op.create_table(
        "purchase_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_suppliers.id"), nullable=True),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("supplier_reference", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("vat_rate", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("subtotal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("vat", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_purchase_orders_tenant_reference"),
    )
    op.create_index("ix_purchase_orders_tenant_id", "purchase_orders", ["tenant_id"])
    op.create_index("ix_purchase_orders_project_id", "purchase_orders", ["project_id"])
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])
    op.create_index("ix_purchase_orders_expected_delivery_date", "purchase_orders", ["expected_delivery_date"])

    op.create_table(
        "purchase_order_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("purchase_order_id", UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id"), nullable=False),
        sa.Column(
            "material_requirement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("project_material_requirements.id"),
            nullable=True,
        ),
        sa.Column("catalogue_surface_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_surfaces.id"), nullable=True),
        sa.Column(
            "catalogue_variant_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_surface_variants.id"), nullable=True
        ),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("unit", sa.String(), nullable=False, server_default="item"),
        sa.Column("unit_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_purchase_order_items_purchase_order_id", "purchase_order_items", ["purchase_order_id"])
    op.create_index(
        "ix_purchase_order_items_material_requirement_id", "purchase_order_items", ["material_requirement_id"]
    )

    op.create_table(
        "purchase_receipts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("purchase_order_id", UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("delivery_reference", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_purchase_receipts_tenant_id", "purchase_receipts", ["tenant_id"])
    op.create_index("ix_purchase_receipts_purchase_order_id", "purchase_receipts", ["purchase_order_id"])

    op.create_table(
        "purchase_receipt_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("purchase_receipt_id", UUID(as_uuid=True), sa.ForeignKey("purchase_receipts.id"), nullable=False),
        sa.Column(
            "purchase_order_item_id", UUID(as_uuid=True), sa.ForeignKey("purchase_order_items.id"), nullable=False
        ),
        sa.Column("quantity_received", sa.Float(), nullable=False),
    )
    op.create_index("ix_purchase_receipt_items_purchase_receipt_id", "purchase_receipt_items", ["purchase_receipt_id"])
    op.create_index(
        "ix_purchase_receipt_items_purchase_order_item_id", "purchase_receipt_items", ["purchase_order_item_id"]
    )

    op.create_table(
        "project_material_allocations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "material_requirement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("project_material_requirements.id"),
            nullable=True,
        ),
        sa.Column(
            "purchase_order_item_id", UUID(as_uuid=True), sa.ForeignKey("purchase_order_items.id"), nullable=True
        ),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("allocated_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_project_material_allocations_tenant_id", "project_material_allocations", ["tenant_id"])
    op.create_index("ix_project_material_allocations_project_id", "project_material_allocations", ["project_id"])
    op.create_index(
        "ix_project_material_allocations_material_requirement_id",
        "project_material_allocations",
        ["material_requirement_id"],
    )

    # Additive linkage from the Plan 04 cost ledger to the PO/PO-item that
    # created a committed cost entry — see app/financials/service.py and
    # ADR-050 for exactly how this prevents double-counting.
    op.add_column(
        "project_cost_entries",
        sa.Column("purchase_order_id", UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id"), nullable=True),
    )
    op.add_column(
        "project_cost_entries",
        sa.Column(
            "purchase_order_item_id", UUID(as_uuid=True), sa.ForeignKey("purchase_order_items.id"), nullable=True
        ),
    )
    op.create_index("ix_project_cost_entries_purchase_order_id", "project_cost_entries", ["purchase_order_id"])
    op.create_index(
        "ix_project_cost_entries_purchase_order_item_id", "project_cost_entries", ["purchase_order_item_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_project_cost_entries_purchase_order_item_id", table_name="project_cost_entries")
    op.drop_index("ix_project_cost_entries_purchase_order_id", table_name="project_cost_entries")
    op.drop_column("project_cost_entries", "purchase_order_item_id")
    op.drop_column("project_cost_entries", "purchase_order_id")

    op.drop_index(
        "ix_project_material_allocations_material_requirement_id", table_name="project_material_allocations"
    )
    op.drop_index("ix_project_material_allocations_project_id", table_name="project_material_allocations")
    op.drop_index("ix_project_material_allocations_tenant_id", table_name="project_material_allocations")
    op.drop_table("project_material_allocations")

    op.drop_index("ix_purchase_receipt_items_purchase_order_item_id", table_name="purchase_receipt_items")
    op.drop_index("ix_purchase_receipt_items_purchase_receipt_id", table_name="purchase_receipt_items")
    op.drop_table("purchase_receipt_items")

    op.drop_index("ix_purchase_receipts_purchase_order_id", table_name="purchase_receipts")
    op.drop_index("ix_purchase_receipts_tenant_id", table_name="purchase_receipts")
    op.drop_table("purchase_receipts")

    op.drop_index("ix_purchase_order_items_material_requirement_id", table_name="purchase_order_items")
    op.drop_index("ix_purchase_order_items_purchase_order_id", table_name="purchase_order_items")
    op.drop_table("purchase_order_items")

    op.drop_index("ix_purchase_orders_expected_delivery_date", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_status", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_supplier_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_project_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_tenant_id", table_name="purchase_orders")
    op.drop_table("purchase_orders")

    op.drop_index("ix_tenant_supplier_accounts_supplier_id", table_name="tenant_supplier_accounts")
    op.drop_index("ix_tenant_supplier_accounts_tenant_id", table_name="tenant_supplier_accounts")
    op.drop_table("tenant_supplier_accounts")

    op.drop_index("ix_project_material_requirements_status", table_name="project_material_requirements")
    op.drop_index("ix_project_material_requirements_project_id", table_name="project_material_requirements")
    op.drop_index("ix_project_material_requirements_tenant_id", table_name="project_material_requirements")
    op.drop_table("project_material_requirements")
