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
"""

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
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
    if user is None:
        raise credentials_error
    return user
