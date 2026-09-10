"""add pipeline_stages

Revision ID: c5d6e7f8a9b0
Revises: b2c3d4e5f6a7

Sprint 039, Workstream D. One new table, and a data seed that **rewrites
no existing row**.

`projects.status` is not touched. Not one `UPDATE projects` runs here.
Sprint 006's stone-shaped pipeline (`enquiry → quoted → booked →
templated → fabricated → installed → complete`) survives verbatim as the
`stone` template, and every tenant that exists at the moment this
migration runs is seeded with exactly those stage keys — so every
in-flight job stays on precisely the stage it was already on, and the
downgrade is a plain DROP TABLE with nothing to reverse.

What makes the product trade-neutral anyway is the `role` column: each
legacy stage records the neutral meaning it always had (`templated`,
`fabricated` and `installed` are all simply "work is under way"), and
every consumer switches to counting roles rather than stage keys. Tenants
created *after* this migration are seeded with the trade-neutral
`standard` template by the application (app/tenants/service.py), so stone
vocabulary stops being GeoCore's default identity from here on.

`LEGACY_STONE_STAGES` below is a deliberate, frozen copy of
app/projects/pipeline.py's `stone` template rather than an import of it.
A migration must never import application code that can change under it —
this file has to keep producing the same rows in five years' time.
tests/test_project_pipeline_config.py asserts the copy still matches, so
the duplication cannot drift silently.
"""

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: (key, label, role, position) — the frozen snapshot described above.
LEGACY_STONE_STAGES: tuple[tuple[str, str, str, int], ...] = (
    ("enquiry", "Enquiry", "lead", 0),
    ("quoted", "Quoted", "quoted", 1),
    ("booked", "Booked", "approved", 2),
    ("templated", "Templated", "in_progress", 3),
    ("fabricated", "Fabricated", "in_progress", 4),
    ("installed", "Installed", "in_progress", 5),
    ("complete", "Complete", "completed", 6),
    ("on_hold", "On hold", "on_hold", 7),
    ("cancelled", "Cancelled", "cancelled", 8),
)


def upgrade() -> None:
    op.create_table(
        "pipeline_stages",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        # ON DELETE CASCADE, unlike every other tenant FK in this schema.
        # This table holds regenerable configuration, not business records:
        # see PipelineStage's own docstring for why blocking a tenant
        # delete on it would protect nothing.
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("template_key", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "key", name="uq_pipeline_stages_tenant_key"),
    )
    op.create_index(
        "ix_pipeline_stages_tenant_id", "pipeline_stages", ["tenant_id"], unique=False
    )

    _seed_existing_tenants()


def _seed_existing_tenants() -> None:
    """Give every tenant that already exists the legacy stone pipeline.

    Ids are generated here in Python rather than by a DB default because
    the table has none — the application supplies ids everywhere else in
    this schema too, and adding a `gen_random_uuid()` default just for
    this migration would leave a column default behind that nothing else
    relies on.
    """
    connection = op.get_bind()
    tenant_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM tenants"))]
    if not tenant_ids:
        return

    insert = sa.text(
        """
        INSERT INTO pipeline_stages
            (id, tenant_id, key, label, role, position, template_key)
        VALUES
            (:id, :tenant_id, :key, :label, :role, :position, 'stone')
        """
    )
    connection.execute(
        insert,
        [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "key": key,
                "label": label,
                "role": role,
                "position": position,
            }
            for tenant_id in tenant_ids
            for (key, label, role, position) in LEGACY_STONE_STAGES
        ],
    )


def downgrade() -> None:
    # Genuinely safe: this migration created rows only in the table being
    # dropped, and changed nothing anywhere else.
    op.drop_index("ix_pipeline_stages_tenant_id", table_name="pipeline_stages")
    op.drop_table("pipeline_stages")
