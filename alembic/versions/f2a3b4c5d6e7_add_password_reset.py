"""add password reset foundation

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6

Sprint 039 Production Readiness Defect Gate, Blocker 2.

MERGE ORDER UPDATE: this branch and the sibling Blocker 1 branch
(sprint-039-gate-a-email-verification, migration e1f2a3b4c5d6) were both
cut from the same base (origin/main @ 8e40039, head b2c3d4e5f6a7) and
developed in parallel per the product owner's explicit phased-branch
decision, so both originally declared the same down_revision. Blocker 1
merged first (PR #28, now origin/main's head); this migration's
`Revises:` has been rebased onto its new head (`e1f2a3b4c5d6`) so the
migration graph stays linear — this is expected sequencing friction from
deliberate parallel work, not a mistake in either migration.

THE PROBLEM: there is no way to recover a forgotten password anywhere in
GeoCore today (docs/SPRINTS/sprint-039.md, Production Readiness Defect
Gate §14.2 — confirmed by discovery: `app/auth/router.py` only ever
exposed `/signup`, `/login`, `/me`, and this blocker's own Blocker-1
verification routes; no `/password/forgot` or `/password/reset` route,
no reset-token table, existed before this migration).

THE CHANGE:
- `users.token_version` (integer, not null, default 0) — incremented by
  exactly 1 on every successful password reset. `get_current_user`
  rejects a JWT whose `token_version` claim doesn't match the user's
  current value, even if the token hasn't otherwise expired — this is
  how "reset revokes existing sessions" works against stateless JWTs
  with no server-side session table to delete rows from (see
  app/auth/security.py's `create_access_token` and
  app/auth/dependencies.py's `get_current_user`). Every existing user
  starts at 0, matching a token with no `token_version` claim at all
  (treated as 0 — see that dependency's own docstring for why), so no
  existing session is invalidated by this migration itself.
  Deliberately an exact integer counter, not a timestamp compared against
  JWT's `iat` claim (the first version of this migration/design) — `iat`
  is second-precision by spec (PyJWT truncates any sub-second component),
  which a real GitHub Actions CI run of the test suite proved can falsely
  reject a genuinely-fresh post-reset login issued within the same
  wall-clock second as the reset. An integer equality check has no such
  precision-loss failure mode.
- `password_reset_tokens` — a new table, same opaque-hashed-single-use
  shape as `email_verification_tokens` (Blocker 1) / `invitations` /
  `portal_links`: token_hash (sha256 hex digest, unique, never the
  recoverable secret), user_id FK, expires_at (1h — deliberately much
  shorter than email verification's 24h, since a reset token grants
  immediate account takeover if leaked, not merely "prove you own this
  inbox"), used_at (nullable, single-use marker).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "password_reset_tokens",
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
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_column("users", "token_version")
