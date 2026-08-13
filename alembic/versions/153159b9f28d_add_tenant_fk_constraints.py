"""add tenant fk constraints

Sprint 008 (docs/DECISIONS.md ADR-025) — second of two revisions. Converts
the 7 existing tenant_id columns (added inert in Sprint 002, ADR-013) into
real foreign keys against the tenants table created by the prior revision.
Column type/nullability is unchanged — still a nullable UUID on every
table; every existing row already has tenant_id = NULL, which is always
valid against a nullable FK, so this needs no data backfill. Constraints
are explicitly named (autogenerate proposed unnamed ones, which makes
`downgrade()` unreliable) so the downgrade below is exact, not guessed.

Revision ID: 153159b9f28d
Revises: f7041a28f140
Create Date: 2026-08-13 00:30:43.242649

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '153159b9f28d'
down_revision: Union[str, None] = 'f7041a28f140'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = [
    "activity_log",
    "customers",
    "materials",
    "notifications",
    "projects",
    "quotes",
    "users",
]


def _fk_name(table: str) -> str:
    return f"fk_{table}_tenant_id_tenants"


def upgrade() -> None:
    for table in _TABLES:
        op.create_foreign_key(
            _fk_name(table), table, "tenants", ["tenant_id"], ["id"]
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_constraint(_fk_name(table), table, type_="foreignkey")
