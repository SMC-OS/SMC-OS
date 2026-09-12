"""add subscription trial columns

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7

Sprint 039 Production Readiness Defect Gate, Blocker 3.

MERGE ORDER UPDATE: this branch and the sibling Blocker 1/2 branches
(sprint-039-gate-a-email-verification, migration e1f2a3b4c5d6;
sprint-039-gate-b-password-reset, migration f2a3b4c5d6e7) were all cut
from the same base (origin/main @ 8e40039, head b2c3d4e5f6a7) and
developed in parallel per the product owner's explicit phased-branch
decision, so all three originally declared the same down_revision.
Blockers 1 and 2 merged first, in that order (PRs #28 and #29); this
migration's `Revises:` has been rebased onto Blocker 2's new head
(`f2a3b4c5d6e7`) so the migration graph stays linear — expected
sequencing friction from deliberate parallel work, not a mistake.

THE PROBLEM: production still shows the stale 2-tier £79/£149 pricing
(docs/SPRINTS/sprint-039.md, Production Readiness Defect Gate §14.3) and
has no trial concept at all — `Subscription` has no trial_start/trial_end
column, and no code path has ever created a trialing subscription
(confirmed by discovery, not assumed).

THE CHANGE: `subscriptions.trial_start` / `subscriptions.trial_end`
(both nullable timestamptz, no backfill — every existing subscription
row, including any created before this migration, keeps NULL/NULL,
correctly meaning "this was never a trial"). Populated only by
app/billing/trial.py's start_trial_if_eligible(), which creates the row
with no Stripe customer/subscription id at all — no existing tenant's
billing state is touched by this migration itself.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("trial_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "trial_end")
    op.drop_column("subscriptions", "trial_start")
