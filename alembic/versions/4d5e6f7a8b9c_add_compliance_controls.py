"""add compliance deletion and copyright controls

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "4d5e6f7a8b9c"
down_revision: Union[str, None] = "3c4d5e6f7a8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("workspace_deletions", sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), primary_key=True), sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False), sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False), sa.Column("eligible_for_purge_at", sa.DateTime(timezone=True), nullable=False), sa.Column("cancelled_at", sa.DateTime(timezone=True)), sa.Column("purged_at", sa.DateTime(timezone=True)))
    op.create_index("ix_workspace_deletions_eligible_for_purge_at", "workspace_deletions", ["eligible_for_purge_at"])
    op.create_table("copyright_cases", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("reporter_name", sa.String(), nullable=False), sa.Column("reporter_email", sa.String(), nullable=False), sa.Column("work_description", sa.Text(), nullable=False), sa.Column("location", sa.String(), nullable=False), sa.Column("statement", sa.Text(), nullable=False), sa.Column("status", sa.String(), nullable=False, server_default="received"), sa.Column("internal_notes", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_copyright_cases_status", "copyright_cases", ["status"])
    op.create_table("workspace_exports", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False), sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("downloaded_at", sa.DateTime(timezone=True)))
    op.create_index("ix_workspace_exports_tenant_id", "workspace_exports", ["tenant_id"])
    op.create_table("marketing_preferences", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False), sa.Column("email", sa.String(), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("source", sa.String(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.UniqueConstraint("tenant_id", "email", name="uq_marketing_preferences_tenant_email"))
    op.create_index("ix_marketing_preferences_tenant_id", "marketing_preferences", ["tenant_id"])
    op.create_table("marketing_unsubscribe_tokens", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False), sa.Column("email", sa.String(), nullable=False), sa.Column("token_hash", sa.String(), nullable=False, unique=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))


def downgrade() -> None:
    op.drop_table("marketing_unsubscribe_tokens")
    op.drop_index("ix_marketing_preferences_tenant_id", table_name="marketing_preferences")
    op.drop_table("marketing_preferences")
    op.drop_index("ix_workspace_exports_tenant_id", table_name="workspace_exports")
    op.drop_table("workspace_exports")
    op.drop_index("ix_copyright_cases_status", table_name="copyright_cases")
    op.drop_table("copyright_cases")
    op.drop_index("ix_workspace_deletions_eligible_for_purge_at", table_name="workspace_deletions")
    op.drop_table("workspace_deletions")
