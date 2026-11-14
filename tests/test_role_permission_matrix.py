"""Role permission matrix: every API operation, called as Owner and as Staff of one workspace.

The matrix is a committed snapshot (tests/data/role_matrix.json). It does not decide what the
roles *should* be able to do; it records what the API actually does, so that

* an unreviewed change in who can call an operation fails this test, and
* the owner can review the table once (which operations a Staff user may call) instead of the
  question staying UNKNOWN.

Outcome classes: "forbidden" (403), "unauthenticated" (401), "allowed" (anything else below
500: the request passed authorisation, even if it then 404s or 422s on dummy input).
Regenerate after an intended change with UPDATE_ROLE_MATRIX=1 and review the diff.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import SignupRequest
from app.auth.service import auth_service
from app.auth.security import create_access_token
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import User
from app.main import app

SNAPSHOT = Path(__file__).parent / "data" / "role_matrix.json"
# Session/credential operations change the caller's own token and are covered elsewhere;
# the Stripe webhook is authenticated by signature, not by a user.
SKIP = re.compile(r"^/api/v1/(auth/.*|billing/webhook.*)$|^/(health|ready|docs|redoc|openapi.json)?$")


def operations():
    for path, ops in sorted(app.openapi()["paths"].items()):
        for method in sorted(ops):
            if not SKIP.match(path):
                yield method.upper(), path


def outcome(status: int, path: str) -> str:
    if status == 503 and path.startswith("/api/v1/billing/"):
        return "allowed"  # authorised, but billing is deliberately unavailable when Stripe is not configured
    return {401: "unauthenticated", 403: "forbidden"}.get(status, "allowed" if status < 500 else f"SERVER-ERROR-{status}")


@pytest.fixture(scope="module")
def workspace():
    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        tenant, owner = auth_service.signup(
            db, SignupRequest(company_name=f"Matrix {tag}", name="Matrix Owner", email=f"matrix-owner-{tag}@acceptance.invalid",
                              password="Matrix-Passw0rd-" + tag)
        )
        owner.email_verified_at = datetime.now(timezone.utc)
        staff = crud.create_user(db, id=uuid.uuid4(), tenant_id=tenant.id, name="Matrix Staff", email=f"matrix-staff-{tag}@acceptance.invalid",
                                 password_hash=owner.password_hash, role="Staff", email_verified_at=datetime.now(timezone.utc))
        db.commit()
        tokens = {
            role: {"Authorization": "Bearer " + create_access_token(subject=str(u.id), tenant_id=str(u.tenant_id), token_version=u.token_version)}
            for role, u in (("owner", owner), ("staff", staff))
        }
    finally:
        db.close()
    yield tokens


def observe(workspace):
    matrix = {}
    with TestClient(app, raise_server_exceptions=False) as client:
        for method, path in operations():
            url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
            row = {}
            for role in ("staff", "owner"):  # staff first: a destructive owner call must not mask it
                r = client.request(method, url, json={} if method in {"POST", "PUT", "PATCH"} else None, headers=workspace[role])
                row[role] = outcome(r.status_code, path)
            matrix[f"{method} {path}"] = row
    return matrix


def test_role_matrix_matches_the_reviewed_snapshot(workspace):
    matrix = observe(workspace)
    errors = {k: v for k, v in matrix.items() if any(x.startswith("SERVER-ERROR") for x in v.values())}
    assert not errors, f"server errors: {errors}"
    assert not {k for k, v in matrix.items() if "unauthenticated" in v.values()}, "a valid session was treated as unauthenticated"
    if os.environ.get("UPDATE_ROLE_MATRIX") == "1":
        SNAPSHOT.write_text(json.dumps(matrix, indent=1, sort_keys=True) + "\n")
    expected = json.loads(SNAPSHOT.read_text())
    changed = {k: {"was": expected.get(k), "now": matrix.get(k)} for k in sorted(set(expected) | set(matrix)) if expected.get(k) != matrix.get(k)}
    assert not changed, f"role behaviour changed (review, then UPDATE_ROLE_MATRIX=1): {json.dumps(changed, indent=1)}"


def test_staff_never_outranks_owner(workspace):
    matrix = json.loads(SNAPSHOT.read_text())
    inverted = [k for k, v in matrix.items() if v["staff"] == "allowed" and v["owner"] == "forbidden"]
    assert not inverted, f"Staff may call operations the Owner may not: {inverted}"
