"""Settings > Security "Change password" — POST /api/v1/auth/password/change.

Pass cases, fail-safely cases and security cases for the signed-in
password change (app/auth/password_change_service.py). No live email
provider is used: Resend is unconfigured in CI, so DeliveryService
records the notification row as failed/unavailable, which is exactly
the "provider failure must not undo the change" path.
"""

import logging
import uuid

import pytest
from sqlalchemy import delete

from app.auth.password_change_service import PasswordChangeService, password_change_service
from app.auth.security import verify_password
from app.auth.service import auth_service
from app.communications.templates import render_password_changed
from app.core.config import settings
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    PasswordResetToken,
    Subscription,
    Tenant,
    User,
)
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

PASSWORD = "Current-Password-123!"
NEW_PASSWORD = "A-Brand-New-Password-456!"
CHANGE_URL = "/api/v1/auth/password/change"


def _unique_email(label: str) -> str:
    return f"pytest-password-change-{label}-{uuid.uuid4().hex[:8]}@example.invalid"


def _login(client, email: str, password: str):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def workspace(client):
    """One tenant with a verified Owner and a verified Staff member."""
    tenant_name = f"Pytest Password Change {uuid.uuid4().hex[:8]}"
    owner_email = _unique_email("owner")
    staff_email = _unique_email("staff")
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=tenant_name))
        owner = auth_service.create_user(
            db, tenant_id=tenant.id, name="Pytest Owner", email=owner_email, password=PASSWORD, role="Owner"
        )
        staff = auth_service.create_user(
            db, tenant_id=tenant.id, name="Pytest Staff", email=staff_email, password=PASSWORD, role="Staff"
        )
        tenant_id, owner_id, staff_id = tenant.id, owner.id, staff.id
    finally:
        db.close()
    owner_token = _login(client, owner_email, PASSWORD).json()["access_token"]
    staff_token = _login(client, staff_email, PASSWORD).json()["access_token"]
    yield {
        "tenant_id": tenant_id,
        "owner": (owner_id, owner_email, owner_token),
        "staff": (staff_id, staff_email, staff_token),
    }
    db = SessionLocal()
    try:
        ids = [owner_id, staff_id]
        db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id.in_(ids)))
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(Communication).where(Communication.tenant_id == tenant_id))
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
        db.execute(delete(User).where(User.id.in_(ids)))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
    finally:
        db.close()


def _password_hash(user_id: uuid.UUID) -> str:
    db = SessionLocal()
    try:
        return db.get(User, user_id).password_hash
    finally:
        db.close()


def _change(client, token: str, current: str = PASSWORD, new: str = NEW_PASSWORD, **extra):
    return client.post(
        CHANGE_URL,
        json={"current_password": current, "new_password": new, **extra},
        headers=_bearer(token),
    )


def _notifications(tenant_id: uuid.UUID) -> list[Communication]:
    db = SessionLocal()
    try:
        return (
            db.query(Communication)
            .filter(Communication.tenant_id == tenant_id, Communication.message_type == "password_changed")
            .all()
        )
    finally:
        db.close()


# ---------------------------------------------------------------- PASS


def test_correct_current_password_changes_it(client, workspace):
    _, email, token = workspace["owner"]
    r = _change(client, token)
    assert r.status_code == 200
    assert _login(client, email, NEW_PASSWORD).status_code == 200
    assert _login(client, email, PASSWORD).status_code == 401


def test_current_session_stays_signed_in_with_the_fresh_token(client, workspace):
    _, email, token = workspace["owner"]
    body = _change(client, token).json()
    assert body["user"]["email"] == email
    assert client.get("/api/v1/auth/me", headers=_bearer(body["access_token"])).status_code == 200


def test_other_sessions_are_revoked(client, workspace):
    _, email, token = workspace["owner"]
    other_device = _login(client, email, PASSWORD).json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=_bearer(other_device)).status_code == 200
    assert _change(client, token).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_bearer(other_device)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 401


def test_change_is_recorded_in_the_activity_log(client, workspace):
    _, email, token = workspace["owner"]
    assert _change(client, token).status_code == 200
    db = SessionLocal()
    try:
        rows = (
            db.query(ActivityLog)
            .filter(ActivityLog.tenant_id == workspace["tenant_id"], ActivityLog.type == "password_changed")
            .all()
        )
    finally:
        db.close()
    assert len(rows) == 1
    assert rows[0].description == email
    assert PASSWORD not in (rows[0].title + (rows[0].description or ""))


def test_notification_goes_to_the_verified_email_without_secrets(client, workspace):
    owner_id, email, token = workspace["owner"]
    assert _change(client, token).status_code == 200
    rows = _notifications(workspace["tenant_id"])
    assert len(rows) == 1
    row = rows[0]
    assert row.recipient == email.lower()
    assert row.subject == "Your GeoCore password was changed"
    for body in (row.body_text, row.body_html):
        assert "no action is required" in body
        assert "/forgot-password" in body
        assert PASSWORD not in body
        assert NEW_PASSWORD not in body
        assert "$2b$" not in body
        assert "token=" not in body


def test_no_notification_for_an_unverified_email(client, workspace):
    owner_id, _, token = workspace["owner"]
    db = SessionLocal()
    try:
        db.get(User, owner_id).email_verified_at = None
        db.commit()
    finally:
        db.close()
    assert _change(client, token).status_code == 200
    assert _notifications(workspace["tenant_id"]) == []


def test_staff_can_change_their_own_password(client, workspace):
    _, email, token = workspace["staff"]
    assert _change(client, token).status_code == 200
    assert _login(client, email, NEW_PASSWORD).status_code == 200


# ------------------------------------------------------ FAIL SAFELY


def test_wrong_current_password_is_rejected_generically(client, workspace):
    owner_id, _, token = workspace["owner"]
    before = _password_hash(owner_id)
    r = _change(client, token, current="Not-The-Password-1!")
    assert r.status_code == 400
    assert r.json()["detail"] == "Your current password is incorrect."
    assert _password_hash(owner_id) == before
    # The session survives a typo.
    assert client.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 200


def test_new_password_must_meet_the_policy(client, workspace):
    owner_id, _, token = workspace["owner"]
    before = _password_hash(owner_id)
    for weak in ("short1!A", "alllowercase-123!", "NoDigitsHere!!", "NoSymbols1234"):
        assert _change(client, token, new=weak).status_code == 422
    assert _password_hash(owner_id) == before


def test_new_password_must_differ_from_the_current_one(client, workspace):
    owner_id, _, token = workspace["owner"]
    before = _password_hash(owner_id)
    r = _change(client, token, new=PASSWORD)
    assert r.status_code == 400
    assert "different" in r.json()["detail"]
    assert _password_hash(owner_id) == before


def test_empty_current_password_is_rejected(client, workspace):
    _, _, token = workspace["owner"]
    assert _change(client, token, current="").status_code == 422


def test_over_long_passwords_fail_safely(client, workspace):
    _, _, token = workspace["owner"]
    assert _change(client, token, new="Aa1!" + "x" * 80).status_code == 422
    assert _change(client, token, current="Aa1!" + "x" * 80).status_code == 400


def test_unauthenticated_request_is_rejected(client):
    r = client.post(CHANGE_URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 401


def test_provider_failure_does_not_roll_back_the_change(client, workspace, monkeypatch, caplog):
    owner_id, email, token = workspace["owner"]

    class ExplodingDelivery:
        def send(self, *args, **kwargs):
            raise RuntimeError("provider down")

    monkeypatch.setattr(password_change_service, "_delivery", ExplodingDelivery())
    with caplog.at_level(logging.WARNING):
        r = _change(client, token)
    assert r.status_code == 200
    assert _login(client, email, NEW_PASSWORD).status_code == 200
    assert "could not be sent" in caplog.text
    assert PASSWORD not in caplog.text and NEW_PASSWORD not in caplog.text


def test_unconfigured_provider_records_the_failure_and_keeps_the_change(client, workspace, monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", None)
    _, email, token = workspace["owner"]
    assert _change(client, token).status_code == 200
    rows = _notifications(workspace["tenant_id"])
    assert len(rows) == 1 and rows[0].status == "failed"
    assert _login(client, email, NEW_PASSWORD).status_code == 200


# ---------------------------------------------------------- SECURITY


@pytest.mark.parametrize(
    "extra",
    [{"user_id": "x"}, {"email": "someone@example.invalid"}, {"id": "x"}],
)
def test_body_cannot_name_another_account(client, workspace, extra):
    staff_id, _, _ = workspace["staff"]
    owner_id, _, owner_token = workspace["owner"]
    staff_before, owner_before = _password_hash(staff_id), _password_hash(owner_id)
    if "user_id" in extra:
        extra = {"user_id": str(staff_id)}
    r = _change(client, owner_token, **extra)
    assert r.status_code == 422
    assert _password_hash(staff_id) == staff_before
    assert _password_hash(owner_id) == owner_before


def test_owner_cannot_change_a_staff_members_password(client, workspace):
    """The Owner's own current password changes the Owner's own account,
    never the Staff member's."""
    staff_id, staff_email, staff_token = workspace["staff"]
    _, _, owner_token = workspace["owner"]
    staff_before = _password_hash(staff_id)
    assert _change(client, owner_token).status_code == 200
    assert _password_hash(staff_id) == staff_before
    assert _login(client, staff_email, PASSWORD).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_bearer(staff_token)).status_code == 200


def test_repeated_wrong_current_passwords_are_rate_limited(client, workspace):
    owner_id, _, token = workspace["owner"]
    for _ in range(settings.password_change_max_attempts):
        assert _change(client, token, current="Wrong-Password-1!").status_code == 400
    blocked = _change(client, token)  # even the right password is refused now
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert verify_password(PASSWORD, _password_hash(owner_id))


def test_rate_limit_is_per_user(client, workspace):
    _, _, owner_token = workspace["owner"]
    _, _, staff_token = workspace["staff"]
    for _ in range(settings.password_change_max_attempts):
        _change(client, owner_token, current="Wrong-Password-1!")
    assert _change(client, staff_token).status_code == 200


def test_response_never_contains_a_password_or_hash(client, workspace):
    owner_id, _, token = workspace["owner"]
    r = _change(client, token)
    text = r.text
    assert PASSWORD not in text and NEW_PASSWORD not in text
    assert "password_hash" not in text
    assert _password_hash(owner_id) not in text


def test_deactivated_user_cannot_change_password(client, workspace):
    owner_id, _, token = workspace["owner"]
    db = SessionLocal()
    try:
        db.get(User, owner_id).is_active = False
        db.commit()
    finally:
        db.close()
    assert _change(client, token).status_code == 401


def test_stored_hash_uses_the_existing_bcrypt_scheme(client, workspace):
    owner_id, _, token = workspace["owner"]
    assert _change(client, token).status_code == 200
    stored = _password_hash(owner_id)
    assert stored.startswith("$2")
    assert verify_password(NEW_PASSWORD, stored)


def test_template_escapes_the_recipient_name():
    rendered = render_password_changed(
        tenant_display_name="GeoCore",
        recipient_name="<script>x</script>",
        changed_at_label="Wednesday 23 September 2026 at 10:00 (UK time)",
        reset_url="https://app.example.invalid/forgot-password",
    )
    assert "<script>" not in rendered.html
    assert rendered.subject == "Your GeoCore password was changed"


def test_service_is_constructor_injectable():
    assert PasswordChangeService(delivery=object())._delivery is not None
