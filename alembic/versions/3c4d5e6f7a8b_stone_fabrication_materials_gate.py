"""stone fabrication materials-ready workflow gate

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-09-18 16:00:00.000000

GeoCore Premium OS Plan 05 (Sprint 044), Task 27 — the one real,
data-backed workflow gate this plan adds: the system `stone_v1`
template's `fabrication` stage now carries a `materials_ready` gate
(app/workflows/gates.py), blocking entry until every one of the
project's own material requirements has actually been received.

Purely additive/configuration: this updates the `gate_definitions`
JSONB column on exactly one existing seeded system stage row (a
GeoCore-provided template, `tenant_id IS NULL`, never a tenant's own
data) — no project, quote, or tenant-owned row is touched. A tenant on
an older workflow version, or a project already bound to a prior
version of `stone_v1`, is unaffected: `workflow_stages` rows are
per-template-version and existing bindings do not move.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c4d5e6f7a8b'
down_revision: Union[str, None] = '2b3c4d5e6f7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE workflow_stages
            SET gate_definitions = CAST(:gate AS JSONB)
            WHERE key = 'fabrication'
              AND workflow_template_id IN (
                  SELECT id FROM workflow_templates
                  WHERE key = 'stone_v1' AND tenant_id IS NULL
              )
            """
        ),
        {"gate": '[{"type": "materials_ready"}]'},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE workflow_stages
            SET gate_definitions = NULL
            WHERE key = 'fabrication'
              AND workflow_template_id IN (
                  SELECT id FROM workflow_templates
                  WHERE key = 'stone_v1' AND tenant_id IS NULL
              )
            """
        )
    )
