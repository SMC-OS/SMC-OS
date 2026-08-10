"""AuthService — authenticates against the `users` table.

Sprint 003. Unlike app/activity and app/notifications (Sprint 001 module-
level singletons, per ADR-001/ADR-019), this is route-level code that takes
a request-scoped session via get_db() — the pattern ADR-019 reserves for
anything built after the database already existed.
"""

import uuid

from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.database import crud
from app.database.models import User


class AuthService:
    def authenticate(self, db: Session, email: str, password: str) -> User | None:
        user = crud.get_user_by_email(db, email)
        if user is None or not verify_password(password, user.password_hash):
            return None
        return user

    def create_user(
        self,
        db: Session,
        *,
        name: str,
        email: str,
        password: str,
        role: str | None = None,
    ) -> User:
        return crud.create_user(
            db,
            id=uuid.uuid4(),
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
        )


auth_service = AuthService()
