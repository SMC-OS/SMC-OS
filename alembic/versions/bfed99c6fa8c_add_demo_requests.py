"""add demo_requests

Revision ID: bfed99c6fa8c
Revises: 0f93d11b04a4
Create Date: 2026-09-18 08:05:00.000000

GeoCore Premium OS, Plan 02 (Public Homepage + Request Demo + 14-Day
Trial Funnel) — public "Request a Demo" lead capture. Standalone,
platform-owned table: no `tenant_id`, no FK to any existing tenant data,
because a prospect's sales lead is GeoCore's own sales pipeline, never a
row inside a customer's CRM.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = 'bfed99c6fa8c'
down_revision: Union[str, None] = '0f93d11b04a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "demo_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("team_size", sa.String(), nullable=False),
        sa.Column("trades", JSONB(), nullable=False, server_default="[]"),
        sa.Column("current_system", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("preferred_contact_method", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="new"),
        sa.Column("source", sa.String(), nullable=False, server_default="marketing_homepage"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_demo_requests_email", "demo_requests", ["email"])


def downgrade() -> None:
    op.drop_index("ix_demo_requests_email", table_name="demo_requests")
    op.drop_table("demo_requests")
