"""add project quote_id

Revision ID: d3e7a9c1f204
Revises: c020a1e9b7f4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3e7a9c1f204"
down_revision: Union[str, None] = "c020a1e9b7f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("quote_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_quote_id_quotes",
        "projects",
        "quotes",
        ["quote_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_projects_quote_id",
        "projects",
        ["quote_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_projects_quote_id", "projects", type_="unique")
    op.drop_constraint("fk_projects_quote_id_quotes", "projects", type_="foreignkey")
    op.drop_column("projects", "quote_id")
