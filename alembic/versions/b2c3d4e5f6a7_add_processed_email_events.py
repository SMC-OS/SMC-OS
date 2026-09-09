"""add processed_email_events

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6

Sprint 038, Phase 2. One new table, no changes to existing ones.

Idempotency ledger for the Resend webhook (`POST /api/v1/communications/
webhook`), the exact same shape as `processed_stripe_events`
(Sprint 032): `id` is the webhook delivery's own unique id (the `svix-id`
header — Resend's webhooks are delivered via Svix, which guarantees
at-least-once delivery and expects the receiver to dedupe on that id), so
a second delivery of the same event fails on the existing-row PK rather
than needing a separate SELECT-then-INSERT race window.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processed_email_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("processed_email_events")
