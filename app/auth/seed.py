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

from app.auth.models import UserRole
from app.auth.service import auth_service
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service


def seed_users() -> None:
    db = SessionLocal()
    try:
        if crud.count_users(db) > 0:
            return  # already seeded
        # Deliberately not auth_service.signup() (which now defaults its
        # new Owner to unverified — Sprint 039 Production Readiness Defect
        # Gate, Blocker 1): this account is provisioned directly by app
        # startup, not the public self-signup flow, so create_user()'s
        # own default (email_verified=True — "this is a real,
        # already-established user") is the correct one here, same as
        # every test fixture that creates a user this same direct way.
        tenant = tenant_service.create(db, TenantCreate(name="Default Workspace"))
        auth_service.create_user(
            db,
            tenant_id=tenant.id,
            name="Simo",
            email=settings.seed_admin_email,
            password=settings.seed_admin_password,
            role=UserRole.OWNER.value,
        )
    finally:
        db.close()
