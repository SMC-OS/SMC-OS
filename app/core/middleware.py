"""HTTP request correlation and safe completion logging."""

import logging
import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.logging import request_id_context


logger = logging.getLogger("simo_os")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def matched_route_path(request: Request) -> str | None:
    """Return only the router template, never a concrete request URL."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    return route_path if isinstance(route_path, str) else None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a validated request ID and emit one safe completion event."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        incoming = request.headers.get("X-Request-ID")
        request_id = (
            incoming
            if incoming and REQUEST_ID_PATTERN.fullmatch(incoming)
            else str(uuid.uuid4())
        )
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            try:
                logger.info(
                    "HTTP request completed",
                    extra={
                        "event": "http_request_completed",
                        "request_id": request_id,
                        "method": request.method,
                        "path": matched_route_path(request),
                        "status_code": status_code,
                        "duration_ms": round(
                            (time.perf_counter() - started_at) * 1000,
                            3,
                        ),
                    },
                )
            finally:
                request_id_context.reset(token)
