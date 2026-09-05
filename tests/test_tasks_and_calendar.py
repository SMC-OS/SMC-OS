"""Tasks and the operational calendar — Sprint 036, Workstreams F/K.

The calendar's contract is narrow and worth stating: every item in it is a
real row this workspace already owns. Nothing is predicted, inferred or
synthesised, and there is deliberately no external calendar integration —
so these tests assert what the feed contains and, just as importantly,
that an approved quote's expiry is not padded into it.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.database.database import SessionLocal
from app.database.models import Appointment, Project, Quote, QuoteItem, Task

RUN_ID = uuid.uuid4().hex[:8]
TEST_PREFIX = f"Pytest Tasks {RUN_ID}"
TEST_POSTCODE = f"PYT36{RUN_ID[:5]}".upper()


def _cleanup():
    db = SessionLocal()
    try:
        project_ids = select(Project.id).where(Project.name.like(f"{TEST_PREFIX}%"))
        quote_ids = select(Quote.id).where(Quote.postcode == TEST_POSTCODE)
        db.execute(delete(Appointment).where(Appointment.project_id.in_(project_ids)))
        db.execute(delete(Task).where(Task.title.like(f"{TEST_PREFIX}%")))
        db.execute(delete(Project).where(Project.quote_id.in_(quote_ids)))
        db.execute(delete(Project).where(Project.name.like(f"{TEST_PREFIX}%")))
        db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
        db.execute(delete(Quote).where(Quote.postcode == TEST_POSTCODE))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


# --- Tasks ----------------------------------------------------------------


def test_create_list_and_complete_a_task(client, auth_headers):
    due = datetime.now(timezone.utc) + timedelta(days=2)
    created = client.post(
        "/api/v1/tasks",
        json={
            "title": f"{TEST_PREFIX} call the client back",
            "body": "Confirm the start date.",
            "due_at": due.isoformat(),
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["status"] == "open"
    assert task["completed_at"] is None

    listed = client.get("/api/v1/tasks?status=open&limit=200", headers=auth_headers).json()
    assert task["id"] in {t["id"] for t in listed}

    done = client.patch(
        f"/api/v1/tasks/{task['id']}/status", json={"status": "done"}, headers=auth_headers
    )
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert done.json()["completed_at"] is not None


def test_cancelling_a_task_does_not_record_a_completion_time(client, auth_headers):
    task = client.post(
        "/api/v1/tasks",
        json={"title": f"{TEST_PREFIX} abandoned"},
        headers=auth_headers,
    ).json()

    cancelled = client.patch(
        f"/api/v1/tasks/{task['id']}/status",
        json={"status": "cancelled"},
        headers=auth_headers,
    ).json()

    # Cancelling is not completing. Recording a completion time for
    # abandoned work would make any later "how long do tasks take"
    # reading wrong.
    assert cancelled["status"] == "cancelled"
    assert cancelled["completed_at"] is None


def test_rejects_an_unknown_task_status(client, auth_headers):
    task = client.post(
        "/api/v1/tasks", json={"title": f"{TEST_PREFIX} x"}, headers=auth_headers
    ).json()
    r = client.patch(
        f"/api/v1/tasks/{task['id']}/status", json={"status": "maybe"}, headers=auth_headers
    )
    assert r.status_code == 422


def test_rejects_an_assignee_from_another_tenant(
    client, auth_headers, other_tenant_auth_headers
):
    other_user_id = client.get("/api/v1/auth/me", headers=other_tenant_auth_headers).json()["id"]
    r = client.post(
        "/api/v1/tasks",
        json={"title": f"{TEST_PREFIX} cross tenant", "assigned_user_id": other_user_id},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_tasks_are_invisible_across_tenants(client, auth_headers, other_tenant_auth_headers):
    task = client.post(
        "/api/v1/tasks", json={"title": f"{TEST_PREFIX} private"}, headers=auth_headers
    ).json()

    listed = client.get("/api/v1/tasks?limit=200", headers=other_tenant_auth_headers).json()
    assert task["id"] not in {t["id"] for t in listed}

    r = client.patch(
        f"/api/v1/tasks/{task['id']}/status",
        json={"status": "done"},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404


# --- Calendar -------------------------------------------------------------


def test_calendar_aggregates_project_dates_tasks_and_quote_expiry(client, auth_headers):
    start = date.today() + timedelta(days=3)
    finish = date.today() + timedelta(days=10)

    project = client.post(
        "/api/v1/projects",
        json={
            "name": f"{TEST_PREFIX} scheduled job",
            "start_date": start.isoformat(),
            "target_completion_date": finish.isoformat(),
        },
        headers=auth_headers,
    ).json()

    task = client.post(
        "/api/v1/tasks",
        json={
            "title": f"{TEST_PREFIX} order materials",
            "due_at": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
        },
        headers=auth_headers,
    ).json()

    quote = client.post(
        "/api/v1/quotes",
        json={
            "title": f"{TEST_PREFIX} quote",
            "site_postcode": TEST_POSTCODE,
            "valid_until": (date.today() + timedelta(days=6)).isoformat(),
            "lines": [{"description": "Work", "quantity": 1, "unit": "job", "unit_price": 500}],
        },
        headers=auth_headers,
    ).json()

    r = client.get(
        f"/api/v1/calendar?start={date.today().isoformat()}"
        f"&end={(date.today() + timedelta(days=30)).isoformat()}",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    by_id = {item["id"]: item for item in items}

    assert f"project_start:{project['id']}" in by_id
    assert f"project_target:{project['id']}" in by_id
    assert f"task:{task['id']}" in by_id
    assert f"quote_expiry:{quote['id']}" in by_id

    # An all-day project date must be flagged as such — rendering it at an
    # arbitrary hour is the classic calendar bug this flag prevents.
    assert by_id[f"project_start:{project['id']}"]["all_day"] is True
    assert by_id[f"task:{task['id']}"]["all_day"] is False


def test_calendar_omits_an_approved_quotes_expiry(client, auth_headers):
    quote = client.post(
        "/api/v1/quotes",
        json={
            "title": f"{TEST_PREFIX} won",
            "site_postcode": TEST_POSTCODE,
            "valid_until": (date.today() + timedelta(days=5)).isoformat(),
            "lines": [{"description": "Work", "quantity": 1, "unit": "job", "unit_price": 500}],
        },
        headers=auth_headers,
    ).json()
    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    items = client.get(
        f"/api/v1/calendar?start={date.today().isoformat()}"
        f"&end={(date.today() + timedelta(days=30)).isoformat()}",
        headers=auth_headers,
    ).json()["items"]

    # An accepted quote's validity date is no longer a deadline. Showing
    # it would fill the calendar with deadlines that have been met.
    assert f"quote_expiry:{quote['id']}" not in {item["id"] for item in items}


def test_calendar_items_are_sorted_by_date(client, auth_headers):
    for offset in (12, 2, 7):
        client.post(
            "/api/v1/projects",
            json={
                "name": f"{TEST_PREFIX} job +{offset}",
                "start_date": (date.today() + timedelta(days=offset)).isoformat(),
            },
            headers=auth_headers,
        )

    items = client.get(
        f"/api/v1/calendar?start={date.today().isoformat()}"
        f"&end={(date.today() + timedelta(days=30)).isoformat()}",
        headers=auth_headers,
    ).json()["items"]

    ours = [i["at"][:10] for i in items if i["title"].startswith(f"Starts: {TEST_PREFIX}")]
    assert ours == sorted(ours)


def test_calendar_clamps_an_over_long_window_and_reports_what_it_served(
    client, auth_headers
):
    start = date.today()
    r = client.get(
        f"/api/v1/calendar?start={start.isoformat()}"
        f"&end={(start + timedelta(days=4000)).isoformat()}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()

    # Clamped rather than refused, and the window actually served is
    # echoed back so the client renders what it got.
    assert (date.fromisoformat(body["end"]) - date.fromisoformat(body["start"])).days <= 366


def test_calendar_is_tenant_scoped(client, auth_headers, other_tenant_auth_headers):
    project = client.post(
        "/api/v1/projects",
        json={
            "name": f"{TEST_PREFIX} private job",
            "start_date": (date.today() + timedelta(days=2)).isoformat(),
        },
        headers=auth_headers,
    ).json()

    items = client.get(
        f"/api/v1/calendar?start={date.today().isoformat()}"
        f"&end={(date.today() + timedelta(days=30)).isoformat()}",
        headers=other_tenant_auth_headers,
    ).json()["items"]

    assert f"project_start:{project['id']}" not in {item["id"] for item in items}
