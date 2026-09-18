"""master materials catalogue + stone quote engine v2

Revision ID: 709c9ed313cc
Revises: bfed99c6fa8c
Create Date: 2026-09-18 09:00:00.000000

GeoCore Premium OS, Plan 03 (Master Materials & Supplier Catalogue +
Stone Quote Engine V2). Purely additive: seven new tables
(catalogue_suppliers/manufacturers/brands/collections/surfaces/
surface_variants/tenant_catalogue_overrides) plus three new nullable
columns on quote_items (catalogue_surface_id, catalogue_variant_id,
catalogue_snapshot). No existing table is rewritten, no existing quote
row is touched, no historical material/thickness free text is
reinterpreted or backfilled with a guessed catalogue link — a
pre-Plan-03 stone quote line simply has NULL catalogue_surface_id
forever, exactly as it does today.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '709c9ed313cc'
down_revision: Union[str, None] = 'bfed99c6fa8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catalogue_suppliers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("website", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("source_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_catalogue_suppliers_slug"),
    )

    op.create_table(
        "catalogue_manufacturers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("website", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("source_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_catalogue_manufacturers_slug"),
    )

    op.create_table(
        "catalogue_brands",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("manufacturer_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_manufacturers.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("website", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_catalogue_brands_slug"),
    )
    op.create_index("ix_catalogue_brands_manufacturer_id", "catalogue_brands", ["manufacturer_id"])

    op.create_table(
        "catalogue_collections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_brands.id"), nullable=True),
        sa.Column("manufacturer_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_manufacturers.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_catalogue_collections_slug"),
    )
    op.create_index("ix_catalogue_collections_brand_id", "catalogue_collections", ["brand_id"])
    op.create_index("ix_catalogue_collections_manufacturer_id", "catalogue_collections", ["manufacturer_id"])

    op.create_table(
        "catalogue_surfaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_suppliers.id"), nullable=True),
        sa.Column("manufacturer_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_manufacturers.id"), nullable=True),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_brands.id"), nullable=True),
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_collections.id"), nullable=True),
        sa.Column("canonical_name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("supplier_sku", sa.String(), nullable=True),
        sa.Column("manufacturer_sku", sa.String(), nullable=True),
        sa.Column("material_family", sa.String(), nullable=False),
        sa.Column("colour_family", sa.String(), nullable=True),
        sa.Column("pattern_family", sa.String(), nullable=True),
        sa.Column("origin_country", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("discontinued", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("source_name", sa.String(), nullable=True),
        sa.Column("source_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_catalogue_surfaces_tenant_id", "catalogue_surfaces", ["tenant_id"])
    op.create_index("ix_catalogue_surfaces_supplier_id", "catalogue_surfaces", ["supplier_id"])
    op.create_index("ix_catalogue_surfaces_manufacturer_id", "catalogue_surfaces", ["manufacturer_id"])
    op.create_index("ix_catalogue_surfaces_brand_id", "catalogue_surfaces", ["brand_id"])
    op.create_index("ix_catalogue_surfaces_collection_id", "catalogue_surfaces", ["collection_id"])
    op.create_index("ix_catalogue_surfaces_canonical_name", "catalogue_surfaces", ["canonical_name"])
    op.create_index("ix_catalogue_surfaces_material_family", "catalogue_surfaces", ["material_family"])
    op.create_index("ix_catalogue_surfaces_active", "catalogue_surfaces", ["active"])

    op.create_table(
        "catalogue_surface_variants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("surface_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_surfaces.id"), nullable=False),
        sa.Column("thickness_mm", sa.Float(), nullable=True),
        sa.Column("finish", sa.String(), nullable=True),
        sa.Column("slab_length_mm", sa.Float(), nullable=True),
        sa.Column("slab_width_mm", sa.Float(), nullable=True),
        sa.Column("supplier_variant_sku", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_catalogue_surface_variants_surface_id", "catalogue_surface_variants", ["surface_id"])

    op.create_table(
        "tenant_catalogue_overrides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("surface_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_surfaces.id"), nullable=False),
        sa.Column(
            "surface_variant_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_surface_variants.id"), nullable=True
        ),
        sa.Column("preferred_supplier_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_suppliers.id"), nullable=True),
        sa.Column("supplier_account_ref", sa.String(), nullable=True),
        sa.Column("tenant_supplier_sku", sa.String(), nullable=True),
        sa.Column("buy_cost_per_slab", sa.Float(), nullable=True),
        sa.Column("buy_cost_per_m2", sa.Float(), nullable=True),
        sa.Column("delivery_cost", sa.Float(), nullable=True),
        sa.Column("fabrication_rate", sa.Float(), nullable=True),
        sa.Column("installation_rate", sa.Float(), nullable=True),
        sa.Column("default_markup_percent", sa.Float(), nullable=True),
        sa.Column("target_margin_percent", sa.Float(), nullable=True),
        sa.Column("selling_price_per_slab", sa.Float(), nullable=True),
        sa.Column("selling_price_per_m2", sa.Float(), nullable=True),
        sa.Column("stock_status", sa.String(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("tenant_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("private_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tenant_catalogue_overrides_tenant_id", "tenant_catalogue_overrides", ["tenant_id"])
    op.create_index("ix_tenant_catalogue_overrides_surface_id", "tenant_catalogue_overrides", ["surface_id"])
    op.create_index(
        "ix_tenant_catalogue_overrides_surface_variant_id", "tenant_catalogue_overrides", ["surface_variant_id"]
    )

    op.add_column(
        "quote_items", sa.Column("catalogue_surface_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_surfaces.id"), nullable=True)
    )
    op.add_column(
        "quote_items",
        sa.Column(
            "catalogue_variant_id", UUID(as_uuid=True), sa.ForeignKey("catalogue_surface_variants.id"), nullable=True
        ),
    )
    op.add_column("quote_items", sa.Column("catalogue_snapshot", JSONB(), nullable=True))
    op.create_index("ix_quote_items_catalogue_surface_id", "quote_items", ["catalogue_surface_id"])


def downgrade() -> None:
    op.drop_index("ix_quote_items_catalogue_surface_id", table_name="quote_items")
    op.drop_column("quote_items", "catalogue_snapshot")
    op.drop_column("quote_items", "catalogue_variant_id")
    op.drop_column("quote_items", "catalogue_surface_id")

    op.drop_index("ix_tenant_catalogue_overrides_surface_variant_id", table_name="tenant_catalogue_overrides")
    op.drop_index("ix_tenant_catalogue_overrides_surface_id", table_name="tenant_catalogue_overrides")
    op.drop_index("ix_tenant_catalogue_overrides_tenant_id", table_name="tenant_catalogue_overrides")
    op.drop_table("tenant_catalogue_overrides")

    op.drop_index("ix_catalogue_surface_variants_surface_id", table_name="catalogue_surface_variants")
    op.drop_table("catalogue_surface_variants")

    op.drop_index("ix_catalogue_surfaces_active", table_name="catalogue_surfaces")
    op.drop_index("ix_catalogue_surfaces_material_family", table_name="catalogue_surfaces")
    op.drop_index("ix_catalogue_surfaces_canonical_name", table_name="catalogue_surfaces")
    op.drop_index("ix_catalogue_surfaces_collection_id", table_name="catalogue_surfaces")
    op.drop_index("ix_catalogue_surfaces_brand_id", table_name="catalogue_surfaces")
    op.drop_index("ix_catalogue_surfaces_manufacturer_id", table_name="catalogue_surfaces")
    op.drop_index("ix_catalogue_surfaces_supplier_id", table_name="catalogue_surfaces")
    op.drop_index("ix_catalogue_surfaces_tenant_id", table_name="catalogue_surfaces")
    op.drop_table("catalogue_surfaces")

    op.drop_index("ix_catalogue_collections_manufacturer_id", table_name="catalogue_collections")
    op.drop_index("ix_catalogue_collections_brand_id", table_name="catalogue_collections")
    op.drop_table("catalogue_collections")

    op.drop_index("ix_catalogue_brands_manufacturer_id", table_name="catalogue_brands")
    op.drop_table("catalogue_brands")

    op.drop_table("catalogue_manufacturers")
    op.drop_table("catalogue_suppliers")
