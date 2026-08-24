"""Sprint 019 local contracts for staging monitoring and smoke scripts.

The scripts themselves are deliberately not pointed at a real Railway
environment in tests.  These tests exercise their safe, offline behaviour.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = PROJECT_ROOT / "scripts" / "staging" / "smoke.py"
HEALTH_SCRIPT = PROJECT_ROOT / "scripts" / "staging" / "check-health.ps1"
MONITOR_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "staging-monitor.yml"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("staging_smoke", SMOKE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "origin",
    [
        "http://staging.example.invalid",
        "https://localhost",
        "https://127.0.0.1",
        "https://[::1]",
        "https://staging.example.invalid/path",
        "https://staging.example.invalid?next=1",
        "https://staging.example.invalid#fragment",
        "https://user:pass@staging.example.invalid",
    ],
)
def test_smoke_runner_rejects_non_public_or_non_origin_urls(origin):
    smoke = load_smoke_module()

    with pytest.raises(ValueError):
        smoke.validate_public_https_origin(origin)


def test_smoke_runner_accepts_a_public_https_origin():
    smoke = load_smoke_module()

    assert smoke.validate_public_https_origin("https://api.staging.example.invalid") == (
        "https://api.staging.example.invalid"
    )


def test_smoke_runner_redacts_sensitive_values_from_evidence():
    smoke = load_smoke_module()
    unsafe = (
        "Authorization: Bearer bearer-secret token=portal-secret "
        "password=passphrase secret=top-secret "
        "DATABASE_URL=postgresql://simo:database-password@db.internal/simo"
    )

    safe = smoke.redact_value(unsafe)

    for secret in ("bearer-secret", "portal-secret", "passphrase", "top-secret", "database-password"):
        assert secret not in safe
    assert "[REDACTED]" in safe


def test_smoke_runner_declares_the_approved_twenty_two_named_gates():
    smoke = load_smoke_module()

    assert len(smoke.SMOKE_GATES) == 22
    assert smoke.SMOKE_GATES == (
        "https_reachability",
        "liveness",
        "readiness",
        "postgresql",
        "migration",
        "no_seeding",
        "signup_login_auth",
        "customer",
        "project",
        "quote_invoice",
        "staff_document",
        "restart_persistence",
        "portal_token",
        "portal_documents",
        "portal_messaging",
        "token_enforcement",
        "tenant_isolation",
        "cors_allowed",
        "cors_denied",
        "logs_request_ids",
        "repository_secret_scan",
        "backup_restore",
    )


def test_smoke_runner_help_exposes_required_origins_and_restart_opt_in():
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--web-url" in result.stdout
    assert "--api-url" in result.stdout
    assert "--allow-restart" in result.stdout


def test_smoke_runner_requires_explicit_public_origins():
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--json-report", "report.json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--web-url" in result.stderr
    assert "--api-url" in result.stderr


def test_smoke_runner_dry_run_emits_all_gates_and_machine_readable_safe_report(tmp_path):
    report = tmp_path / "smoke-report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SMOKE_SCRIPT),
            "--web-url",
            "https://web.staging.example.invalid",
            "--api-url",
            "https://api.staging.example.invalid",
            "--dry-run",
            "--json-report",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert len(payload["gates"]) == 22
    assert payload["totals"] == {"passed": 0, "failed": 0, "blocked": 22}
    assert all(gate["status"] == "BLOCKED" for gate in payload["gates"])
    assert "https://web.staging.example.invalid" in result.stdout
    assert "Authorization" not in result.stdout


def test_smoke_runner_redacts_tokens_and_sensitive_response_fields_from_report():
    smoke = load_smoke_module()

    safe = smoke.sanitize_evidence(
        {
            "access_token": "secret-access-token",
            "email": "synthetic@example.invalid",
            "nested": {"password": "synthetic-password", "id": "safe-id"},
        }
    )

    serialized = json.dumps(safe)
    for secret in ("secret-access-token", "synthetic@example.invalid", "synthetic-password"):
        assert secret not in serialized
    assert safe["nested"]["id"] == "safe-id"


def test_smoke_runner_marks_a_false_workflow_assertion_as_failed_not_passed():
    smoke = load_smoke_module()
    runner = smoke.SmokeRunner(
        "https://web.staging.example.invalid",
        "https://api.staging.example.invalid",
        allow_restart=False,
        timeout=5,
    )

    runner.gate("customer", lambda: {"created": False})

    assert runner.results == [
        {"name": "customer", "status": "FAIL", "evidence": {"assertion_failed": "created"}}
    ]


def test_smoke_runner_preserves_gate_evidence_with_reserved_result_keys():
    smoke = load_smoke_module()
    runner = smoke.SmokeRunner(
        "https://web.staging.example.invalid",
        "https://api.staging.example.invalid",
        allow_restart=False,
        timeout=5,
    )

    runner.gate("project", lambda: {"status": "enquiry", "name": "Synthetic Project", "created": True})

    assert runner.results == [
        {
            "name": "project",
            "status": "PASS",
            "evidence": {"observed_status": "enquiry", "observed_name": "Synthetic Project", "created": True},
        }
    ]


def test_smoke_runner_contains_unexpected_gate_exception_and_reports_remaining_gates():
    smoke = load_smoke_module()
    runner = smoke.SmokeRunner(
        "https://web.staging.example.invalid",
        "https://api.staging.example.invalid",
        allow_restart=False,
        timeout=5,
    )

    def unexpected_failure():
        raise RuntimeError("SELECT * FROM users WHERE email='synthetic@example.invalid' token=unsafe")

    runner.gate("customer", unexpected_failure)
    runner.gate("project", lambda: {"created": True})
    report = runner.report()

    assert report["gates"][0] == {
        "name": "customer",
        "status": "FAIL",
        "evidence": {"error_type": "RuntimeError"},
    }
    assert report["gates"][1]["status"] == "PASS"
    assert report["totals"] == {"passed": 1, "failed": 1, "blocked": 0}
    assert "SELECT" not in json.dumps(report)
    assert "synthetic@example.invalid" not in json.dumps(report)
    assert "unsafe" not in json.dumps(report)


def test_smoke_runner_reports_safe_http_failure_metadata_only():
    smoke = load_smoke_module()
    runner = smoke.SmokeRunner("https://web.staging.example.invalid", "https://api.staging.example.invalid", allow_restart=False, timeout=5)
    runner.gate("quote_invoice", lambda: (_ for _ in ()).throw(smoke.SmokeHttpError("POST", "quote_create", 400)))
    assert runner.results == [{"name": "quote_invoice", "status": "FAIL", "evidence": {"method": "POST", "route": "quote_create", "status_code": 400}}]


def test_quote_inputs_must_be_supplied_together_and_missing_quote_blocks_gate():
    smoke = load_smoke_module()
    runner = smoke.SmokeRunner("https://web.staging.example.invalid", "https://api.staging.example.invalid", allow_restart=False, timeout=5)
    runner.blocked("quote_invoice", "requires --quote-material and --quote-thickness")
    assert runner.results[0]["status"] == "BLOCKED"
    assert smoke.build_parser().parse_args(["--web-url", "https://web.staging.example.invalid", "--api-url", "https://api.staging.example.invalid", "--json-report", "report.json", "--quote-material", "Quartz"]).quote_thickness is None


def test_health_monitor_requires_both_origins_and_never_uses_credentials():
    content = HEALTH_SCRIPT.read_text(encoding="utf-8")

    assert "[Parameter(Mandatory = $true)]" in content
    assert "$WebOrigin" in content
    assert "$ApiOrigin" in content
    assert "/health" in content
    assert "/ready" in content
    assert "X-Request-ID" in content
    assert "Authorization" not in content
    assert "Bearer" not in content


@pytest.mark.parametrize(
    "unsafe_origin",
    [
        "https://user:pass@staging.example.invalid",
        "https://staging.example.invalid?next=1",
        "https://staging.example.invalid#fragment",
    ],
)
def test_health_monitor_rejects_unsafe_public_origin_components_before_network(unsafe_origin):
    result = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(HEALTH_SCRIPT),
            "-WebOrigin",
            unsafe_origin,
            "-ApiOrigin",
            "https://api.staging.example.invalid",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "Origins must be public HTTPS origins without paths." in result.stderr


def test_monitor_workflow_uses_only_public_origin_variables():
    content = MONITOR_WORKFLOW.read_text(encoding="utf-8")

    assert "schedule:" in content
    assert "workflow_dispatch:" in content
    assert "STAGING_WEB_ORIGIN" in content
    assert "STAGING_API_ORIGIN" in content
    assert "check-health.ps1" in content
    for forbidden in ("RAILWAY_TOKEN", "DATABASE_URL", "JWT_SECRET", "SEED_ADMIN_PASSWORD"):
        assert forbidden not in content
