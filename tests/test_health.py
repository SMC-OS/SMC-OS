"""Route-mount smoke tests — catches a missed router mount during the
Sprint 003 /api/v1 restructuring, and confirms the old unprefixed paths
were actually cut over, not left as a dual-mount leftover.
"""


def test_root(client):
    assert client.get("/").status_code == 200


def test_health(client):
    assert client.get("/health").status_code == 200


def test_dashboard_under_v1(client):
    # Sprint 012 (ADR-029): now auth-gated — 401 (not 404) still proves the
    # route is mounted under /api/v1, which is all this smoke test checks.
    assert client.get("/api/v1/dashboard").status_code == 401


def test_activity_under_v1(client):
    # Sprint 012 (ADR-029): now auth-gated — 401 (not 404) still proves the
    # route is mounted under /api/v1, which is all this smoke test checks.
    assert client.get("/api/v1/activity").status_code == 401


def test_notifications_under_v1(client):
    # Sprint 012 (ADR-029): now auth-gated — 401 (not 404) still proves the
    # route is mounted under /api/v1, which is all this smoke test checks.
    assert client.get("/api/v1/notifications").status_code == 401


def test_old_unprefixed_business_routes_are_gone(client):
    assert client.get("/quote").status_code == 404
    assert client.get("/dashboard").status_code == 404
    assert client.get("/activity").status_code == 404
    assert client.get("/notifications").status_code == 404


def test_root_welcome_message_names_the_current_platform_brand(client):
    # Sprint 035 rebrand audit: Sprint 034 renamed platform chrome to
    # GeoCore but missed the FastAPI app title and this response body —
    # both are platform-facing (OpenAPI docs, API root), never a tenant's
    # own business identity.
    body = client.get("/").json()
    assert "GeoCore" in body["message"]
    assert "Simo OS" not in body["message"]


def test_openapi_title_names_the_current_platform_brand(client):
    from app.main import app as fastapi_app

    assert fastapi_app.title == "GeoCore"
