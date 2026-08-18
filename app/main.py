"""FastAPI application factory and import-safe module entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.activity.router import router as activity_router
from app.activity.seed import seed_activity
from app.api.v1 import api_router
from app.auth.seed import seed_users
from app.core.config import Settings, settings
from app.core.errors import register_exception_handlers
from app.core.health import ReadinessProbe, create_health_router, probe_database
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.startup import create_lifespan
from app.materials.seed import seed_materials
from app.notifications.router import router as notifications_router
from app.notifications.seed import seed_notifications

DEFAULT_SEEDERS = (
    seed_activity,
    seed_notifications,
    seed_users,
    seed_materials,
)
logger = logging.getLogger("simo_os")


def create_runtime_lifespan(runtime_settings: Settings):
    """Configure logging before startup and safely report startup failures."""
    startup_lifespan = create_lifespan(runtime_settings, DEFAULT_SEEDERS)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(runtime_settings.app_env)
        startup_complete = False
        try:
            async with startup_lifespan(application):
                startup_complete = True
                yield
        except Exception as exc:
            if not startup_complete:
                logger.error(
                    "Application startup failed",
                    extra={
                        "event": "startup_failed",
                        "exception_type": type(exc).__name__,
                    },
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
            raise

    return lifespan


def create_app(
    settings_override: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    """Assemble an app whose runtime initialization runs during lifespan."""
    runtime_settings = settings_override or settings
    application = FastAPI(
        title="Simo OS",
        version="0.1.0",
        description="AI Operating System",
        lifespan=create_runtime_lifespan(runtime_settings),
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added after CORS so request context is the outer user middleware and
    # therefore also covers preflight responses.
    application.add_middleware(RequestContextMiddleware)

    register_exception_handlers(application)

    # Sprint 003: every route below (except / and /health, which stay
    # unversioned as infra/health-check endpoints) is mounted under /api/v1.
    application.include_router(api_router)
    application.include_router(activity_router, prefix="/api/v1")
    application.include_router(notifications_router, prefix="/api/v1")
    application.add_api_route("/", root, methods=["GET"])
    configured_readiness_probe = (
        readiness_probe if readiness_probe is not None else probe_database
    )
    application.include_router(
        create_health_router(
            configured_readiness_probe,
            readiness_timeout_seconds=runtime_settings.readiness_timeout_seconds,
        )
    )
    return application


def root():
    return {
        "message": "Welcome to Simo OS",
        "status": "running",
    }


app = create_app()
