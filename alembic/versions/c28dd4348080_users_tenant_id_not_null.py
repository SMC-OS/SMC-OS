"""users tenant_id not null

Sprint 009 (docs/DECISIONS.md new ADR) — users.tenant_id becomes NOT NULL,
the first column to actually enforce Sprint 008's FK (ADR-025). Any
existing user row with tenant_id IS NULL (the pre-Sprint-009 seeded owner
account, created before tenants existed) is backfilled to a brand-new
"Default Workspace" tenant before the constraint is added, so no existing
account is orphaned or broken by this migration. On a fresh database
(nothing seeded yet, e.g. a clean CI run) there are zero NULL rows and the
backfill block is a no-op — the app's own seed_users() creates a tenant via
AuthService.signup() the normal way once it starts.

Revision ID: c28dd4348080
Revises: 153159b9f28d
Create Date: 2026-08-13 19:07:24.968923

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c28dd4348080'
down_revision: Union[str, None] = '153159b9f28d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    orphaned = conn.execute(sa.text("SELECT id FROM users WHERE tenant_id IS NULL")).fetchall()
    if orphaned:
        tenant_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO tenants (id, name, slug, status, created_at) "
                "VALUES (:id, :name, :slug, 'active', now())"
            ),
            {"id": tenant_id, "name": "Default Workspace", "slug": "default-workspace"},
        )
        conn.execute(
            sa.text("UPDATE users SET tenant_id = :tid WHERE tenant_id IS NULL"),
            {"tid": tenant_id},
        )
    op.alter_column("users", "tenant_id", existing_type=sa.UUID(), nullable=False)


def downgrade() -> None:
    op.alter_column("users", "tenant_id", existing_type=sa.UUID(), nullable=True)
