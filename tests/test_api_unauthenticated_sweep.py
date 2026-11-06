"""Phase 4 — every API operation, called with no credentials and unknown ids,
must deny without data and without a server error. The only operations that
may answer 2xx anonymously are listed here on purpose; a new route that does
so, or that crashes, fails this test until it is reviewed."""

import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Intentionally public and data-free (or the caller's own session ending).
ANONYMOUS_SUCCESS_ALLOWED = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/api/v1/auth/admission"),
    ("GET", "/api/v1/billing/plans"),
    ("POST", "/api/v1/auth/logout"),
}

# Public by design (sign-in, public forms, anonymous quoting, token links,
# internal-token operations). Without valid input or a valid token they must
# refuse with a 4xx that reveals nothing.
PUBLIC_BY_DESIGN = re.compile(
    r"^/api/v1/(auth/(login|signup|password/(forgot|reset)|email/verify/confirm)"
    r"|compliance/copyright-reports|compliance/internal/.*|demo-requests|estimate|process|quote"
    r"|invitations/token/.*|portal-links/token/.*|privacy/marketing-unsubscribe/.*"
    r"|privacy/internal/.*)$"
)


def _operations():
    for path, ops in sorted(app.openapi()["paths"].items()):
        for method in ops:
            yield method.upper(), path


@pytest.fixture(scope="module")
def anonymous():
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("method,path", list(_operations()))
def test_anonymous_call_is_denied_without_data_or_error(anonymous, method, path):
    url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
    response = anonymous.request(method, url, json={} if method in {"POST", "PUT", "PATCH"} else None)
    assert response.status_code < 500, f"{method} {path} -> {response.status_code}"
    if (method, path) in ANONYMOUS_SUCCESS_ALLOWED:
        return
    assert response.status_code >= 400, f"{method} {path} answered {response.status_code} without credentials"
    if PUBLIC_BY_DESIGN.match(path):
        assert response.status_code in {400, 401, 403, 404, 422}, f"{method} {path} -> {response.status_code}"
    else:
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}, expected 401"
