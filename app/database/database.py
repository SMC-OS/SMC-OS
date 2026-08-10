"""SQLAlchemy engine/session setup for SIMO OS.

Sprint 002 introduced the database layer, reading DATABASE_URL straight from
the environment via python-dotenv. Sprint 003 routes that same value through
app/core/config.py's Settings instead, now that the settings module exists.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

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
