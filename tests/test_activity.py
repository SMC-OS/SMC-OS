"""Sprint 012 (ADR-029) — app/activity/router.py had no auth at all before
this sprint (docs/USER_ROLES.md §1's "still true" list). No test file
existed for it either. This covers the new auth gate and tenant scoping.
"""

from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog

TEST_TITLE = "Pytest Activity Event"
TEST_DESCRIPTION = "pytest-activity-description"


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(ActivityLog).where(ActivityLog.title == TEST_TITLE))
        db.commit()
    finally:
        db.close()


def test_activity_routes_require_auth(client):
    assert client.get("/api/v1/activity").status_code == 401
    assert (
        client.post(
            "/api/v1/activity",
            json={"type": "customer_added", "title": TEST_TITLE},
        ).status_code
        == 401
    )


def test_create_and_list_activity_own_tenant(client, auth_headers):
    _cleanup()
    try:
        r = client.post(
            "/api/v1/activity",
            json={
                "type": "customer_added",
                "title": TEST_TITLE,
                "description": TEST_DESCRIPTION,
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["title"] == TEST_TITLE

        listed = client.get("/api/v1/activity?limit=50", headers=auth_headers)
        titles = [e["title"] for e in listed.json()]
        assert TEST_TITLE in titles
    finally:
        _cleanup()


def test_activity_not_visible_to_other_tenant(
    client, auth_headers, other_tenant_auth_headers
):
    _cleanup()
    try:
        client.post(
            "/api/v1/activity",
            json={"type": "customer_added", "title": TEST_TITLE},
            headers=auth_headers,
        )

        listed = client.get(
            "/api/v1/activity?limit=50", headers=other_tenant_auth_headers
        )
        titles = [e["title"] for e in listed.json()]
        assert TEST_TITLE not in titles
    finally:
        _cleanup()
