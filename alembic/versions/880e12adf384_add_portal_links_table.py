"""add portal_links table

Sprint 013 (docs/DECISIONS.md ADR-030) — read-only client portal. Schema
only; app/portal/ (service+router) is what actually creates/reads rows
here. Constraints are explicitly named (autogenerate proposed unnamed
ones, same reason as 153159b9f28d/7aedf0956cff) so the downgrade below is
exact, not guessed. No data backfill needed — new table, zero existing
rows. See app/database/models.py's PortalLink docstring for why "expired"
isn't a stored status, and why there's no "accepted" state (unlike
Invitation, a portal link is reusable, not single-use).

Revision ID: 880e12adf384
Revises: a8d91098a01e
Create Date: 2026-08-15 07:02:30.983233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '880e12adf384'
down_revision: Union[str, None] = 'a8d91098a01e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'portal_links',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='active', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
        sa.ForeignKeyConstraint(
            ['tenant_id'], ['tenants.id'], name='fk_portal_links_tenant_id_tenants'
        ),
        sa.ForeignKeyConstraint(
            ['customer_id'], ['customers.id'], name='fk_portal_links_customer_id_customers'
        ),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'], ['users.id'], name='fk_portal_links_created_by_user_id_users'
        ),
    )


def downgrade() -> None:
    op.drop_table('portal_links')
