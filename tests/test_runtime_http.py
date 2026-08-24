import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def make_development_settings(**values: object) -> Settings:
    return Settings(
        _env_file=None,
        cors_allowed_origins=["https://allowed.example"],
        **values,
    )


def make_production_settings(upload_dir: Path, **values: object) -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+psycopg://simo:strong-password@db.internal/simo_os",
        jwt_secret_key="x" * 32,
        seed_admin_email="bootstrap@example.invalid",
        seed_admin_password="safe-bootstrap-password",
        seed_data_enabled=False,
        cors_allowed_origins=["https://app.example.com"],
        upload_dir=str(upload_dir),
        **values,
    )


@pytest.fixture()
def preserve_simo_os_logger():
    logger = logging.getLogger("simo_os")
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate
    yield
    for handler in logger.handlers:
        if handler not in original_handlers:
            handler.close()
    logger.handlers[:] = original_handlers
    logger.setLevel(original_level)
    logger.propagate = original_propagate


def parse_json_log_lines(serialized_logs: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in serialized_logs.splitlines() if line.strip()]


def test_cors_preflight_allows_configured_origin():
    application = create_app(make_development_settings())
    client = TestClient(application)

    response = client.options(
        "/api/v1/customers",
        headers={
            "Origin": "https://allowed.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers["access-control-allow-origin"] == "https://allowed.example"


def test_cors_preflight_rejects_origin_outside_configuration():
    application = create_app(make_development_settings())
    client = TestClient(application)

    response = client.options(
        "/api/v1/customers",
        headers={
            "Origin": "https://denied.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_health_is_unauthenticated_and_does_not_call_the_readiness_probe():
    async def unexpected_probe(timeout_seconds: float) -> None:
        raise AssertionError(f"liveness must not probe the database: {timeout_seconds}")

    application = create_app(
        make_development_settings(readiness_timeout_seconds=2.0),
        readiness_probe=unexpected_probe,
    )
    client = TestClient(application)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_ready_is_unauthenticated_and_reports_a_reachable_database():
    async def ready_probe(timeout_seconds: float) -> None:
        assert timeout_seconds == 2.0

    application = create_app(
        make_development_settings(readiness_timeout_seconds=2.0),
        readiness_probe=ready_probe,
    )
    client = TestClient(application)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "reachable"}


def test_ready_redacts_database_errors_and_logs_only_the_exception_type(caplog):
    secret_database_host = "postgresql://simo:password@secret-db.internal/simo_os"

    async def failed_probe(timeout_seconds: float) -> None:
        assert timeout_seconds == 2.0
        raise TimeoutError(secret_database_host)

    application = create_app(
        make_development_settings(readiness_timeout_seconds=2.0),
        readiness_probe=failed_probe,
    )
    client = TestClient(application)

    with caplog.at_level("WARNING", logger="simo_os"):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unreachable"}
    assert "readiness_failed" in caplog.text
    assert "TimeoutError" in caplog.text
    assert secret_database_host not in caplog.text


def test_database_probe_executes_select_one_and_closes_its_connection(monkeypatch):
    from app.core import health

    connection = MagicMock()
    connection.__enter__.return_value = connection
    engine = MagicMock()
    engine.connect.return_value = connection
    monkeypatch.setattr(health, "engine", engine)

    asyncio.run(health.probe_database(2.0))

    connection.execute.assert_called_once()
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"
    connection.__exit__.assert_called_once_with(None, None, None)


def test_missing_request_id_is_generated_and_returned():
    application = create_app(make_development_settings(seed_data_enabled=False))
    client = TestClient(application)

    response = client.get("/health")

    assert UUID(response.headers["x-request-id"])


def test_valid_request_id_is_preserved():
    application = create_app(make_development_settings(seed_data_enabled=False))
    client = TestClient(application)

    response = client.get("/health", headers={"X-Request-ID": "deploy-018_1"})

    assert response.headers["x-request-id"] == "deploy-018_1"


@pytest.mark.parametrize(
    "incoming_request_id",
    [
        b"",
        b"x" * 129,
        b"contains space",
        b"contains/slash",
        "caf\N{LATIN SMALL LETTER E WITH ACUTE}".encode(),
        b"contains\nnewline",
    ],
    ids=["blank", "oversized", "whitespace", "slash", "unicode", "newline"],
)
def test_invalid_request_id_is_replaced(incoming_request_id: bytes):
    application = create_app(make_development_settings(seed_data_enabled=False))
    client = TestClient(application)

    response = client.get(
        "/health",
        headers=[(b"x-request-id", incoming_request_id)],
    )

    generated = response.headers["x-request-id"]
    assert UUID(generated)
    assert generated.encode() != incoming_request_id


def test_request_id_context_does_not_leak_between_sequential_requests():
    application = create_app(make_development_settings(seed_data_enabled=False))
    client = TestClient(application)

    first = client.get("/health", headers={"X-Request-ID": "first-request"})
    second = client.get("/health")

    assert first.headers["x-request-id"] == "first-request"
    assert UUID(second.headers["x-request-id"])
    assert second.headers["x-request-id"] != "first-request"


def test_cors_preflight_response_carries_request_id():
    application = create_app(make_development_settings(seed_data_enabled=False))
    client = TestClient(application)

    response = client.options(
        "/api/v1/customers",
        headers={
            "Origin": "https://allowed.example",
            "Access-Control-Request-Method": "GET",
            "X-Request-ID": "preflight-request",
        },
    )

    assert response.headers["x-request-id"] == "preflight-request"


def test_production_request_logging_is_structured_and_redacts_request_data(
    tmp_path,
    capsys,
    preserve_simo_os_logger,
):
    application = create_app(make_production_settings(tmp_path))

    @application.post("/api/v1/portal-links/token/{token}/logging-probe")
    async def logging_probe(token: str):
        return {"status": "ok"}

    concrete_token = "concrete-portal-token-secret"
    query_secret = "query-secret-value"
    body_secret = "body-secret-value"
    authorization_secret = "authorization-secret-value"
    with TestClient(application) as client:
        response = client.post(
            f"/api/v1/portal-links/token/{concrete_token}/logging-probe"
            f"?access={query_secret}",
            json={"body": body_secret},
            headers={
                "Authorization": f"Bearer {authorization_secret}",
                "X-Request-ID": "structured-request",
            },
        )
        serialized_logs = capsys.readouterr().err

    records = parse_json_log_lines(serialized_logs)
    completion = next(
        record for record in records if record["event"] == "http_request_completed"
    )
    assert response.status_code == 200
    assert completion["timestamp"].endswith("Z")
    assert completion["level"] == "INFO"
    assert completion["logger"] == "simo_os"
    assert completion["message"] == "HTTP request completed"
    assert completion["request_id"] == "structured-request"
    assert completion["method"] == "POST"
    assert completion["path"] == "/api/v1/portal-links/token/{token}/logging-probe"
    assert completion["status_code"] == 200
    assert completion["duration_ms"] >= 0
    assert set(completion) <= {
        "timestamp",
        "level",
        "logger",
        "event",
        "message",
        "request_id",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "exception_type",
        "stack_trace",
    }
    for secret in (
        concrete_token,
        query_secret,
        body_secret,
        authorization_secret,
    ):
        assert secret not in serialized_logs


def test_unhandled_exception_is_structured_redacted_and_keeps_safe_response(
    tmp_path,
    capsys,
    monkeypatch,
    preserve_simo_os_logger,
):
    application = create_app(make_production_settings(tmp_path))
    raw_sql = "SELECT users WHERE email = %(email_1)s"
    synthetic_email = "synthetic@example.invalid"
    synthetic_password = "synthetic-password-value"
    exception_token = "exception-token-value"
    exception_secret = f"{raw_sql}; {synthetic_email}; {synthetic_password}; {exception_token}"
    concrete_token = "unhandled-concrete-token"

    @application.get("/testing/unhandled/{token}")
    async def unhandled_probe(token: str):
        raise RuntimeError(exception_secret)

    logged = []
    from app.core.errors import logger as error_logger

    original_error = error_logger.error

    def capture_error(*args, **kwargs):
        logged.append((args, kwargs))
        return original_error(*args, **kwargs)

    monkeypatch.setattr(error_logger, "error", capture_error)

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get(
            f"/testing/unhandled/{concrete_token}",
            headers={"X-Request-ID": "failed-request"},
        )
        serialized_logs = capsys.readouterr().err

    records = parse_json_log_lines(serialized_logs)
    events = [record["event"] for record in records]
    unhandled = next(record for record in records if record["event"] == "unhandled_exception")
    completion = next(
        record for record in records if record["event"] == "http_request_completed"
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["x-request-id"] == "failed-request"
    assert events.count("unhandled_exception") == 1
    assert events.count("http_request_completed") == 1
    assert unhandled["request_id"] == "failed-request"
    assert unhandled["method"] == "GET"
    assert unhandled["path"] == "/testing/unhandled/{token}"
    assert unhandled["exception_type"] == "RuntimeError"
    assert "stack_trace" not in unhandled
    assert completion["status_code"] == 500
    assert exception_secret not in serialized_logs
    for sensitive_value in (raw_sql, synthetic_email, synthetic_password, exception_token):
        assert sensitive_value not in serialized_logs
        assert sensitive_value not in response.text
    assert concrete_token not in serialized_logs
    assert "Traceback (most recent call last)" not in serialized_logs
    assert logged[0][1].get("exc_info") is None


def test_startup_failure_is_structured_and_redacts_exception_message(
    tmp_path,
    capsys,
    preserve_simo_os_logger,
):
    missing_upload_directory = tmp_path / "missing-upload-mount"
    application = create_app(make_production_settings(missing_upload_directory))

    with pytest.raises(RuntimeError), TestClient(application):
        pass
    serialized_logs = capsys.readouterr().err

    records = parse_json_log_lines(serialized_logs)
    startup = next(record for record in records if record["event"] == "startup_failed")
    assert startup["exception_type"] == "RuntimeError"
    assert startup["message"] == "Application startup failed"
    assert "UPLOAD_DIR must be an existing directory" not in serialized_logs


def test_unmatched_sensitive_path_is_omitted_from_logs(
    tmp_path,
    capsys,
    preserve_simo_os_logger,
):
    application = create_app(make_production_settings(tmp_path))
    raw_secret_path = "unmatched-token-secret"
    query_secret = "unmatched-query-secret"

    with TestClient(application) as client:
        response = client.get(f"/{raw_secret_path}?token={query_secret}")
        serialized_logs = capsys.readouterr().err

    records = parse_json_log_lines(serialized_logs)
    completion = next(
        record for record in records if record["event"] == "http_request_completed"
    )
    assert response.status_code == 404
    assert completion["path"] is None
    assert raw_secret_path not in serialized_logs
    assert query_secret not in serialized_logs


def test_production_readiness_logging_has_request_context_and_redacts_error(
    tmp_path,
    capsys,
    preserve_simo_os_logger,
):
    database_secret = "postgresql://simo:secret@private-db.internal/simo_os"

    async def failed_probe(timeout_seconds: float) -> None:
        raise TimeoutError(database_secret)

    application = create_app(
        make_production_settings(tmp_path),
        readiness_probe=failed_probe,
    )
    with TestClient(application) as client:
        response = client.get(
            "/ready",
            headers={"X-Request-ID": "readiness-request"},
        )
        serialized_logs = capsys.readouterr().err

    records = parse_json_log_lines(serialized_logs)
    readiness = next(record for record in records if record["event"] == "readiness_failed")
    assert response.status_code == 503
    assert readiness["request_id"] == "readiness-request"
    assert readiness["exception_type"] == "TimeoutError"
    assert database_secret not in serialized_logs


def test_known_error_contracts_keep_bodies_and_request_id_headers():
    application = create_app(make_development_settings(seed_data_enabled=False))

    @application.get("/testing/key-error")
    async def key_error_probe():
        raise KeyError("material")

    @application.get("/testing/validation")
    async def validation_probe(required_integer: int):
        return {"required_integer": required_integer}

    client = TestClient(application)
    bad_value = client.get(
        "/testing/key-error",
        headers={"X-Request-ID": "bad-value-request"},
    )
    invalid_request = client.get(
        "/testing/validation",
        headers={"X-Request-ID": "validation-request"},
    )

    assert bad_value.status_code == 400
    assert bad_value.json() == {"detail": "Unrecognised value: 'material'"}
    assert bad_value.headers["x-request-id"] == "bad-value-request"
    assert invalid_request.status_code == 422
    assert invalid_request.json()["detail"] == "Invalid request"
    assert invalid_request.headers["x-request-id"] == "validation-request"
