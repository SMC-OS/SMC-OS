"""add tenant_id indexes for isolation

Revision ID: a8d91098a01e
Revises: 7aedf0956cff
Create Date: 2026-08-15 05:46:59.010734

Sprint 012 (ADR-029) — customers, projects, quotes, activity_log, and
notifications are now filtered by tenant_id on every query (see
app/database/crud.py). This adds a plain non-unique index on tenant_id
for each of those 5 tables so the new WHERE tenant_id = :tenant_id clause
doesn't do a sequential scan. Additive only — no column changes, no data
migration, fully reversible.

Deliberately not indexed: `materials` (stays a shared, unfiltered
reference catalogue — not tenant-owned data, see ADR-029), `users` and
`invitations` (already correctly tenant-scoped since Sprint 009/011,
unchanged and untouched by this sprint), `tenants` (is the tenant, not
owned by one).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d91098a01e'
down_revision: Union[str, None] = '7aedf0956cff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_activity_log_tenant_id'), 'activity_log', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_customers_tenant_id'), 'customers', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_notifications_tenant_id'), 'notifications', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_projects_tenant_id'), 'projects', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_quotes_tenant_id'), 'quotes', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_quotes_tenant_id'), table_name='quotes')
    op.drop_index(op.f('ix_projects_tenant_id'), table_name='projects')
    op.drop_index(op.f('ix_notifications_tenant_id'), table_name='notifications')
    op.drop_index(op.f('ix_customers_tenant_id'), table_name='customers')
    op.drop_index(op.f('ix_activity_log_tenant_id'), table_name='activity_log')
