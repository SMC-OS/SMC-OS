"""add email verification foundation

Revision ID: e1f2a3b4c5d6
Revises: b2c3d4e5f6a7

Sprint 039 Production Readiness Defect Gate, Blocker 1.

THE PROBLEM: any string can be used as a signup email today and nothing
ever confirms the account owner actually controls it (docs/SPRINTS/
sprint-039.md, Production Readiness Defect Gate section, Blocker 1 —
confirmed by discovery, not assumed: app/auth/router.py's signup route
returns a valid session token immediately, no verification step exists
anywhere).

THE CHANGE:
- `users.email_verified_at` (nullable timestamptz) — NULL for every user
  that exists before this migration runs, and NULL for every *new* user
  until they actually click a verification link (this migration does not
  auto-verify anyone, including brand-new signups created moments before
  it runs). Set exactly once, by EmailVerificationService.verify().
  A NULL here does not, by itself, block anything — see
  app/auth/dependencies.py's require_verified_email() for the legacy
  grace-period logic that reads this column. No existing session is
  affected by this column's addition; get_current_user's shape is
  unchanged.
- `email_verification_tokens` — a new table, same opaque-hashed-single-
  use-token shape already used twice in this schema (Invitation.
  token_hash / PortalLink.token_hash, Sprint 011/013): token_hash
  (sha256 hex digest, unique, never the recoverable secret), user_id FK,
  expires_at, used_at (nullable, single-use marker). A dedicated table
  rather than reusing Invitation/PortalLink's shape, because this token
  authenticates "prove you own this inbox," a materially different claim
  than either of those two tables' tokens, and because a user can have
  many historical rows here (each resend) without any status/lifecycle
  overlap with Invitation.status.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_verification_tokens_user_id", table_name="email_verification_tokens"
    )
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "email_verified_at")
