"""Testable application startup operations.

Database migrations remain an operator-owned release operation. This module
only validates the upload mount and runs the existing development/test seeders
during FastAPI's lifespan.
"""

from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncContextManager
from uuid import uuid4

from fastapi import FastAPI

from app.core.config import AppEnvironment, Settings

Seeder = Callable[[], None]


def prepare_upload_directory(settings: Settings) -> Path:
    """Return a usable upload directory without touching existing documents."""
    upload_directory = Path(settings.upload_dir).expanduser().resolve(strict=False)

    if settings.app_env is not AppEnvironment.PRODUCTION:
        upload_directory.mkdir(parents=True, exist_ok=True)
        return upload_directory

    if not upload_directory.is_dir():
        raise RuntimeError("UPLOAD_DIR must be an existing directory in production")

    _verify_directory_is_writable(upload_directory)
    return upload_directory


def _verify_directory_is_writable(upload_directory: Path) -> None:
    """Write and remove a private zero-byte probe, leaving mounted data intact."""
    probe = upload_directory / f".simo-os-write-probe-{uuid4().hex}"
    try:
        with probe.open("xb"):
            pass
    except OSError as exc:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            # Preserve the original write error when a mount prevents both
            # probe creation and cleanup.
            pass
        raise RuntimeError("UPLOAD_DIR must be writable in production") from exc

    try:
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError("UPLOAD_DIR probe cleanup failed in production") from exc


def run_seeders(settings: Settings, seeders: Iterable[Seeder]) -> None:
    """Run injected seeders only when the active runtime explicitly allows it."""
    if not settings.seed_data_enabled:
        return

    for seeder in seeders:
        seeder()


def create_lifespan(
    settings: Settings, seeders: Iterable[Seeder]
) -> Callable[[FastAPI], AsyncContextManager[None]]:
    """Build the FastAPI lifespan hook without doing work at import time."""
    configured_seeders = tuple(seeders)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        prepare_upload_directory(settings)
        run_seeders(settings, configured_seeders)
        yield

    return lifespan
