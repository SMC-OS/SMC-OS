"""Sprint 039 Production Readiness Defect Gate, final auth gate —
Blocker A: password policy.

Owner manual staging acceptance found `123` created a real GeoCore
account. Before this file's fix, SignupRequest.password
(app/auth/models.py) was a bare `str` with zero validation — see
app.auth.password_policy's docstring for the full rationale — and
ResetPasswordRequest.new_password only enforced an 8-character
minimum with no character-class rules, and
AcceptInvitationRequest.password (app/invitations/models.py) also had
zero validation. This file proves all three now share one policy
(minimum 10 characters, at least one uppercase letter, one lowercase
letter, one number, one special character — NOT a first-character-
uppercase requirement), while login stays fully compatible with a
historical/legacy weak password (the policy is never consulted there
— it only applies where a password is newly chosen).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete

from app.auth.password_policy import validate_password_strength
from app.auth.service import auth_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailVerificationToken,
    Invitation,
    PasswordResetToken,
    Subscription,
    Tenant,
    User,
)
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

RUN_ID = uuid.uuid4().hex[:8]
STRONG_PASSWORD = "Pytest-Strong-Password-1!"


def _unique_email(label: str) -> str:
    return f"pytest-password-policy-{RUN_ID}-{label}@example.invalid"


def _cleanup(*, tenant_name: str, emails: list[str]) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(Invitation).where(Invitation.email.in_(emails)))
        user_ids = [u.id for u in db.query(User).filter(User.email.in_(emails)).all()]
        if user_ids:
            db.execute(
                delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(user_ids))
            )
            db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id.in_(user_ids)))
        db.execute(delete(User).where(User.email.in_(emails)))
        tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
        if tenant is not None:
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
            db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
        db.execute(delete(Tenant).where(Tenant.name == tenant_name))
        db.commit()
    finally:
        db.close()


def _signup_payload(email: str, password: str, *, company: str) -> dict:
    return {
        "company_name": company,
        "name": "Pytest Owner",
        "email": email,
        "password": password,
    }


# ---------------------------------------------------------------------
# Unit-level: the shared validator itself.
# ---------------------------------------------------------------------


def test_validator_rejects_123():
    try:
        validate_password_strength("123")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "10 characters" in str(exc)


def test_validator_rejects_too_short():
    try:
        validate_password_strength("Ab1!Ab1!")  # 8 chars, otherwise valid
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "10 characters" in str(exc)


def test_validator_rejects_missing_uppercase():
    try:
        validate_password_strength("lowercase-1!only")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "uppercase" in str(exc)


def test_validator_rejects_missing_lowercase():
    try:
        validate_password_strength("UPPERCASE-1!ONLY")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "lowercase" in str(exc)


def test_validator_rejects_missing_number():
    try:
        validate_password_strength("No-Numbers-Here!")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "number" in str(exc)


def test_validator_rejects_missing_symbol():
    try:
        validate_password_strength("NoSymbolsHere123")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "special character" in str(exc)


def test_validator_accepts_a_valid_strong_password():
    assert validate_password_strength(STRONG_PASSWORD) == STRONG_PASSWORD


def test_validator_does_not_require_the_first_character_to_be_uppercase():
    # Explicit ticket requirement: "Do NOT require the first character
    # specifically to be uppercase." An uppercase letter anywhere in the
    # password (not just position 0) must satisfy the requirement.
    assert validate_password_strength("password-Strong-1!") == "password-Strong-1!"


# ---------------------------------------------------------------------
# HTTP-level: signup (SignupRequest.password).
# ---------------------------------------------------------------------


def test_signup_rejects_123(client):
    email = _unique_email("signup-123")
    company = f"Pytest Password Policy Signup Co {RUN_ID}"
    try:
        r = client.post(
            "/api/v1/auth/signup", json=_signup_payload(email, "123", company=company)
        )
        assert r.status_code == 422
        # Never echo the submitted password back in an error body.
        assert "123" not in r.text or '"password"' not in r.text
    finally:
        _cleanup(tenant_name=company, emails=[email])


def test_signup_accepts_a_valid_strong_password(client):
    email = _unique_email("signup-strong")
    company = f"Pytest Password Policy Signup Strong Co {RUN_ID}"
    try:
        r = client.post(
            "/api/v1/auth/signup",
            json=_signup_payload(email, STRONG_PASSWORD, company=company),
        )
        assert r.status_code == 201
    finally:
        _cleanup(tenant_name=company, emails=[email])


# ---------------------------------------------------------------------
# HTTP-level: password reset (ResetPasswordRequest.new_password) uses
# the identical policy — see tests/test_password_reset.py for the full
# token-lifecycle coverage; this file only proves policy parity.
# ---------------------------------------------------------------------


def test_reset_uses_the_identical_policy_as_signup(client):
    import hashlib
    import secrets
    from datetime import timedelta

    from app.database import crud as _crud

    email = _unique_email("reset-policy")
    company = f"Pytest Password Policy Reset Co {RUN_ID}"
    try:
        db = SessionLocal()
        try:
            tenant = tenant_service.create(db, TenantCreate(name=company))
            user = auth_service.create_user(
                db,
                tenant_id=tenant.id,
                name="Pytest User",
                email=email,
                password="whatever-the-legacy-password-was",
                role="Owner",
            )
            raw_token = secrets.token_urlsafe(32)
            _crud.create_password_reset_token(
                db,
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        finally:
            db.close()

        weak = client.post(
            "/api/v1/auth/password/reset", json={"token": raw_token, "new_password": "123"}
        )
        assert weak.status_code == 422

        strong = client.post(
            "/api/v1/auth/password/reset",
            json={"token": raw_token, "new_password": STRONG_PASSWORD},
        )
        assert strong.status_code == 200
    finally:
        _cleanup(tenant_name=company, emails=[email])


# ---------------------------------------------------------------------
# HTTP-level: invitation-accept (AcceptInvitationRequest.password) —
# the third, easily-missed password-creation entry point (no
# "change password while logged in" flow exists in this product).
# ---------------------------------------------------------------------


def test_invite_accept_uses_the_identical_policy_as_signup(client):
    email = _unique_email("invite-owner")
    invitee_email = _unique_email("invite-invitee")
    company = f"Pytest Password Policy Invite Co {RUN_ID}"
    try:
        db = SessionLocal()
        try:
            tenant = tenant_service.create(db, TenantCreate(name=company))
            auth_service.create_user(
                db,
                tenant_id=tenant.id,
                name="Pytest Owner",
                email=email,
                password=STRONG_PASSWORD,
                role="Owner",
            )
        finally:
            db.close()

        login = client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        created = client.post(
            "/api/v1/invitations", json={"email": invitee_email}, headers=headers
        ).json()

        weak = client.post(
            f"/api/v1/invitations/token/{created['token']}/accept",
            json={"name": "New Staffer", "password": "123"},
        )
        assert weak.status_code == 422

        strong = client.post(
            f"/api/v1/invitations/token/{created['token']}/accept",
            json={"name": "New Staffer", "password": STRONG_PASSWORD},
        )
        assert strong.status_code == 200
    finally:
        _cleanup(tenant_name=company, emails=[email, invitee_email])


# ---------------------------------------------------------------------
# Login compatibility — the policy must never be consulted at login,
# so an account whose password predates this policy (or was created
# directly, bypassing the HTTP layer, same as every other
# directly-created fixture user in this suite) keeps working.
# ---------------------------------------------------------------------


def test_existing_login_remains_compatible_with_a_legacy_weak_password(client):
    email = _unique_email("legacy-login")
    company = f"Pytest Password Policy Legacy Co {RUN_ID}"
    legacy_password = "123"  # shorter than even the OLD reset-only 8-char rule
    try:
        db = SessionLocal()
        try:
            tenant = tenant_service.create(db, TenantCreate(name=company))
            auth_service.create_user(
                db,
                tenant_id=tenant.id,
                name="Pytest Legacy User",
                email=email,
                password=legacy_password,
                role="Owner",
            )
        finally:
            db.close()

        r = client.post("/api/v1/auth/login", json={"email": email, "password": legacy_password})
        assert r.status_code == 200
    finally:
        _cleanup(tenant_name=company, emails=[email])
