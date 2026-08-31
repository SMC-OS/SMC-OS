"""Sprint 026 Contract C — security response headers on every response.

Reuses the make_development_settings/make_production_settings helpers from
tests/test_runtime_http.py (same pattern already used by that file's own
production-vs-development assertions) rather than duplicating them.
"""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_runtime_http import make_development_settings, make_production_settings


def test_security_headers_present_on_a_normal_response():
    application = create_app(make_development_settings())
    client = TestClient(application)

    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_security_headers_present_on_an_error_response():
    application = create_app(make_development_settings())
    client = TestClient(application)

    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_hsts_present_in_production(tmp_path):
    application = create_app(make_production_settings(tmp_path))
    with TestClient(application) as client:
        response = client.get("/health")

    assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"


def test_hsts_absent_outside_production():
    application = create_app(make_development_settings())
    client = TestClient(application)

    response = client.get("/health")

    assert "strict-transport-security" not in response.headers
