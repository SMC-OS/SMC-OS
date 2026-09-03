"""add quote structured dimensions

Revision ID: b7f3a1c9d420
Revises: 2243d66f83da

Sprint 032 (Workstream C) — replaces the ambiguous single `kitchen_length`
float (metres, unit implied, never stored) as the *source of truth* with
explicit structured dimensions in millimetres: `quantity`, `length_mm`,
`width_mm`, `thickness_mm`, `unit_input` (provenance), plus independent
`splashback_length_mm`/`upstands_length_mm` so those components stop
silently reusing the worktop run's own length.

`kitchen_length` is kept, unchanged, as a derived/mirrored column for
backward compatibility — no existing quote data is destroyed or
recalculated. Every new column is backfilled from existing data before
being made NOT NULL where that's safe:

- length_mm       = kitchen_length * 1000 (existing values were metres)
- width_mm        = 650 (the previous hardcoded SlabCalculator.DEPTH_M)
- quantity        = 1 (every existing quote was implicitly a single run)
- unit_input      = 'm' (the previous form only ever accepted metres)
- thickness_mm    = parsed from the existing `thickness` string where it
                     matches the "<int>mm" shape (stays NULL otherwise —
                     nothing to safely infer)
- splashback_length_mm / upstands_length_mm = kitchen_length * 1000, but
  only for rows where that flag was already True — mirrors the exact
  legacy calculation (app/quotes/slab_calculator.py reused kitchen_length
  for these) so a legacy quote's stored total remains explainable from
  its own now-visible dimensions. Left NULL where the flag is False,
  since there is nothing to preserve.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7f3a1c9d420"
down_revision: Union[str, None] = "2243d66f83da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("quantity", sa.Integer(), nullable=True))
    op.add_column("quotes", sa.Column("length_mm", sa.Float(), nullable=True))
    op.add_column("quotes", sa.Column("width_mm", sa.Float(), nullable=True))
    op.add_column("quotes", sa.Column("thickness_mm", sa.Float(), nullable=True))
    op.add_column("quotes", sa.Column("unit_input", sa.String(), nullable=True))
    op.add_column("quotes", sa.Column("splashback_length_mm", sa.Float(), nullable=True))
    op.add_column("quotes", sa.Column("upstands_length_mm", sa.Float(), nullable=True))

    op.execute("UPDATE quotes SET quantity = 1 WHERE quantity IS NULL")
    op.execute("UPDATE quotes SET length_mm = kitchen_length * 1000 WHERE length_mm IS NULL")
    op.execute("UPDATE quotes SET width_mm = 650 WHERE width_mm IS NULL")
    op.execute("UPDATE quotes SET unit_input = 'm' WHERE unit_input IS NULL")
    op.execute(
        "UPDATE quotes SET thickness_mm = CAST(regexp_replace(thickness, '[^0-9]', '', 'g') AS FLOAT) "
        "WHERE thickness_mm IS NULL AND thickness ~ '^[0-9]+\\s*mm$'"
    )
    op.execute(
        "UPDATE quotes SET splashback_length_mm = kitchen_length * 1000 "
        "WHERE splashback IS TRUE AND splashback_length_mm IS NULL"
    )
    op.execute(
        "UPDATE quotes SET upstands_length_mm = kitchen_length * 1000 "
        "WHERE upstands IS TRUE AND upstands_length_mm IS NULL"
    )

    op.alter_column("quotes", "quantity", nullable=False, server_default="1")
    op.alter_column("quotes", "length_mm", nullable=False)
    op.alter_column("quotes", "width_mm", nullable=False, server_default="650")
    op.alter_column("quotes", "unit_input", nullable=False, server_default="mm")


def downgrade() -> None:
    op.drop_column("quotes", "upstands_length_mm")
    op.drop_column("quotes", "splashback_length_mm")
    op.drop_column("quotes", "unit_input")
    op.drop_column("quotes", "thickness_mm")
    op.drop_column("quotes", "width_mm")
    op.drop_column("quotes", "length_mm")
    op.drop_column("quotes", "quantity")
