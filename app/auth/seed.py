"""Seed one owner account (and its tenant) so login has something to
authenticate against.

Guarded like app/activity/seed.py / app/notifications/seed.py — only runs
if the `users` table is empty, so restarts never create duplicates.
Credentials come from settings (.env), never hardcoded here.

Sprint 009 — every user needs a tenant, so this now goes through
AuthService.signup() (the same path a real company's first signup uses)
rather than a bare create_user() call, giving the seeded owner a real
"Default Workspace" tenant instead of duplicating tenant-creation logic
here.
"""

from app.auth.models import SignupRequest
from app.auth.service import auth_service
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal


def seed_users() -> None:
    db = SessionLocal()
    try:
        if crud.count_users(db) > 0:
            return  # already seeded
        auth_service.signup(
            db,
            SignupRequest(
                company_name="Default Workspace",
                name="Simo",
                email=settings.seed_admin_email,
                password=settings.seed_admin_password,
            ),
        )
    finally:
        db.close()
