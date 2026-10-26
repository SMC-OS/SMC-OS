"""Add per-session logout revocation; never change customer/tenant data.

Revision ID: 6f0e42a9c731
Revises: 4d5e6f7a8b9c
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "6f0e42a9c731"
down_revision = "4d5e6f7a8b9c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("revoked_browser_sessions",
        sa.Column("token_id", sa.String(64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_revoked_browser_sessions_user_id", "revoked_browser_sessions", ["user_id"])


def downgrade():
    op.drop_index("ix_revoked_browser_sessions_user_id", table_name="revoked_browser_sessions")
    op.drop_table("revoked_browser_sessions")
