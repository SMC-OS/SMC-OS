"""add notification_preferences

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0

Sprint 039, Workstream B. One new table, no changes to existing ones, and
no data seeded.

Sprint 036 shipped the notification-settings screen as four `localStorage`
keys, and said so honestly in its own docstring: a per-user server-side
preference table was "genuine follow-up work". This is that table.

Nothing is backfilled on purpose. A user with no row for a category gets
the defaults in app/notifications/categories.py — in-app on, email off —
which is exactly the behaviour every user has today. So this migration
changes nobody's experience, and nobody starts receiving email they did
not ask for.

Both foreign keys cascade. That is the same exception `pipeline_stages`
makes and for the same reason: this table holds regenerable
configuration, not business records. Deleting every row restores the
defaults, so blocking a user or tenant delete on it would protect
nothing.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("in_app", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "category", name="uq_notification_preferences_user_category"
        ),
    )
    op.create_index(
        "ix_notification_preferences_tenant_id",
        "notification_preferences",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_preferences_user_id",
        "notification_preferences",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    # Genuinely safe: this migration created no rows anywhere, and
    # dropping every preference restores the defaults that a user with no
    # row already gets.
    op.drop_index(
        "ix_notification_preferences_user_id", table_name="notification_preferences"
    )
    op.drop_index(
        "ix_notification_preferences_tenant_id", table_name="notification_preferences"
    )
    op.drop_table("notification_preferences")
