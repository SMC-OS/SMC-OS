"""add project assigned_user_id

Sprint 023 (docs/SPRINTS/sprint-023.md) — responsible Staff/Owner member
for a Project, nullable (most historical/pre-booking Projects have none).
Constraint is explicitly named (autogenerate proposed an unnamed one, same
reason as every prior new-column/table migration in this repo, e.g.
3a56d7ee9bba) so the downgrade below is exact, not guessed.

Revision ID: 081460e0e63a
Revises: 3a56d7ee9bba
Create Date: 2026-08-31 03:11:37.604223

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '081460e0e63a'
down_revision: Union[str, None] = '3a56d7ee9bba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('assigned_user_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_projects_assigned_user_id'), 'projects', ['assigned_user_id'], unique=False)
    op.create_foreign_key(
        'fk_projects_assigned_user_id_users', 'projects', 'users', ['assigned_user_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_projects_assigned_user_id_users', 'projects', type_='foreignkey')
    op.drop_index(op.f('ix_projects_assigned_user_id'), table_name='projects')
    op.drop_column('projects', 'assigned_user_id')
