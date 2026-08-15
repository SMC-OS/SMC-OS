"""add invitations table

Sprint 011 (docs/DECISIONS.md ADR-028) — first table enabling more than
one user per tenant. Schema only; app/invitations/ (service+router) is
what actually creates/reads rows here. Constraints are explicitly named
(autogenerate proposed unnamed ones, same reason as 153159b9f28d) so the
downgrade below is exact, not guessed. No data backfill needed — new
table, zero existing rows. See app/database/models.py's Invitation
docstring for why "expired" isn't a stored status.

Revision ID: 7aedf0956cff
Revises: c28dd4348080
Create Date: 2026-08-14 00:37:36.179731

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7aedf0956cff'
down_revision: Union[str, None] = 'c28dd4348080'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'invitations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('invited_by_user_id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
        sa.ForeignKeyConstraint(
            ['tenant_id'], ['tenants.id'], name='fk_invitations_tenant_id_tenants'
        ),
        sa.ForeignKeyConstraint(
            ['invited_by_user_id'], ['users.id'], name='fk_invitations_invited_by_user_id_users'
        ),
    )


def downgrade() -> None:
    op.drop_table('invitations')
