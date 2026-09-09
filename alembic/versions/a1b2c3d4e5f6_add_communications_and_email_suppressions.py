"""add communications and email_suppressions

Revision ID: a1b2c3d4e5f6
Revises: d5e6f7a8b9c0

Sprint 038, Phase 1. Two new tables, no changes to existing ones.

`communications` is the outbound-email audit ledger — named `Communication`/
`communications` rather than `Message`/`messages`, because that name and
table are already taken by the Sprint 017 (ADR-033) portal chat feature.
This is a different thing entirely: one row per attempted transmission out
of the platform (invitation, quote, follow-up, project update, review
request), not a conversation thread.

Idempotency is enforced by the database, not merely attempted in code, same
defence-in-depth pattern as `tasks.dedupe_key`/`automation_runs.dedupe_key`
(Sprint 036): `communications` gets a UNIQUE(tenant_id, dedupe_key)
constraint rather than a global-unique column, since a dedupe key like
"invitation:<id>" is only meaningful scoped to its own tenant.

`email_suppressions` is tenant-scoped rather than global — one tenant's
customer hard-bouncing does not affect another tenant's ability to email
that same address, matching every other per-tenant isolation boundary in
this schema. UNIQUE(tenant_id, email) so a suppression can only exist once
per tenant.

Every table carries a NOT NULL tenant_id with an index. No column on
either table ever stores an API key, token, or other credential — see
docs/SPRINTS/sprint-038.md §5 for the full design rationale.

Every nullable subject FK on `communications` (customer/quote/project/
invitation/automation/automation_run) is `ondelete="SET NULL"` — this is
an audit ledger, and a hard-deleted subject row (which today only happens
from test cleanup SQL, never a product code path) must not be blocked by
a dangling FK, nor take the communication history down with it.
`email_suppressions.source_communication_id` gets the same treatment for
the same reason. `tenant_id` on both tables deliberately does not — no
code path, test or product, hard-deletes a Tenant row.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "quote_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quotes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "invitation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invitations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "automation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "automation_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automation_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel", sa.String(), nullable=False, server_default="email"),
        sa.Column("direction", sa.String(), nullable=False, server_default="outbound"),
        sa.Column("message_type", sa.String(), nullable=False),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("sender_identity", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("provider_message_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_category", sa.String(), nullable=True),
        sa.Column("failure_detail", sa.String(), nullable=True),
        sa.Column("dedupe_key", sa.String(), nullable=False),
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
        sa.UniqueConstraint(
            "tenant_id", "dedupe_key", name="uq_communications_tenant_dedupe_key"
        ),
    )
    op.create_index("ix_communications_tenant_id", "communications", ["tenant_id"])
    op.create_index("ix_communications_customer_id", "communications", ["customer_id"])
    op.create_index("ix_communications_quote_id", "communications", ["quote_id"])
    op.create_index("ix_communications_project_id", "communications", ["project_id"])
    op.create_index("ix_communications_invitation_id", "communications", ["invitation_id"])
    op.create_index("ix_communications_automation_id", "communications", ["automation_id"])
    op.create_index(
        "ix_communications_automation_run_id", "communications", ["automation_run_id"]
    )
    op.create_index(
        "ix_communications_provider_message_id", "communications", ["provider_message_id"]
    )
    op.create_index("ix_communications_status", "communications", ["status"])

    op.create_table(
        "email_suppressions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column(
            "source_communication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("communications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "email", name="uq_email_suppressions_tenant_email"),
    )
    op.create_index("ix_email_suppressions_tenant_id", "email_suppressions", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_email_suppressions_tenant_id", table_name="email_suppressions")
    op.drop_table("email_suppressions")

    op.drop_index("ix_communications_status", table_name="communications")
    op.drop_index("ix_communications_provider_message_id", table_name="communications")
    op.drop_index("ix_communications_automation_run_id", table_name="communications")
    op.drop_index("ix_communications_automation_id", table_name="communications")
    op.drop_index("ix_communications_invitation_id", table_name="communications")
    op.drop_index("ix_communications_project_id", table_name="communications")
    op.drop_index("ix_communications_quote_id", table_name="communications")
    op.drop_index("ix_communications_customer_id", table_name="communications")
    op.drop_index("ix_communications_tenant_id", table_name="communications")
    op.drop_table("communications")
