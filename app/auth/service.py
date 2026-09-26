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
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.auth.dependencies import has_active_billing_access, is_verification_required
from app.auth.models import SignupRequest, UserOut, UserRole
from app.auth.password_policy import password_exceeds_max_bytes
from app.auth.security import PasswordTooLongError, hash_password, verify_password
from app.billing.trial import start_trial_if_eligible
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
        email_verified: bool = True,
        grant_legacy_billing_access: bool = True,
    ) -> User:
        """`email_verified` defaults to True: every existing caller of this
        low-level method (test fixtures, app/auth/seed.py, and
        InvitationService.accept_invitation — see its own call site for
        why an invited user is already effectively proven, having clicked
        a real emailed link with a token) is asserting "this is a real,
        already-established user," not running the public self-signup
        flow. Only signup() below explicitly opts out, since that is the
        one path where nothing has yet confirmed the caller controls the
        email address they typed in (Sprint 039 Production Readiness
        Defect Gate, Blocker 1).

        `grant_legacy_billing_access` is the exact same reasoning applied
        to Sprint 039's final auth + trial gate: every one of those same
        callers represents a tenant that already exists, not a fresh
        public signup (which gets a no-card trial instead, see signup()), so
        it defaults to giving the tenant an already-active, grandfathered
        Subscription (idempotent — a no-op if one already exists) rather
        than leaving it to fail the new require_billing_access dependency.
        Only signup() opts out, for the same reason.
        """
        user = crud.create_user(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
            email_verified_at=datetime.now(timezone.utc) if email_verified else None,
        )
        if grant_legacy_billing_access and crud.get_subscription_by_tenant_id(db, tenant_id) is None:
            crud.upsert_subscription(
                db,
                tenant_id=tenant_id,
                plan="pro",
                billing_period="monthly",
                status="active",
                legacy_grandfathered=True,
            )
            # crud.upsert_subscription()'s own commit (expire_on_commit,
            # SQLAlchemy's default) expires every object already loaded on
            # this session, including `user` above — already fresh from
            # crud.create_user()'s own commit+refresh. Without this, a
            # caller that later accesses `user`'s attributes after this
            # method returns (e.g. once its own `db` session has closed)
            # hits a DetachedInstanceError trying to lazily reload them.
            db.refresh(user)
        return user

    def signup(self, db: Session, data: SignupRequest) -> tuple[Tenant, User]:
        """Creates a new company workspace and its first (Owner) user.

        Email availability is checked first, before the tenant is created,
        so a duplicate-email signup never leaves an orphaned tenant with no
        user — see EmailAlreadyRegisteredError.
        """
        if crud.get_user_by_email(db, data.email) is not None:
            raise EmailAlreadyRegisteredError(data.email)
        # Defence in depth behind SignupRequest's validator: an unhashable
        # password must fail before the tenant is committed, not after.
        if password_exceeds_max_bytes(data.password):
            raise PasswordTooLongError()

        tenant = tenant_service.create(db, TenantCreate(name=data.company_name))
        user = self.create_user(
            db,
            tenant_id=tenant.id,
            name=data.name,
            email=data.email,
            password=data.password,
            role=UserRole.OWNER.value,
            email_verified=False,
            # A new public signup is never a grandfathered legacy tenant.
            grant_legacy_billing_access=False,
        )
        # Phase B — the 14-day free trial starts with the workspace. No
        # card, no Stripe Checkout: payment details are only requested
        # when the owner subscribes (app/billing/trial.py). Workspace
        # access still waits for email verification (require_verified_email
        # runs before require_billing_access).
        start_trial_if_eligible(db, tenant.id, plan=data.plan, billing_period=data.billing_period)
        db.refresh(user)
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
        subscription = crud.get_subscription_by_tenant_id(db, user.tenant_id)
        return UserOut(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            tenant_id=user.tenant_id,
            tenant_name=tenant.name if tenant is not None else "",
            email_verified_at=user.email_verified_at,
            verification_required=is_verification_required(user),
            billing_access_required=not has_active_billing_access(subscription),
        )


auth_service = AuthService()
