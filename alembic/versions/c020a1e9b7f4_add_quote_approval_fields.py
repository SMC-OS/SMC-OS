"""add quote approval fields

Revision ID: c020a1e9b7f4
Revises: f81683afc3f4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c020a1e9b7f4"
down_revision: Union[str, None] = "f81683afc3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quotes",
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
    )
    op.add_column(
        "quotes",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "quotes",
        sa.Column("approved_by_user_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_quotes_approved_by_user_id_users",
        "quotes",
        "users",
        ["approved_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_quotes_approved_by_user_id_users",
        "quotes",
        type_="foreignkey",
    )
    op.drop_column("quotes", "approved_by_user_id")
    op.drop_column("quotes", "approved_at")
    op.drop_column("quotes", "status")