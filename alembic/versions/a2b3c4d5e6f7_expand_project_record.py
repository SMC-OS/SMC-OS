"""expand project record (site address, type, dates, value)

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6

Sprint 036, Workstream F. A project was name + optional customer + notes +
status. A construction job needs to know where it is, what kind of work it
is, when it starts, when it is due, and what it is worth — none of which
had anywhere to live.

All additive and all nullable, so every existing project stays valid with
no backfill, and the existing POST /api/v1/projects body
({name, customer_id, notes}) keeps working unchanged — which the
quote-handoff path (Sprint 020) and several E2E specs depend on.

Two deliberate type choices:

  * `start_date` / `target_completion_date` are DATE, not TIMESTAMP. A job
    starts on a day. Storing 00:00 in some arbitrary timezone would make
    the "project starts tomorrow" automation's answer depend on the
    server's clock offset rather than on the calendar.
  * `estimated_value` is a plain float, consistent with every other money
    column in this schema (quotes.total, materials.price). Introducing
    NUMERIC here alone would create two money representations in one
    database, which is worse than one imperfect one; migrating all of them
    together is a separate, deliberate piece of work.

This migration adds no index. `start_date` is scanned by the automation
job across a tenant's own (small) project set, already filtered by
tenant_id, which is indexed. An index here would be speculative.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (name, type) pairs rather than pre-built sa.Column objects: a Column
# instance can only be attached to one table once, so building them here
# and reusing them would break on a re-run.
_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("project_type", sa.String()),
    ("description", sa.Text()),
    ("site_address_line1", sa.String()),
    ("site_address_line2", sa.String()),
    ("site_city", sa.String()),
    ("site_postcode", sa.String()),
    ("start_date", sa.Date()),
    ("target_completion_date", sa.Date()),
    ("estimated_value", sa.Float()),
)


def upgrade() -> None:
    for name, column_type in _COLUMNS:
        op.add_column("projects", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("projects", name)
