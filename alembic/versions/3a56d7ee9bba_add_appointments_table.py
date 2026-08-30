"""add appointments table

Sprint 022 (docs/SPRINTS/sprint-022.md) — staff-scheduled site visits against
a Project. Constraints are explicitly named (autogenerate proposed unnamed
ones, same reason as 153159b9f28d/7aedf0956cff/880e12adf384) so the
downgrade below is exact, not guessed. No data backfill needed — new
table, zero existing rows.

Revision ID: 3a56d7ee9bba
Revises: d3e7a9c1f204
Create Date: 2026-08-30 22:24:44.064851

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a56d7ee9bba'
down_revision: Union[str, None] = 'd3e7a9c1f204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'appointments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(), server_default='scheduled', nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['tenant_id'], ['tenants.id'], name='fk_appointments_tenant_id_tenants'
        ),
        sa.ForeignKeyConstraint(
            ['project_id'], ['projects.id'], name='fk_appointments_project_id_projects'
        ),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'], ['users.id'], name='fk_appointments_created_by_user_id_users'
        ),
    )
    op.create_index(op.f('ix_appointments_project_id'), 'appointments', ['project_id'], unique=False)
    op.create_index(op.f('ix_appointments_tenant_id'), 'appointments', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_appointments_tenant_id'), table_name='appointments')
    op.drop_index(op.f('ix_appointments_project_id'), table_name='appointments')
    op.drop_table('appointments')
