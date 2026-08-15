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
