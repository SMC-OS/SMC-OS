"""get_current_user — reusable FastAPI dependency.

Not applied to any existing route in Sprint 003 (confirmed scope decision —
see docs/DECISIONS.md). Sprint 004/006/007/008 attach it to routes with
Depends(get_current_user) once there's real per-user data worth protecting.

Sprint 009 — the token now must carry a `tenant_id` claim (not just `sub`).
A token missing it (i.e. any token issued before this sprint) is rejected
the same way a missing/invalid token is — a clean cutover, not a dual-mode
shim (see app/auth/security.py's docstring). The DB row fetched below is
still the actual source of truth for `user.tenant_id`; the claim is only
validated for shape here, not substituted for the DB value.

Sprint 010 — adds require_role(), a permission-checking dependency built
on top of get_current_user. Not attached to any route yet: every user in
the system today is a UserRole.OWNER (Sprint 011's invitations are what
first make a Staff user possible), so there is nothing a role check could
meaningfully restrict yet. Shipped as inert machinery — same "ship it,
prove it doesn't break anything, enforce later" shape as this file's own
Sprint 003 -> Sprint 004 history. See docs/DECISIONS.md's new ADR and
docs/SPRINTS/sprint-010.md.

Sprint 012 (ADR-029) — adds get_current_user_optional, used only by
POST /api/v1/quote and /estimate (app/api/v1/core.py), which stay
deliberately public (ADR-023) but now tag a created Quote with the
caller's tenant_id when a valid token happens to be present. Unlike
get_current_user, a missing/invalid/expired token is not an error here —
it just means "anonymous," returning None instead of raising 401.

Sprint 015 (docs/DECISIONS.md ADR-031) — get_current_user now also rejects
a token whose user has been deactivated (is_active = False), with the same
generic "Could not validate credentials" 401 — no detail leak distinguishing
"deactivated" from "invalid/expired." This costs no extra query: the row is
already fetched below. The first sprint where another user's action (an
Owner deactivating them) can end a Staff user's already-issued, unexpired
session mid-flight — previously only natural token expiry did.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.auth.security import decode_access_token
from app.core.config import settings
from app.database import crud
from app.database.database import get_db
from app.database.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_error
    try:
        payload = decode_access_token(token)
        user_uuid = uuid.UUID(payload["sub"])
        uuid.UUID(payload["tenant_id"])  # present and well-formed; DB row is authoritative
    except (jwt.PyJWTError, ValueError, KeyError):
        raise credentials_error

    user = crud.get_user_by_id(db, user_uuid)
    if user is None or not user.is_active:
        raise credentials_error
    # Sprint 039 Production Readiness Defect Gate, Blocker 2 — a password
    # reset sets token_valid_after; any token issued before that instant
    # is rejected here even if it hasn't otherwise expired (see
    # app/auth/security.py's create_access_token). Deliberately NOT a
    # blanket "iat is now required" cutover the way tenant_id's claim
    # was (this file's own Sprint 009 precedent) — that would force
    # every already-signed-in production user to re-authenticate the
    # moment this migration deploys, not just the ones who actually
    # reset a password. `token_valid_after` stays NULL until a user's
    # first real reset (see that column's own migration docstring), so
    # this branch is unreachable for every existing session today; a
    # token that reaches here missing `iat` only after a real reset has
    # happened is rejected, since it can't prove it was issued after it.
    if user.token_valid_after is not None:
        issued_at = payload.get("iat")
        if issued_at is None:
            raise credentials_error
        issued_at_dt = datetime.fromtimestamp(issued_at, tz=timezone.utc)
        if issued_at_dt < user.token_valid_after:
            raise credentials_error
    return user


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User | None:
    """Like get_current_user, but never raises — a missing, malformed, or
    expired token just means "anonymous" (returns None) rather than a 401.

    Only for routes that are genuinely allowed to be called without auth
    but want to opportunistically attribute the action to a tenant when a
    valid token happens to be presented (Sprint 012, ADR-029)."""
    if token is None:
        return None
    try:
        payload = decode_access_token(token)
        user_uuid = uuid.UUID(payload["sub"])
        uuid.UUID(payload["tenant_id"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
    return crud.get_user_by_id(db, user_uuid)


def require_role(*allowed_roles: UserRole):
    """Dependency factory — returns a FastAPI dependency that only lets a
    request through if the current user's role is one of `allowed_roles`.

    Not wired into any route in Sprint 010 (see this module's docstring).
    Rejects with 403, not 401: reaching this check means the token was
    already valid (get_current_user succeeded), so the failure is "not
    authorized for this action," not "not authenticated."
    """

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in {role.value for role in allowed_roles}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return checker


def require_verified_email(current_user: User = Depends(get_current_user)) -> User:
    """Sprint 039 Production Readiness Defect Gate, Blocker 1 — blocks a
    sensitive action for a user whose email is unverified, unless the
    legacy grace period covers them.

    A user is exempt (never blocked) when EITHER:
    - `email_verified_at` is set (they verified), OR
    - they were created before `settings.identity_security_cutover_at`
      (a fixed instant, not "now" — see that setting's own docstring) AND
      today is still within `legacy_verification_grace_days` of that same
      fixed instant.

    A user created *after* the cutover gets no grace at all — they were
    always required to verify, from day one of this feature's existence.
    Only ever attached to specific routes considered sensitive today
    (see app/invitations/router.py); it deliberately does not gate every
    route in the app, to avoid locking out an entire existing tenant the
    moment this migration deploys.
    """
    if current_user.email_verified_at is not None:
        return current_user

    cutover = settings.identity_security_cutover_at
    grace_ends_at = cutover + timedelta(days=settings.legacy_verification_grace_days)
    is_legacy = current_user.created_at < cutover
    if is_legacy and datetime.now(timezone.utc) < grace_ends_at:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Please verify your email address to continue.",
    )
