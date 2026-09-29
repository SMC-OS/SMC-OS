"""Fail-closed authentication for server-to-server compliance work."""
import secrets

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_internal_compliance_auth(
    x_geocore_internal_token: str | None = Header(default=None),
) -> None:
    configured = settings.internal_compliance_token
    if not configured or len(configured) < 32 or not x_geocore_internal_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal operation unavailable")
    if not secrets.compare_digest(configured, x_geocore_internal_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal operation unavailable")
