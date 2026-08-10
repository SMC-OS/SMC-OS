"""SQLAlchemy engine/session setup for SIMO OS.

Sprint 002 introduces the database layer. DATABASE_URL is read straight from
the environment (via python-dotenv, already a project dependency) rather than
through a dedicated settings module — app/core/config.py (pydantic-settings)
is explicitly Sprint 003 scope per docs/DECISIONS.md, and this file
intentionally does not anticipate it.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Load .env from the repository root if present. A no-op if the file doesn't
# exist (e.g. a future deployment that injects env vars another way).
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://simo:simo@localhost:5432/simo_os"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for every model in app/database/models.py."""


def get_db():
    """FastAPI dependency — yields a session, closes it after the request.

    Not wired into any route in Sprint 002 (no new API surface this sprint,
    per docs/SPRINTS/sprint-002.md). Provided so the Postgres-backed
    repositories (app/activity, app/notifications) and future route work
    have a ready-made session dependency to use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
