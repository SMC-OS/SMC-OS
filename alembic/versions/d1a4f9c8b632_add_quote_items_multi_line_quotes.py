"""add quote_items table (multi-line-item quotes)

Revision ID: d1a4f9c8b632
Revises: c4e8b2a017f5

Sprint 033 (Workstream C) — the true multi-line-item quote architecture
deferred in Sprint 032 §4. `quotes` stays a header row (customer/status/
postcode/approval/totals); every quote's actual contents move to one or
more `quote_items` rows.

Backfill, not a breaking migration: every existing quote gets reconstructed
into one or more QuoteItem rows from its own former scalar columns —
- always one "worktop" item (material/thickness/quantity/length_mm/
  width_mm/thickness_mm/unit_input, verbatim)
- an "island" item if `island` was true (length_mm = the old fixed
  ISLAND_EXTRA_RUN_MM constant, 1800mm, at the worktop's own width)
- a "waterfall_panel" item, quantity = the old `waterfall` count, if > 0
  (length_mm/width_mm = the old fixed WATERFALL_PANEL_AREA_M2 constant,
  expressed as 900mm x 650mm)
- a "splashback" item if `splashback` was true (length_mm = the row's own
  `splashback_length_mm`, falling back to the worktop's length_mm for a
  pre-Sprint-032 row that predates that column; width_mm = the old fixed
  SPLASHBACK_HEIGHT_MM constant, 150mm)
- an "upstand" item if `upstands` was true (same shape, upstands_length_mm
  falling back to length_mm; width_mm = the old fixed UPSTAND_HEIGHT_MM
  constant, 60mm)

No existing `quotes` row, column, or computed total (price_before_vat/vat/
total) is touched — this migration only ever adds rows to the new table.
`quotes.material`/`thickness`/`kitchen_length`/etc. remain exactly as they
were and continue to be populated as a single-item summary going forward
(see app/quotes/service.py) so every existing reader keeps working
unmodified.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1a4f9c8b632"
down_revision: Union[str, None] = "c4e8b2a017f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ISLAND_EXTRA_RUN_MM = 1800
_WATERFALL_PANEL_LENGTH_MM = 900
_WATERFALL_PANEL_WIDTH_MM = 650
_SPLASHBACK_HEIGHT_MM = 150
_UPSTAND_HEIGHT_MM = 60


def _quotes_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "quotes",
        metadata,
        sa.Column("id", sa.UUID),
        sa.Column("material", sa.String),
        sa.Column("thickness", sa.String),
        sa.Column("quantity", sa.Integer),
        sa.Column("length_mm", sa.Float),
        sa.Column("width_mm", sa.Float),
        sa.Column("thickness_mm", sa.Float),
        sa.Column("unit_input", sa.String),
        sa.Column("island", sa.Boolean),
        sa.Column("waterfall", sa.Integer),
        sa.Column("splashback", sa.Boolean),
        sa.Column("splashback_length_mm", sa.Float),
        sa.Column("upstands", sa.Boolean),
        sa.Column("upstands_length_mm", sa.Float),
    )


def _quote_items_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "quote_items",
        metadata,
        sa.Column("id", sa.UUID),
        sa.Column("quote_id", sa.UUID),
        sa.Column("position", sa.Integer),
        sa.Column("item_type", sa.String),
        sa.Column("material", sa.String),
        sa.Column("thickness", sa.String),
        sa.Column("quantity", sa.Integer),
        sa.Column("length_mm", sa.Float),
        sa.Column("width_mm", sa.Float),
        sa.Column("thickness_mm", sa.Float),
        sa.Column("unit_input", sa.String),
        sa.Column("notes", sa.String),
    )


def upgrade() -> None:
    import uuid

    op.create_table(
        "quote_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("quote_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("item_type", sa.String(), nullable=False, server_default="worktop"),
        sa.Column("material", sa.String(), nullable=False),
        sa.Column("thickness", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("length_mm", sa.Float(), nullable=False),
        sa.Column("width_mm", sa.Float(), nullable=False),
        sa.Column("thickness_mm", sa.Float(), nullable=True),
        sa.Column("unit_input", sa.String(), nullable=False, server_default="mm"),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("price_per_slab", sa.Float(), nullable=True),
        sa.Column("slabs", sa.Integer(), nullable=True),
        sa.Column("line_total", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], name="fk_quote_items_quote_id_quotes"),
    )
    op.create_index("ix_quote_items_quote_id", "quote_items", ["quote_id"])

    bind = op.get_bind()
    quotes = _quotes_table()
    quote_items = _quote_items_table()

    rows = bind.execute(sa.select(quotes)).mappings().all()
    to_insert = []
    for row in rows:
        position = 0

        to_insert.append(
            {
                "id": uuid.uuid4(),
                "quote_id": row["id"],
                "position": position,
                "item_type": "worktop",
                "material": row["material"],
                "thickness": row["thickness"],
                "quantity": row["quantity"] or 1,
                "length_mm": row["length_mm"],
                "width_mm": row["width_mm"],
                "thickness_mm": row["thickness_mm"],
                "unit_input": row["unit_input"] or "mm",
                "notes": "Migrated from a Sprint 032 single-job quote",
            }
        )
        position += 1

        if row["island"]:
            to_insert.append(
                {
                    "id": uuid.uuid4(),
                    "quote_id": row["id"],
                    "position": position,
                    "item_type": "island",
                    "material": row["material"],
                    "thickness": row["thickness"],
                    "quantity": 1,
                    "length_mm": _ISLAND_EXTRA_RUN_MM,
                    "width_mm": row["width_mm"],
                    "thickness_mm": row["thickness_mm"],
                    "unit_input": "mm",
                    "notes": "Migrated from a Sprint 032 quote's `island` flag",
                }
            )
            position += 1

        if row["waterfall"]:
            to_insert.append(
                {
                    "id": uuid.uuid4(),
                    "quote_id": row["id"],
                    "position": position,
                    "item_type": "waterfall_panel",
                    "material": row["material"],
                    "thickness": row["thickness"],
                    "quantity": row["waterfall"],
                    "length_mm": _WATERFALL_PANEL_LENGTH_MM,
                    "width_mm": _WATERFALL_PANEL_WIDTH_MM,
                    "thickness_mm": row["thickness_mm"],
                    "unit_input": "mm",
                    "notes": "Migrated from a Sprint 032 quote's `waterfall` count",
                }
            )
            position += 1

        if row["splashback"]:
            to_insert.append(
                {
                    "id": uuid.uuid4(),
                    "quote_id": row["id"],
                    "position": position,
                    "item_type": "splashback",
                    "material": row["material"],
                    "thickness": row["thickness"],
                    "quantity": 1,
                    "length_mm": row["splashback_length_mm"] or row["length_mm"],
                    "width_mm": _SPLASHBACK_HEIGHT_MM,
                    "thickness_mm": row["thickness_mm"],
                    "unit_input": "mm",
                    "notes": "Migrated from a Sprint 032 quote's `splashback` flag",
                }
            )
            position += 1

        if row["upstands"]:
            to_insert.append(
                {
                    "id": uuid.uuid4(),
                    "quote_id": row["id"],
                    "position": position,
                    "item_type": "upstand",
                    "material": row["material"],
                    "thickness": row["thickness"],
                    "quantity": 1,
                    "length_mm": row["upstands_length_mm"] or row["length_mm"],
                    "width_mm": _UPSTAND_HEIGHT_MM,
                    "thickness_mm": row["thickness_mm"],
                    "unit_input": "mm",
                    "notes": "Migrated from a Sprint 032 quote's `upstands` flag",
                }
            )
            position += 1

    if to_insert:
        bind.execute(sa.insert(quote_items), to_insert)


def downgrade() -> None:
    op.drop_index("ix_quote_items_quote_id", table_name="quote_items")
    op.drop_table("quote_items")
