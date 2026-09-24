"""Password hashing and JWT issuance/validation.

Sprint 003 — basic JWT auth (ADR-011). Uses bcrypt directly rather than
passlib, which has known compatibility issues with modern bcrypt releases.

Sprint 009 — the token payload gains a `tenant_id` claim (docs/DECISIONS.md
new ADR). This is a clean-cutover shape change, not a backwards-compatible
one: any token issued before this sprint has no `tenant_id` claim and is
rejected by app/auth/dependencies.py's get_current_user, same "old shape
just stops working, no dual-mode shim" precedent as ADR-012's /api/v1
cutover. The DB row (`users.tenant_id`) remains the actual source of truth
for which tenant a user belongs to — the claim is carried for cheap access
without a DB round-trip, not trusted over the DB.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.auth.password_policy import PASSWORD_TOO_LONG_MESSAGE, password_exceeds_max_bytes
from app.core.config import settings


class PasswordTooLongError(ValueError):
    """A password over bcrypt's 72-byte input limit reached the hashing
    boundary. Raised before bcrypt is called, so no other bcrypt error is
    ever reported as this one. Mapped to a 422 in app/core/errors.py."""

    def __init__(self) -> None:
        super().__init__(PASSWORD_TOO_LONG_MESSAGE)


def hash_password(password: str) -> str:
    # Never truncate: a longer password is refused, not silently shortened.
    if password_exceeds_max_bytes(password):
        raise PasswordTooLongError()
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    # No stored hash can match over-long input: bcrypt 5 (pinned since the
    # first requirements.txt) refuses to hash it, so it was never stored.
    # Answer "no match" instead of letting bcrypt raise.
    if password_exceeds_max_bytes(password):
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(subject: str, tenant_id: str, token_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    # Sprint 039 Production Readiness Defect Gate, Blocker 2 —
    # `token_version` lets get_current_user reject a token minted before
    # a password reset even if it hasn't otherwise expired (see
    # User.token_version and that dependency's docstring). An exact
    # integer equality check, not a timestamp comparison against `iat` —
    # `iat` is still included below for general JWT hygiene/debugging,
    # but is not load-bearing for revocation: a real GitHub Actions CI
    # run proved iat's second-precision truncation makes it unsuitable
    # for that (see User.token_version's migration docstring for the
    # full story of that first, wrong design).
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "token_version": token_version,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Returns the full decoded payload (`sub`, `tenant_id`, `token_version`,
    `iat`, `exp`).

    Raises jwt.PyJWTError if invalid/expired. Sprint 009 — previously
    returned just the `sub` string; now returns the whole payload since
    app/auth/dependencies.py needs `tenant_id` too (and, since Sprint 039
    Blocker 2, `token_version`).
    """
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
