"""add notification recipient and source fields

Sprint 024 (docs/SPRINTS/sprint-024.md) — extends NotificationRecord for
per-user targeted, source-linked, deduplicated automated notifications.
All four columns are nullable; existing tenant-wide broadcast rows need
no backfill. Constraints are explicitly named (autogenerate proposed
unnamed ones, same reason as every prior new-column migration in this
repo, e.g. 081460e0e63a) so the downgrade below is exact, not guessed.

Revision ID: 2243d66f83da
Revises: 081460e0e63a
Create Date: 2026-08-31 05:36:18.844525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2243d66f83da'
down_revision: Union[str, None] = '081460e0e63a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('notifications', sa.Column('recipient_user_id', sa.UUID(), nullable=True))
    op.add_column('notifications', sa.Column('source_type', sa.String(), nullable=True))
    op.add_column('notifications', sa.Column('source_id', sa.UUID(), nullable=True))
    op.add_column('notifications', sa.Column('dedupe_key', sa.String(), nullable=True))
    op.create_index(
        op.f('ix_notifications_recipient_user_id'), 'notifications', ['recipient_user_id'], unique=False
    )
    op.create_unique_constraint('uq_notifications_dedupe_key', 'notifications', ['dedupe_key'])
    op.create_foreign_key(
        'fk_notifications_recipient_user_id_users',
        'notifications', 'users', ['recipient_user_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_notifications_recipient_user_id_users', 'notifications', type_='foreignkey')
    op.drop_constraint('uq_notifications_dedupe_key', 'notifications', type_='unique')
    op.drop_index(op.f('ix_notifications_recipient_user_id'), table_name='notifications')
    op.drop_column('notifications', 'dedupe_key')
    op.drop_column('notifications', 'source_id')
    op.drop_column('notifications', 'source_type')
    op.drop_column('notifications', 'recipient_user_id')
