"""Global exception handlers.

Sprint 003. Registered on the FastAPI app in app/main.py. Turns the raw-500
bug documented in docs/API_SPEC.md — an unrecognised /quote material
raising an unhandled KeyError — into a real 400, adds a cleaner 422 body
for validation errors, and adds a catch-all so an unexpected exception
never leaks a stack trace to the client.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import request_id_context
from app.core.middleware import matched_route_path
from app.quotes.validator import DimensionError

logger = logging.getLogger("simo_os")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # jsonable_encoder, not raw exc.errors(): a field_validator that
        # raises ValueError (e.g. app/appointments/models.py's
        # scheduled_at check) puts the live exception object in each
        # error's ctx["error"], which plain json.dumps can't serialize.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Invalid request", "errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"Unrecognised value: {exc.args[0]!r}"},
        )

    @app.exception_handler(DimensionError)
    async def dimension_error_handler(request: Request, exc: DimensionError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", None) or request_id_context.get()
        logger.error(
            "Unhandled exception",
            extra={
                "event": "unhandled_exception",
                "request_id": request_id,
                "method": request.method,
                "path": matched_route_path(request),
                "exception_type": type(exc).__name__,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
            headers={"X-Request-ID": request_id} if request_id else None,
        )
