"""Safe application logging configuration and request-scoped state."""

import json
import logging
import re
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from app.core.config import AppEnvironment


request_id_context: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)

_MANAGED_HANDLER_ATTRIBUTE = "_simo_os_managed_handler"
_RECORD_FIELDS = (
    "method",
    "path",
    "status_code",
    "duration_ms",
)
_LEGACY_EVENT_PATTERN = re.compile(r"^(readiness_failed)\b")
_LEGACY_EXCEPTION_TYPE_PATTERN = re.compile(r"\bexception_type=([A-Za-z0-9_.]+)\b")


def _event_for(record: logging.LogRecord) -> str:
    configured_event = getattr(record, "event", None)
    if isinstance(configured_event, str) and configured_event:
        return configured_event
    legacy_event = _LEGACY_EVENT_PATTERN.match(record.getMessage())
    return legacy_event.group(1) if legacy_event else "log"


def _request_id_for(record: logging.LogRecord) -> str | None:
    configured_request_id = getattr(record, "request_id", None)
    return configured_request_id or request_id_context.get()


def _exception_type_for(record: logging.LogRecord) -> str | None:
    configured_type = getattr(record, "exception_type", None)
    if isinstance(configured_type, str) and configured_type:
        return configured_type
    legacy_type = _LEGACY_EXCEPTION_TYPE_PATTERN.search(record.getMessage())
    return legacy_type.group(1) if legacy_type else None


def _safe_stack_trace(record: logging.LogRecord) -> list[str] | None:
    """Keep traceback locations while deliberately excluding exception text."""
    if not record.exc_info or record.exc_info[2] is None:
        return None
    return [
        f"{frame.filename}:{frame.lineno} in {frame.name}"
        for frame in traceback.extract_tb(record.exc_info[2])
    ]


class JsonFormatter(logging.Formatter):
    """Serialize an explicit safe field allowlist as one JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, timezone.utc)
        payload: dict[str, Any] = {
            "timestamp": timestamp.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": _event_for(record),
            "message": record.getMessage(),
        }

        request_id = _request_id_for(record)
        if request_id is not None:
            payload["request_id"] = request_id
        for field in _RECORD_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)

        exception_type = _exception_type_for(record)
        if exception_type is not None:
            payload["exception_type"] = exception_type
        stack_trace = _safe_stack_trace(record)
        if stack_trace is not None:
            payload["stack_trace"] = stack_trace
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


class DevelopmentFormatter(logging.Formatter):
    """Render the same event vocabulary in a concise readable form."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = _request_id_for(record) or "-"
        exception_type = _exception_type_for(record)
        suffix = f" exception_type={exception_type}" if exception_type else ""
        return (
            f"{record.levelname} {record.name} event={_event_for(record)} "
            f"request_id={request_id} {record.getMessage()}{suffix}"
        )


def configure_logging(app_env: AppEnvironment) -> None:
    """Configure one application handler without accumulating duplicates."""
    logger = logging.getLogger("simo_os")
    for handler in list(logger.handlers):
        if getattr(handler, _MANAGED_HANDLER_ATTRIBUTE, False):
            logger.removeHandler(handler)
            handler.close()

    handler = logging.StreamHandler()
    setattr(handler, _MANAGED_HANDLER_ATTRIBUTE, True)
    if app_env is AppEnvironment.PRODUCTION:
        handler.setFormatter(JsonFormatter())
        logger.propagate = False
    else:
        handler.setFormatter(DevelopmentFormatter())
        # Pytest's caplog and development tooling commonly observe the root
        # logger; production remains isolated so every emitted line is JSON.
        logger.propagate = True
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
