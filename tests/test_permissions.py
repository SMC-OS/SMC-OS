"""Sprint 010 — require_role() unit tests.

require_role() isn't attached to any route yet (see app/auth/dependencies.py's
docstring), so there's no HTTP endpoint to exercise it through. It's a plain
dependency-factory function, so it's tested directly: build the inner
`checker` and call it with a hand-built User, bypassing FastAPI's dependency
injection (which would otherwise try to resolve `current_user`'s own
`Depends(get_current_user)` default).
"""

import uuid

import pytest
from fastapi import HTTPException

from app.auth.dependencies import require_role
from app.auth.models import UserRole
from app.database.models import User


def _make_user(role: str | None) -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="Permissions Test User",
        email="pytest-permissions-test@example.invalid",
        role=role,
        password_hash="irrelevant-for-this-test",
    )


def test_require_role_allows_matching_role():
    checker = require_role(UserRole.OWNER)
    user = _make_user(UserRole.OWNER.value)

    assert checker(current_user=user) is user


def test_require_role_allows_any_of_multiple_roles():
    checker = require_role(UserRole.OWNER, UserRole.STAFF)
    user = _make_user(UserRole.STAFF.value)

    assert checker(current_user=user) is user


def test_require_role_rejects_non_matching_role():
    checker = require_role(UserRole.OWNER)
    user = _make_user(UserRole.STAFF.value)

    with pytest.raises(HTTPException) as exc_info:
        checker(current_user=user)
    assert exc_info.value.status_code == 403


def test_require_role_rejects_missing_role():
    checker = require_role(UserRole.OWNER)
    user = _make_user(role=None)

    with pytest.raises(HTTPException) as exc_info:
        checker(current_user=user)
    assert exc_info.value.status_code == 403
