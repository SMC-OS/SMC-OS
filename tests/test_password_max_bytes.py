"""bcrypt's 72-byte input limit, handled at every password boundary.

bcrypt 5 raises ValueError for input over 72 bytes. Before this hotfix a
long password reached hash_password (signup, reset, invite accept) or
verify_password (login) and surfaced as a 500. The limit is UTF-8 BYTES:
the Unicode cases below are well under 72 characters but over 72 bytes.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth.models import SignupRequest
from app.auth.password_policy import PASSWORD_TOO_LONG_MESSAGE, validate_password_strength
from app.auth.password_reset_service import password_reset_service
from app.auth.security import PasswordTooLongError, hash_password, verify_password
from app.auth.service import auth_service
from app.core.errors import register_exception_handlers
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

# A: exactly 72 ASCII bytes, meets the policy.
ASCII_72 = "Aa1!" + "a" * 68
# B: 73 ASCII bytes.
ASCII_73 = ASCII_72 + "a"
# C: 38 characters, 72 UTF-8 bytes ("é" is 2 bytes).
UNICODE_72_BYTES = "Aa1!" + "é" * 34
# D: 39 characters, 74 UTF-8 bytes — far under 72 characters.
UNICODE_74_BYTES = "Aa1!" + "é" * 35
# Emoji are 4 bytes each: 22 characters, 76 bytes.
EMOJI_76_BYTES = "Aa1!" + "\U0001F600" * 18
# E / F
VALID = "Correct-Horse-Battery-1!"
WEAK = "short"

TOO_LONG = [ASCII_73, UNICODE_74_BYTES, EMOJI_76_BYTES]


def test_fixture_byte_and_character_lengths():
    assert len(ASCII_72.encode()) == 72 and len(ASCII_73.encode()) == 73
    assert len(UNICODE_72_BYTES) == 38 and len(UNICODE_72_BYTES.encode()) == 72
    assert len(UNICODE_74_BYTES) == 39 and len(UNICODE_74_BYTES.encode()) == 74
    assert len(EMOJI_76_BYTES) == 22 and len(EMOJI_76_BYTES.encode()) == 76


# ------------------------------------------------------------ policy


@pytest.mark.parametrize("password", [ASCII_72, UNICODE_72_BYTES, VALID])
def test_policy_accepts_up_to_72_bytes(password):
    assert validate_password_strength(password) == password


@pytest.mark.parametrize("password", TOO_LONG)
def test_policy_rejects_over_72_bytes(password):
    with pytest.raises(ValueError, match="at most 72 bytes"):
        validate_password_strength(password)


def test_policy_still_rejects_weak_passwords():
    with pytest.raises(ValueError, match="at least 10 characters"):
        validate_password_strength(WEAK)


# ------------------------------------------------- hashing boundary


@pytest.mark.parametrize("password", [ASCII_72, UNICODE_72_BYTES])
def test_hash_and_verify_at_the_72_byte_boundary(password):
    stored = hash_password(password)
    assert verify_password(password, stored)
    assert not verify_password(password[:-1], stored)


@pytest.mark.parametrize("password", TOO_LONG)
def test_hash_refuses_over_72_bytes_without_truncating(password):
    with pytest.raises(PasswordTooLongError) as excinfo:
        hash_password(password)
    assert str(excinfo.value) == PASSWORD_TOO_LONG_MESSAGE
    assert password not in str(excinfo.value)


def test_long_input_never_matches_the_hash_of_its_first_72_bytes():
    """No silent truncation: a password that merely starts with the stored
    password is not accepted."""
    stored = hash_password(ASCII_72)
    assert verify_password(ASCII_73, stored) is False


@pytest.mark.parametrize("password", TOO_LONG)
def test_verify_answers_false_for_over_long_input(password):
    assert verify_password(password, hash_password(VALID)) is False


def test_existing_hashes_still_verify():
    stored = hash_password(VALID)
    assert verify_password(VALID, stored)
    assert not verify_password("Wrong-Password-1!", stored)


def test_unrelated_bcrypt_errors_are_not_disguised():
    with pytest.raises(ValueError) as excinfo:
        verify_password(VALID, "not-a-bcrypt-hash")
    assert not isinstance(excinfo.value, PasswordTooLongError)


def test_boundary_error_maps_to_422():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        hash_password(ASCII_73)

    r = TestClient(app).get("/boom")
    assert r.status_code == 422
    assert r.json() == {"detail": PASSWORD_TOO_LONG_MESSAGE}


# ------------------------------------------------------------- HTTP


def _email(label: str) -> str:
    return f"pytest-pw72-{label}-{uuid.uuid4().hex[:8]}@example.invalid"


def _delete_tenants(names: list[str]) -> None:
    db = SessionLocal()
    try:
        for tenant in db.scalars(select(Tenant).where(Tenant.name.in_(names))).all():
            user_ids = [u.id for u in db.scalars(select(User).where(User.tenant_id == tenant.id))]
            if user_ids:
                db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id.in_(user_ids)))
                db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(user_ids)))
            for model in (Invitation, Communication, ActivityLog, Subscription, User):
                db.execute(delete(model).where(model.tenant_id == tenant.id))
            db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()
    finally:
        db.close()


def _tenant_exists(name: str) -> bool:
    db = SessionLocal()
    try:
        return db.scalar(select(Tenant).where(Tenant.name == name)) is not None
    finally:
        db.close()


def _user_exists(email: str) -> bool:
    db = SessionLocal()
    try:
        return crud.get_user_by_email(db, email) is not None
    finally:
        db.close()


@pytest.fixture()
def tenant_names():
    names: list[str] = []
    yield names
    _delete_tenants(names)


def _signup(client, tenant_names, password):
    company = f"Pytest PW72 Co {uuid.uuid4().hex[:8]}"
    tenant_names.append(company)
    email = _email("signup")
    r = client.post(
        "/api/v1/auth/signup",
        json={"company_name": company, "name": "PW72", "email": email, "password": password},
    )
    return r, company, email


# SIGNUP


@pytest.mark.parametrize("password", [ASCII_72, UNICODE_72_BYTES, VALID])
def test_signup_accepts_passwords_up_to_72_bytes(client, tenant_names, password):
    r, _, email = _signup(client, tenant_names, password)
    assert r.status_code == 201
    assert client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200


@pytest.mark.parametrize("password", TOO_LONG)
def test_signup_rejects_over_72_bytes_without_creating_anything(client, tenant_names, password):
    r, company, email = _signup(client, tenant_names, password)
    assert r.status_code == 422
    assert PASSWORD_TOO_LONG_MESSAGE in r.text
    assert password not in r.text
    assert not _tenant_exists(company)
    assert not _user_exists(email)


def test_signup_rejects_weak_password(client, tenant_names):
    r, company, _ = _signup(client, tenant_names, WEAK)
    assert r.status_code == 422
    assert not _tenant_exists(company)


def test_signup_service_guard_leaves_no_orphan_tenant(tenant_names):
    """Defence in depth: even a request object that skipped validation is
    refused before the tenant row is written."""
    company = f"Pytest PW72 Service {uuid.uuid4().hex[:8]}"
    tenant_names.append(company)
    data = SignupRequest.model_construct(
        company_name=company, name="PW72", email=_email("svc"), password=ASCII_73, plan=None, billing_period=None
    )
    db = SessionLocal()
    try:
        with pytest.raises(PasswordTooLongError):
            auth_service.signup(db, data)
    finally:
        db.close()
    assert not _tenant_exists(company)


# LOGIN


@pytest.mark.parametrize("password", TOO_LONG)
def test_login_with_over_long_password_is_a_normal_401(client, tenant_names, password):
    r, _, email = _signup(client, tenant_names, VALID)
    assert r.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 401
    assert login.json()["detail"] == "Incorrect email or password"


def test_login_with_over_long_password_for_unknown_email_is_identical(client):
    r = client.post("/api/v1/auth/login", json={"email": _email("nobody"), "password": ASCII_73})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password"


# PASSWORD RESET


@pytest.fixture()
def reset_user(tenant_names):
    company = f"Pytest PW72 Reset {uuid.uuid4().hex[:8]}"
    tenant_names.append(company)
    email = _email("reset")
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=company))
        user = auth_service.create_user(
            db, tenant_id=tenant.id, name="PW72", email=email, password=VALID, role="Owner"
        )
        raw = secrets.token_urlsafe(32)
        token = crud.create_password_reset_token(
            db,
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        token_id = token.id
    finally:
        db.close()
    return email, raw, token_id


def _token_used(token_id) -> bool:
    db = SessionLocal()
    try:
        return db.get(PasswordResetToken, token_id).used_at is not None
    finally:
        db.close()


@pytest.mark.parametrize("password", TOO_LONG)
def test_reset_rejects_over_72_bytes_and_keeps_token_and_old_password(client, reset_user, password):
    email, raw, token_id = reset_user
    r = client.post("/api/v1/auth/password/reset", json={"token": raw, "new_password": password})
    assert r.status_code == 422
    assert PASSWORD_TOO_LONG_MESSAGE in r.text
    assert password not in r.text
    assert not _token_used(token_id)
    assert client.post("/api/v1/auth/login", json={"email": email, "password": VALID}).status_code == 200
    # The same link still works with an acceptable password.
    ok = client.post("/api/v1/auth/password/reset", json={"token": raw, "new_password": UNICODE_72_BYTES})
    assert ok.status_code == 200
    assert _token_used(token_id)
    assert client.post("/api/v1/auth/login", json={"email": email, "password": UNICODE_72_BYTES}).status_code == 200


def test_reset_service_guard_does_not_consume_the_token(reset_user):
    _, raw, token_id = reset_user
    db = SessionLocal()
    try:
        with pytest.raises(PasswordTooLongError):
            password_reset_service.reset_password(db, raw, ASCII_73)
    finally:
        db.close()
    assert not _token_used(token_id)


# INVITE ACCEPTANCE


@pytest.fixture()
def invite(client, tenant_names):
    company = f"Pytest PW72 Invite {uuid.uuid4().hex[:8]}"
    tenant_names.append(company)
    owner_email = _email("owner")
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=company))
        auth_service.create_user(
            db, tenant_id=tenant.id, name="PW72 Owner", email=owner_email, password=VALID, role="Owner"
        )
    finally:
        db.close()
    token = client.post("/api/v1/auth/login", json={"email": owner_email, "password": VALID}).json()["access_token"]
    invitee = _email("invitee")
    created = client.post(
        "/api/v1/invitations", json={"email": invitee}, headers={"Authorization": f"Bearer {token}"}
    ).json()
    return created["token"], invitee


@pytest.mark.parametrize("password", TOO_LONG)
def test_invite_accept_rejects_over_72_bytes_and_stays_usable(client, invite, password):
    raw, invitee = invite
    url = f"/api/v1/invitations/token/{raw}/accept"
    r = client.post(url, json={"name": "PW72 Staff", "password": password})
    assert r.status_code == 422
    assert PASSWORD_TOO_LONG_MESSAGE in r.text
    assert password not in r.text
    assert not _user_exists(invitee)
    assert client.get(f"/api/v1/invitations/token/{raw}").json()["status"] == "pending"
    ok = client.post(url, json={"name": "PW72 Staff", "password": ASCII_72})
    assert ok.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": invitee, "password": ASCII_72}).status_code == 200


# CHANGE PASSWORD


@pytest.mark.parametrize("password", TOO_LONG)
def test_change_password_rejects_over_72_bytes(client, tenant_names, password):
    r, _, email = _signup(client, tenant_names, VALID)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    change = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": VALID, "new_password": password},
        headers=headers,
    )
    assert change.status_code == 422
    assert PASSWORD_TOO_LONG_MESSAGE in change.text
    assert password not in change.text


def test_change_password_with_over_long_current_password_is_a_wrong_password(client, tenant_names):
    r, _, _ = _signup(client, tenant_names, VALID)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    change = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": ASCII_73, "new_password": UNICODE_72_BYTES},
        headers=headers,
    )
    assert change.status_code == 400
    assert change.json()["detail"] == "Your current password is incorrect."


# ------------------------------------------------ no password echo


def test_missing_field_error_does_not_echo_the_password(client):
    r = client.post(
        "/api/v1/auth/signup",
        json={"company_name": "Pytest PW72 Echo", "email": _email("echo"), "password": VALID},
    )
    assert r.status_code == 422
    assert VALID not in r.text


def test_current_password_is_never_echoed(client, tenant_names):
    r, _, _ = _signup(client, tenant_names, VALID)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    secret = "S" * 300  # over the field's max_length, so Pydantic rejects it
    change = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": secret, "new_password": UNICODE_72_BYTES},
        headers=headers,
    )
    assert change.status_code == 422
    assert secret not in change.text
