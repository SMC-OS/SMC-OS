"""get_current_user — reusable FastAPI dependency for future sprints.

Not applied to any existing route in Sprint 003 (confirmed scope decision —
see docs/DECISIONS.md). Provided so a later sprint can attach it to routes
with Depends(get_current_user) once there's real per-user data worth
protecting.
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
        user_id = decode_access_token(token)
        user_uuid = uuid.UUID(user_id)
    except (jwt.PyJWTError, ValueError):
        raise credentials_error

    user = crud.get_user_by_id(db, user_uuid)
    if user is None:
        raise credentials_error
    return user
