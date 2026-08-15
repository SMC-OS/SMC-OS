"""Sprint 012 (ADR-029) — app/notifications/router.py had no auth at all
before this sprint (docs/USER_ROLES.md §1's "still true" list). No test
file existed for it either. This covers the new auth gate, tenant scoping,
and the tenant-ownership check on PATCH .../read.
"""

from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import NotificationRecord

TEST_TITLE = "Pytest Notification"
TEST_MESSAGE = "pytest-notification-message"


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(NotificationRecord).where(NotificationRecord.title == TEST_TITLE))
        db.commit()
    finally:
        db.close()


def test_notifications_routes_require_auth(client):
    assert client.get("/api/v1/notifications").status_code == 401
    assert client.get("/api/v1/notifications/unread-count").status_code == 401
    assert (
        client.post(
            "/api/v1/notifications",
            json={"title": TEST_TITLE, "message": TEST_MESSAGE},
        ).status_code
        == 401
    )
    assert client.patch("/api/v1/notifications/does-not-exist/read").status_code == 401


def test_create_and_list_notification_own_tenant(client, auth_headers):
    _cleanup()
    try:
        r = client.post(
            "/api/v1/notifications",
            json={"title": TEST_TITLE, "message": TEST_MESSAGE, "type": "info"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["title"] == TEST_TITLE

        listed = client.get("/api/v1/notifications?limit=50", headers=auth_headers)
        titles = [n["title"] for n in listed.json()]
        assert TEST_TITLE in titles
    finally:
        _cleanup()


def test_notification_not_visible_to_other_tenant(
    client, auth_headers, other_tenant_auth_headers
):
    _cleanup()
    try:
        client.post(
            "/api/v1/notifications",
            json={"title": TEST_TITLE, "message": TEST_MESSAGE},
            headers=auth_headers,
        )

        listed = client.get(
            "/api/v1/notifications?limit=50", headers=other_tenant_auth_headers
        )
        titles = [n["title"] for n in listed.json()]
        assert TEST_TITLE not in titles
    finally:
        _cleanup()


def test_mark_read_cross_tenant_returns_404_and_does_not_mutate(
    client, auth_headers, other_tenant_auth_headers
):
    _cleanup()
    try:
        created = client.post(
            "/api/v1/notifications",
            json={"title": TEST_TITLE, "message": TEST_MESSAGE},
            headers=auth_headers,
        ).json()

        r = client.patch(
            f"/api/v1/notifications/{created['id']}/read",
            headers=other_tenant_auth_headers,
        )
        assert r.status_code == 404

        # Confirm it genuinely wasn't mutated for its actual owner.
        listed = client.get("/api/v1/notifications?limit=50", headers=auth_headers)
        mine = next(n for n in listed.json() if n["id"] == created["id"])
        assert mine["read"] is False
    finally:
        _cleanup()


def test_mark_read_own_tenant(client, auth_headers):
    _cleanup()
    try:
        created = client.post(
            "/api/v1/notifications",
            json={"title": TEST_TITLE, "message": TEST_MESSAGE},
            headers=auth_headers,
        ).json()

        r = client.patch(
            f"/api/v1/notifications/{created['id']}/read", headers=auth_headers
        )
        assert r.status_code == 200
        assert r.json()["read"] is True
    finally:
        _cleanup()
