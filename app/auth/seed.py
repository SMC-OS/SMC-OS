"""Seed one owner account so login has something to authenticate against.

Guarded like app/activity/seed.py / app/notifications/seed.py — only runs
if the `users` table is empty, so restarts never create duplicates.
Credentials come from settings (.env), never hardcoded here.
"""

from app.auth.service import auth_service
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal


def seed_users() -> None:
    db = SessionLocal()
    try:
        if crud.count_users(db) > 0:
            return  # already seeded
        auth_service.create_user(
            db,
            name="Simo",
            email=settings.seed_admin_email,
            password=settings.seed_admin_password,
            role="Owner",
        )
    finally:
        db.close()
