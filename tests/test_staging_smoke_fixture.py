"""Staging smoke fixture repair.

scripts/staging/smoke.py signed up fresh workspaces and drove protected routes
without verifying them, so on a post-Sprint-039 build every workspace gate was
refused (403, require_verified_email) and the rest cascaded into KeyErrors.
These tests pin the real product behaviour (it must stay strict), the operator
fixture that satisfies it for synthetic users only, and the safe evidence.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from app.core import staging_fixture
from app.core.staging_fixture import FixtureRefused, verify_synthetic_users
from app.database import crud

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = PROJECT_ROOT / "scripts" / "staging" / "smoke.py"
STAGING = {"RAILWAY_ENVIRONMENT_NAME": "staging"}
VERIFY_MESSAGE = "Please verify your email address to continue."


def load_smoke():
    spec = importlib.util.spec_from_file_location("staging_smoke_fixture_under_test", SMOKE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Ctx:
    """Stands in for `with httpx.Client() as client` using the app's TestClient."""

    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self.client

    def __exit__(self, *exc):
        return False


def make_runner(smoke, client, db, *, verifier=True):
    def fixture(prefix):
        try:
            verify_synthetic_users(db, prefix, environ=STAGING)
        except FixtureRefused as exc:
            raise smoke.FixtureVerificationError(str(exc)) from None

    runner = smoke.SmokeRunner(
        "https://web.staging.example.invalid",
        "https://api.staging.example.invalid",
        allow_restart=False,
        timeout=30,
        fixture_verifier=fixture if verifier else None,
    )
    runner.client = client
    return runner


def signup_synthetic(client, prefix, tenant):
    email = f"{prefix}-{tenant}@example.invalid"
    password = f"S019-{uuid.uuid4().hex}!"
    response = client.post(
        "/api/v1/auth/signup",
        json={"company_name": f"{prefix}-{tenant}", "name": "Synthetic Operator", "email": email, "password": password},
    )
    assert response.status_code == 201
    return email, response.json()["access_token"]


def new_prefix():
    return f"s019-{uuid.uuid4().hex[:12]}"


# --- root cause: the product is strict, and a fresh signup is unverified ----


def test_fresh_smoke_user_is_unverified_and_workspace_access_is_denied(client):
    _, token = signup_synthetic(client, new_prefix(), "a")
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/v1/auth/me", headers=headers).json()
    denied = client.get("/api/v1/customers", headers=headers)
    command_centre = client.get("/api/v1/dashboard/command-centre", headers=headers)

    assert me["verification_required"] is True
    assert denied.status_code == 403 and denied.json()["detail"] == VERIFY_MESSAGE
    assert command_centre.status_code == 403 and command_centre.json()["detail"] == VERIFY_MESSAGE


def test_smoke_run_proves_unverified_rejection_then_keeps_the_real_no_card_trial(client, db):
    smoke = load_smoke()
    runner = make_runner(smoke, client, db)

    runner.gate("signup_login_auth", runner.signup_and_prepare)

    result = runner.results[0]
    assert result["status"] == "PASS", result
    evidence = result["evidence"]
    assert evidence["unverified_access_rejected"] is True
    assert evidence["unverified_status_code"] == 403
    assert evidence["fixture_verification"] == "applied"
    assert evidence["verified_access_allowed"] is True
    assert evidence["trial_retained"] is True

    # The trial is the real one signup started: not grandfathered, not paid.
    owner = crud.get_user_by_email(db, f"{runner.prefix}-a@example.invalid")
    db.refresh(owner)
    subscription = crud.get_subscription_by_tenant_id(db, owner.tenant_id)
    assert subscription.status == "trialing" and not subscription.legacy_grandfathered
    assert subscription.trial_start is not None and subscription.trial_end is not None


def test_customer_gate_and_downstream_gates_proceed_after_verification(client, db):
    smoke = load_smoke()
    runner = make_runner(smoke, client, db)
    runner.gate("signup_login_auth", runner.signup_and_prepare)

    runner.workspace_gate("customer", runner.customer)
    runner.workspace_gate("project", runner.project, requires=("customer_id",))
    runner.workspace_gate("staff_document", runner.document, requires=("customer_id",))
    runner.workspace_gate("appointment", runner.appointment, requires=("project_id",))
    runner.workspace_gate("command_centre", runner.command_centre)

    assert [(r["name"], r["status"]) for r in runner.results] == [
        ("signup_login_auth", "PASS"),
        ("customer", "PASS"),
        ("project", "PASS"),
        ("staff_document", "PASS"),
        ("appointment", "PASS"),
        ("command_centre", "PASS"),
    ]


def test_without_the_operator_fixture_workspace_gates_are_blocked_not_failed(client, db):
    smoke = load_smoke()
    runner = make_runner(smoke, client, db, verifier=False)

    runner.gate("signup_login_auth", runner.signup_and_prepare)
    runner.workspace_gate("customer", runner.customer)
    runner.workspace_gate("project", runner.project, requires=("customer_id",))

    assert runner.results[0]["status"] == "PASS"
    assert runner.results[0]["evidence"]["unverified_access_rejected"] is True
    assert runner.results[0]["evidence"]["fixture_verification"] == "unavailable"
    assert [r["status"] for r in runner.results[1:]] == ["BLOCKED", "BLOCKED"]
    assert "email verification" in runner.results[1]["evidence"]["reason"]


def test_a_workspace_that_is_not_refused_when_unverified_fails_the_signup_gate(client, db):
    smoke = load_smoke()
    runner = make_runner(smoke, client, db)
    runner.signup = lambda tenant: {  # type: ignore[method-assign]
        "signup_status": 201,
        "login_token_received": True,
        "unverified_status_code": 200,
        "unverified_access_rejected": False,
    }

    runner.gate("signup_login_auth", runner.signup_and_prepare)

    assert runner.results[0]["status"] == "FAIL"
    assert runner.results[0]["evidence"] == {"assertion_failed": "unverified_access_rejected"}


# --- the fixture is scoped to the run's own synthetic users, staging only ---


def test_fixture_verifies_only_the_run_s_own_synthetic_users(client, db):
    prefix = new_prefix()
    signup_synthetic(client, prefix, "a")
    signup_synthetic(client, prefix, "b")
    bystander_email, _ = signup_synthetic(client, new_prefix(), "a")

    changed = verify_synthetic_users(db, prefix, environ=STAGING)

    assert changed == 2
    for tenant in ("a", "b"):
        user = crud.get_user_by_email(db, f"{prefix}-{tenant}@example.invalid")
        db.refresh(user)
        assert user.email_verified_at is not None
    other = crud.get_user_by_email(db, bystander_email)
    db.refresh(other)
    assert other.email_verified_at is None


@pytest.mark.parametrize(
    "bad_prefix",
    ["", "owner", "s019-short", "s019-ZZZZZZZZZZZZ", "s019-0123456789abc", "s019-0123456789ab@example.com", "../s019-0123456789ab"],
)
def test_fixture_refuses_anything_that_is_not_a_smoke_run_prefix(db, bad_prefix):
    with pytest.raises(FixtureRefused):
        verify_synthetic_users(db, bad_prefix, environ=STAGING)


def test_fixture_cannot_verify_a_non_synthetic_or_mislabelled_user(client, db):
    # An ordinary user with a real-looking address is unreachable: the fixture
    # only ever derives <prefix>-a|b@example.invalid.
    real_email = f"real-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/v1/auth/signup", json={"company_name": "Real Co", "name": "Real", "email": real_email, "password": f"S019-{uuid.uuid4().hex}!"})
    with pytest.raises(FixtureRefused):
        verify_synthetic_users(db, new_prefix(), environ=STAGING)

    # Right address shape, but the tenant is not named by that smoke run.
    prefix = new_prefix()
    client.post(
        "/api/v1/auth/signup",
        json={"company_name": "Somebody Else", "name": "X", "email": f"{prefix}-a@example.invalid", "password": f"S019-{uuid.uuid4().hex}!"},
    )
    with pytest.raises(FixtureRefused):
        verify_synthetic_users(db, prefix, ("a",), environ=STAGING)
    user = crud.get_user_by_email(db, f"{prefix}-a@example.invalid")
    db.refresh(user)
    assert user.email_verified_at is None


def test_fixture_refuses_users_older_than_this_smoke_run(client, db):
    prefix = new_prefix()
    signup_synthetic(client, prefix, "a")
    later = datetime.now(timezone.utc) + timedelta(hours=2)

    with pytest.raises(FixtureRefused):
        verify_synthetic_users(db, prefix, ("a",), environ=STAGING, now=later)
    user = crud.get_user_by_email(db, f"{prefix}-a@example.invalid")
    db.refresh(user)
    assert user.email_verified_at is None


@pytest.mark.parametrize("environment", [{"RAILWAY_ENVIRONMENT_NAME": "production"}, {"RAILWAY_ENVIRONMENT_NAME": "Staging"}, {"RAILWAY_ENVIRONMENT_NAME": ""}, {"APP_ENV": "staging"}, {}])
def test_fixture_fails_closed_outside_staging_and_changes_nothing(client, db, environment):
    prefix = new_prefix()
    signup_synthetic(client, prefix, "a")

    with pytest.raises(FixtureRefused):
        verify_synthetic_users(db, prefix, ("a",), environ=environment)
    user = crud.get_user_by_email(db, f"{prefix}-a@example.invalid")
    db.refresh(user)
    assert user.email_verified_at is None


def test_fixture_cli_refuses_in_production_and_prints_no_secrets(monkeypatch, capsys):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")

    code = staging_fixture.main(["verify-email", "--run-prefix", new_prefix()])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "refused" in captured.err and "@" not in captured.err


def test_fixture_exposes_no_http_route():
    from app.main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any("fixture" in path or "staging" in path for path in paths)


# --- evidence: safe status + route, and prerequisite-aware reporting --------


def test_http_failures_keep_status_and_a_redacted_route_only():
    smoke = load_smoke()
    runner = smoke.SmokeRunner("https://web.staging.example.invalid", "https://api.staging.example.invalid", allow_restart=False, timeout=5)
    token = "x" * 43
    document_id = str(uuid.uuid4())
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(403, json={"detail": "secret-detail", "token": "leak"})

    runner.client = httpx.Client(transport=httpx.MockTransport(handler))
    runner.state["fixture_verified"] = True

    runner.workspace_gate(
        "portal_documents",
        lambda: runner.request("GET", f"/api/v1/portal-links/token/{token}/documents/{document_id}/download?x=1") and {},
    )

    assert runner.results == [
        {
            "name": "portal_documents",
            "status": "FAIL",
            "evidence": {"method": "GET", "route": "/api/v1/portal-links/token/{id}/documents/{id}/download", "status_code": 403},
        }
    ]
    serialized = json.dumps(runner.report())
    assert token not in serialized and document_id not in serialized and "secret-detail" not in serialized


def test_missing_prerequisites_are_blocked_and_name_the_missing_record():
    smoke = load_smoke()
    runner = smoke.SmokeRunner("https://web.staging.example.invalid", "https://api.staging.example.invalid", allow_restart=False, timeout=5)
    runner.state["fixture_verified"] = True

    runner.workspace_gate("project", lambda: {"created": True}, requires=("customer_id",))

    assert runner.results == [
        {"name": "project", "status": "BLOCKED", "evidence": {"reason": "prerequisite not created by an earlier gate: customer_id"}}
    ]
    assert runner.report()["totals"] == {"passed": 0, "failed": 0, "blocked": 1}


def test_signup_report_never_contains_credentials_or_synthetic_emails(client, db):
    smoke = load_smoke()
    runner = make_runner(smoke, client, db)
    runner.gate("signup_login_auth", runner.signup_and_prepare)
    runner.workspace_gate("customer", runner.customer)

    serialized = json.dumps(runner.report())

    assert "example.invalid@" not in serialized
    assert f"{runner.prefix}-a@" not in serialized and f"{runner.prefix}-b@" not in serialized
    assert "Bearer" not in serialized and runner.state["a_token"] not in serialized and runner.state["b_token"] not in serialized
    assert "S019-" not in serialized


# --- the operator hook: staging-only by construction ------------------------


def test_railway_fixture_hook_is_pinned_to_staging_and_runs_the_module_not_an_endpoint(monkeypatch):
    smoke = load_smoke()
    monkeypatch.setattr(smoke.shutil, "which", lambda name: "railway-cli")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return type("Done", (), {"returncode": 0})()

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)
    verifier = smoke.railway_fixture_verifier("proj-123", "simo-api-staging", "https://simo-api-staging-staging.up.railway.app")
    prefix = new_prefix()

    verifier(prefix)

    command = captured["command"]
    assert command[command.index("--environment") + 1] == "staging"
    assert command[command.index("--") + 1 :] == ["python", "-m", "app.core.staging_fixture", "verify-email", "--run-prefix", prefix]


def test_railway_fixture_hook_rejects_non_staging_hosts_odd_arguments_and_bad_prefixes(monkeypatch):
    smoke = load_smoke()
    monkeypatch.setattr(smoke.shutil, "which", lambda name: "railway-cli")
    with pytest.raises(ValueError):
        smoke.railway_fixture_verifier("proj", "svc", "https://simo-api-production.up.railway.app")
    with pytest.raises(ValueError):
        smoke.railway_fixture_verifier("proj; rm -rf /", "svc", "https://api-staging.up.railway.app")
    monkeypatch.setattr(smoke.subprocess, "run", lambda *a, **k: type("Done", (), {"returncode": 1})())
    verifier = smoke.railway_fixture_verifier("proj", "svc", "https://api-staging.up.railway.app")
    with pytest.raises(smoke.FixtureVerificationError):
        verifier("not-a-prefix")
    with pytest.raises(smoke.FixtureVerificationError):
        verifier(new_prefix())  # the container-side refusal (exit 2 etc.) surfaces as a failure


def test_cli_requires_both_railway_fixture_options():
    smoke = load_smoke()
    with pytest.raises(SystemExit):
        smoke.main(["--web-url", "https://web.staging.example.invalid", "--api-url", "https://api-staging.example.invalid", "--json-report", "x.json", "--fixture-verify-railway-project", "p"])
