"""AuthService — authenticates against the `users` table.

Sprint 003. Unlike app/activity and app/notifications (Sprint 001 module-
level singletons, per ADR-001/ADR-019), this is route-level code that takes
a request-scoped session via get_db() — the pattern ADR-019 reserves for
anything built after the database already existed.

Sprint 009 — every user now belongs to a tenant. `signup()` creates the
Tenant (reusing app.tenants.service.tenant_service, not duplicating its
slugify logic) and the first User (role="Owner") together; `create_user()`
requires a tenant_id, no longer optional.

Sprint 010 — `role` is now UserRole, a real enum (app/auth/models.py),
not a free string. `signup()` always assigns UserRole.OWNER; there is
still no path that creates a Staff user (Sprint 011's invitations).
"""

import uuid

from sqlalchemy.orm import Session

from app.auth.models import SignupRequest, UserOut, UserRole
from app.auth.security import hash_password, verify_password
from app.database import crud
from app.database.models import Tenant, User
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service


class EmailAlreadyRegisteredError(Exception):
    """Raised by signup() when the email is already taken. Caught by the
    router and turned into a 409 — checked explicitly, before any row is
    written, so a duplicate signup never leaves an orphaned tenant behind."""


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
        tenant_id: uuid.UUID,
        name: str,
        email: str,
        password: str,
        role: str | None = None,
    ) -> User:
        return crud.create_user(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
        )

    def signup(self, db: Session, data: SignupRequest) -> tuple[Tenant, User]:
        """Creates a new company workspace and its first (Owner) user.

        Email availability is checked first, before the tenant is created,
        so a duplicate-email signup never leaves an orphaned tenant with no
        user — see EmailAlreadyRegisteredError.
        """
        if crud.get_user_by_email(db, data.email) is not None:
            raise EmailAlreadyRegisteredError(data.email)

        tenant = tenant_service.create(db, TenantCreate(name=data.company_name))
        user = self.create_user(
            db,
            tenant_id=tenant.id,
            name=data.name,
            email=data.email,
            password=data.password,
            role=UserRole.OWNER.value,
        )
        return tenant, user

    def build_user_out(self, db: Session, user: User) -> UserOut:
        """UserOut needs `tenant_name`, which isn't a column on `users` —
        not derivable via plain from_attributes validation, so built by
        hand. No SQLAlchemy relationship() is used anywhere in this
        codebase (plain FK columns + explicit lookups, matching
        app.quotes/app.projects' customer_id convention) — kept consistent
        here rather than introducing one just for this.
        """
        tenant = crud.get_tenant_by_id(db, user.tenant_id)
        return UserOut(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            tenant_id=user.tenant_id,
            tenant_name=tenant.name if tenant is not None else "",
        )


auth_service = AuthService()
