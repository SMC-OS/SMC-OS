"""add automations, automation_runs and tasks

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8

Sprint 036, Workstream G. Three new tables, no changes to existing ones.

`tasks` is one table serving four callers rather than four near-identical
ones: the task foundation under a Project (Workstream F), the automation
engine's create_task/draft_message actions (G), "tasks requiring
attention" on Dashboard V2 (C), and dated items on the Calendar (K).

`automations.conditions` and `automations.actions` are JSONB — the first
JSON columns in this schema. The normalised alternative (two child tables)
was rejected because both are always read and written whole, as a complete
rule, and are never queried into or joined against. Their shape is
validated at the Pydantic boundary on every write, so nothing unvalidated
reaches the column. JSONB rather than JSON so a future "which automations
use action X" query is possible without a migration.

Idempotency is enforced by the database, not merely attempted in code:
`tasks.dedupe_key` and `automation_runs.dedupe_key` are both UNIQUE. This
is the same defence-in-depth Sprint 024 established for
notifications.dedupe_key — the pre-check avoids the common case, the
constraint makes a concurrent double-fire impossible rather than unlikely.
Postgres treats multiple NULLs in a UNIQUE column as distinct, so
hand-created tasks (which set no key) are unconstrained.

Every table carries a NOT NULL tenant_id with an index, matching the
isolation posture ADR-029 locked in: there is no such thing as a
cross-tenant or tenant-less automation, run or task.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "assigned_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dedupe_key", sa.String(), nullable=True, unique=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tasks_tenant_id", "tasks", ["tenant_id"])
    op.create_index("ix_tasks_assigned_user_id", "tasks", ["assigned_user_id"])
    op.create_index("ix_tasks_due_at", "tasks", ["due_at"])

    op.create_table(
        "automations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("template_key", sa.String(), nullable=True),
        sa.Column("trigger_type", sa.String(), nullable=False),
        sa.Column(
            "conditions", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column("actions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_automations_tenant_id", "automations", ["tenant_id"])
    op.create_index("ix_automations_trigger_type", "automations", ["trigger_type"])

    op.create_table(
        "automation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "automation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automations.id"),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.String(), nullable=False),
        sa.Column("subject_type", sa.String(), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_automation_runs_dedupe_key"),
    )
    op.create_index("ix_automation_runs_tenant_id", "automation_runs", ["tenant_id"])
    op.create_index(
        "ix_automation_runs_automation_id", "automation_runs", ["automation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_automation_runs_automation_id", table_name="automation_runs")
    op.drop_index("ix_automation_runs_tenant_id", table_name="automation_runs")
    op.drop_table("automation_runs")

    op.drop_index("ix_automations_trigger_type", table_name="automations")
    op.drop_index("ix_automations_tenant_id", table_name="automations")
    op.drop_table("automations")

    op.drop_index("ix_tasks_due_at", table_name="tasks")
    op.drop_index("ix_tasks_assigned_user_id", table_name="tasks")
    op.drop_index("ix_tasks_tenant_id", table_name="tasks")
    op.drop_table("tasks")
