"""Unauthenticated liveness and database-aware readiness endpoints."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.database import engine


logger = logging.getLogger("simo_os")

ReadinessProbe = Callable[[float], Awaitable[None]]


def health():
    return {"status": "healthy"}


async def probe_database(timeout_seconds: float) -> None:
    """Run the bounded database connectivity check without blocking the event loop."""

    def execute_probe() -> None:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    async with asyncio.timeout(timeout_seconds):
        await asyncio.to_thread(execute_probe)


def create_health_router(
    readiness_probe: ReadinessProbe,
    *,
    readiness_timeout_seconds: float = 2.0,
) -> APIRouter:
    """Build liveness and readiness routes with an injectable readiness boundary."""
    router = APIRouter()

    router.add_api_route("/health", health, methods=["GET"])

    @router.get("/ready")
    async def ready():
        try:
            await readiness_probe(readiness_timeout_seconds)
        except (SQLAlchemyError, TimeoutError, OSError) as exc:
            logger.warning("readiness_failed exception_type=%s", type(exc).__name__)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "database": "unreachable"},
            )
        return {"status": "ready", "database": "reachable"}

    return router
