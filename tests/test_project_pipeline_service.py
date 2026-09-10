"""Pipeline V2 through the API — Sprint 039, Workstream D.

Exercises the service and route layer against a real tenant on GeoCore's
trade-neutral default pipeline: where a new job starts, which transitions
the graph allows, and how hold/resume/cancel behave now that the pipeline
is no longer a strict linear walk.

Every test here signs up its own workspace (`other_tenant_auth_headers`)
rather than using the seeded owner. That is deliberate: which pipeline a
tenant is on depends on *when it was created* — Sprint 039's migration
seeded every pre-existing tenant with the legacy `stone` template, while
anything created afterwards gets `standard`. A suite that assumed the
seeded owner was on one or the other would pass on a fresh CI database and
fail on a developer's long-lived local one. Signing up removes the
question: a tenant created now is always on `standard`.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import Project

RUN_ID = uuid.uuid4().hex[:8]
TEST_PREFIX = f"Pytest Pipeline Service {RUN_ID}"


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(Project).where(Project.name.like(f"{TEST_PREFIX}%")))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


def _create(client, other_tenant_auth_headers, **overrides):
    payload = {"name": f"{TEST_PREFIX} job"}
    payload.update(overrides)
    r = client.post("/api/v1/projects", json=payload, headers=other_tenant_auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def _set_status(client, other_tenant_auth_headers, project_id, status):
    return client.patch(
        f"/api/v1/projects/{project_id}/status",
        json={"status": status},
        headers=other_tenant_auth_headers,
    )


def _advance(client, other_tenant_auth_headers, project_id, *statuses):
    for status in statuses:
        r = _set_status(client, other_tenant_auth_headers, project_id, status)
        assert r.status_code == 200, (status, r.text)
    return r.json()


# --- Where a job starts, and what it reports about itself ----------------


def test_a_new_job_starts_at_the_trade_neutral_lead_stage(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)

    assert project["status"] == "lead"


def test_a_project_reports_its_neutral_role_alongside_its_stage_key(client, other_tenant_auth_headers):
    """The role is what every other surface reasons about, so the API
    states it rather than making each client re-derive it from a stage
    key whose name is tenant configuration."""
    project = _create(client, other_tenant_auth_headers)

    assert project["status_role"] == "lead"


def test_the_pipeline_endpoint_describes_this_tenant_s_own_stages(client, other_tenant_auth_headers):
    r = client.get("/api/v1/projects/meta/pipeline", headers=other_tenant_auth_headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert [stage["key"] for stage in body["stages"]] == [
        "lead",
        "quoted",
        "approved",
        "scheduled",
        "in_progress",
        "completed",
        "on_hold",
        "cancelled",
    ]
    assert body["stages"][0]["label"] == "Planning"
    assert body["stages"][0]["role"] == "lead"


def test_the_pipeline_endpoint_states_which_transitions_each_stage_allows(
    client, other_tenant_auth_headers
):
    """Served from the backend so the UI can only ever offer a move the
    engine will actually accept — the same reasoning that keeps
    /automations/meta authoritative for triggers and actions."""
    body = client.get("/api/v1/projects/meta/pipeline", headers=other_tenant_auth_headers).json()

    by_key = {stage["key"]: stage for stage in body["stages"]}
    assert by_key["lead"]["allowed_transitions"] == ["quoted", "on_hold", "cancelled"]
    assert by_key["completed"]["allowed_transitions"] == []


# --- Forward progress ----------------------------------------------------


def test_forward_progress_moves_one_stage_at_a_time(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)

    updated = _advance(client, other_tenant_auth_headers, project["id"], "quoted")

    assert updated["status"] == "quoted"
    assert updated["status_role"] == "quoted"


def test_skipping_a_stage_is_still_refused(client, other_tenant_auth_headers):
    """Sprint 023's real invariant survives Pipeline V2 unchanged."""
    project = _create(client, other_tenant_auth_headers)

    r = _set_status(client, other_tenant_auth_headers, project["id"], "in_progress")

    assert r.status_code == 409


def test_moving_backwards_is_still_refused(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)
    _advance(client, other_tenant_auth_headers, project["id"], "quoted")

    r = _set_status(client, other_tenant_auth_headers, project["id"], "lead")

    assert r.status_code == 409


def test_a_job_can_be_walked_all_the_way_to_completed(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)

    final = _advance(
        client,
        other_tenant_auth_headers,
        project["id"],
        "quoted",
        "approved",
        "scheduled",
        "in_progress",
        "completed",
    )

    assert final["status_role"] == "completed"


def test_a_completed_job_is_terminal(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)
    _advance(
        client, other_tenant_auth_headers, project["id"],
        "quoted", "approved", "scheduled", "in_progress", "completed",
    )

    r = _set_status(client, other_tenant_auth_headers, project["id"], "cancelled")

    assert r.status_code == 409


# --- Hold, resume, cancel — what Sprint 023's linear walk could not say ---


def test_a_job_in_progress_can_be_put_on_hold(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)
    _advance(client, other_tenant_auth_headers, project["id"], "quoted", "approved", "scheduled", "in_progress")

    r = _set_status(client, other_tenant_auth_headers, project["id"], "on_hold")

    assert r.status_code == 200
    assert r.json()["status_role"] == "on_hold"


def test_a_held_job_can_resume_where_the_business_says_it_resumes(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)
    _advance(client, other_tenant_auth_headers, project["id"], "quoted", "approved", "on_hold")

    r = _set_status(client, other_tenant_auth_headers, project["id"], "scheduled")

    assert r.status_code == 200
    assert r.json()["status"] == "scheduled"


def test_coming_off_hold_can_never_mark_a_job_completed(client, other_tenant_auth_headers):
    """Completion is always its own deliberate forward step."""
    project = _create(client, other_tenant_auth_headers)
    _advance(client, other_tenant_auth_headers, project["id"], "quoted", "approved", "on_hold")

    r = _set_status(client, other_tenant_auth_headers, project["id"], "completed")

    assert r.status_code == 409


def test_a_job_can_be_cancelled_from_any_active_stage(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)
    _advance(client, other_tenant_auth_headers, project["id"], "quoted")

    r = _set_status(client, other_tenant_auth_headers, project["id"], "cancelled")

    assert r.status_code == 200
    assert r.json()["status_role"] == "cancelled"


def test_a_cancelled_job_is_terminal(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)
    _advance(client, other_tenant_auth_headers, project["id"], "cancelled")

    r = _set_status(client, other_tenant_auth_headers, project["id"], "quoted")

    assert r.status_code == 409


# --- Stage keys are tenant configuration, so unknown ones are refused ----


def test_a_stage_this_tenant_does_not_have_is_refused(client, other_tenant_auth_headers):
    """`fabricated` is a real stage — for a stone tenant. This workspace
    is on the standard pipeline and must not accept it."""
    project = _create(client, other_tenant_auth_headers)

    r = _set_status(client, other_tenant_auth_headers, project["id"], "fabricated")

    assert r.status_code in (409, 422)


def test_a_nonsense_stage_is_refused(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)

    r = _set_status(client, other_tenant_auth_headers, project["id"], "not-a-stage")

    assert r.status_code in (409, 422)


# --- Conversion keys off the role, not the stage name --------------------


def test_a_lead_stage_project_can_still_be_converted_to_a_customer(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)

    r = client.post(
        f"/api/v1/projects/{project['id']}/convert-to-customer",
        json={"name": f"{TEST_PREFIX} customer"},
        headers=other_tenant_auth_headers,
    )

    assert r.status_code == 200, r.text


def test_a_project_past_the_lead_stage_cannot_be_converted(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)
    _advance(client, other_tenant_auth_headers, project["id"], "quoted")

    r = client.post(
        f"/api/v1/projects/{project['id']}/convert-to-customer",
        json={"name": f"{TEST_PREFIX} customer"},
        headers=other_tenant_auth_headers,
    )

    assert r.status_code == 409


# --- The dashboard counts roles, which is what makes it trade-neutral ----


def test_the_command_centre_pipeline_is_keyed_by_neutral_role(client, other_tenant_auth_headers):
    body = client.get("/api/v1/dashboard/command-centre", headers=other_tenant_auth_headers).json()

    assert set(body["pipeline"]) == {
        "lead",
        "quoted",
        "approved",
        "scheduled",
        "in_progress",
        "on_hold",
        "completed",
        "cancelled",
    }


def test_a_held_job_is_counted_under_on_hold(client, other_tenant_auth_headers):
    project = _create(client, other_tenant_auth_headers)
    before = client.get("/api/v1/dashboard/command-centre", headers=other_tenant_auth_headers).json()
    _advance(client, other_tenant_auth_headers, project["id"], "quoted", "on_hold")

    after = client.get("/api/v1/dashboard/command-centre", headers=other_tenant_auth_headers).json()

    assert after["pipeline"]["on_hold"] == before["pipeline"]["on_hold"] + 1
