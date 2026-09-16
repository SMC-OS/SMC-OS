"""Sprint 039 Production Readiness Defect Gate — Blocker 2 follow-up
(verification resend/token hotfix).

Reproduces the owner's exact live staging observation (SMC-OS/SMC-OS,
staging HTTP logs for simo-api-staging, 2026-09-16T09:53-10:02 UTC):

    09:53:07  POST /auth/signup                  -> 201  (token T1 issued)
    09:53:44  POST /auth/email/verify/confirm     -> 200  (T1 verifies — genuine success)
    09:53:46  POST /auth/email/verify/confirm     -> 400  (T1 replayed — correctly rejected)
    10:01:23  POST /auth/email/verify/resend      -> 200  (already verified — silently a no-op)
    10:01:47  POST /auth/email/verify/confirm     -> 400  (no new token exists to confirm)
    10:01:51  POST /auth/email/verify/resend      -> 200  (still a no-op, 28s after the last one)

Two real defects, neither a token-invalidation race (the existing
architecture never invalidates a prior token on resend at all — see
app/auth/verification_service.py's send_verification_email, unchanged
here):

1. resend_verification_email() returns an identical HTTP 200
   {"message": "..."} whether it actually queued a new email or
   silently no-op'd because the account was already verified — the
   frontend could not tell these apart, so a resend after verification
   looked like a truthful "check your inbox" with no way to know a
   second email was never coming.
2. The /verify-email page's own second (or later) view of the SAME,
   already-successfully-used link renders as a scary "invalid or
   expired" with no acknowledgement that the account is, in fact,
   already verified — exactly what the owner saw at 09:53:46 and again
   at 10:01:47.

Fix: a dedicated VerificationResendResponse.already_verified flag the
frontend renders honestly, plus (frontend-only, covered in apps/web's
own test suite) an "already verified" state on /verify-email driven by
the viewer's own live auth state rather than the confirm() outcome.

Explicitly NOT changed: confirm()'s HTTP contract for a replayed token
is 400, unchanged — single-use and replay-rejection stay exactly as
strict as before (test_confirm_is_single_use in test_email_
verification.py already covers this and must keep passing unmodified).
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.communications.provider import EmailProviderUnavailable
from app.communications.service import DeliveryService
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailVerificationToken,
    Subscription,
    Tenant,
    User,
)
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

TENANT_NAME = "Pytest Verification Resend Tenant"
USER_EMAIL = "pytest-verification-resend-user@example.invalid"
PASSWORD = "correct-horse-battery-staple"


def _cleanup():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == USER_EMAIL).first()
        if user is not None:
            db.execute(
                delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
            )
        db.execute(delete(User).where(User.email == USER_EMAIL))
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
            db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
            db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()
    finally:
        db.close()


def _issue_raw_token(user_id: uuid.UUID, *, expires_at: datetime) -> str:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db = SessionLocal()
    try:
        crud.create_email_verification_token(
            db, id=uuid.uuid4(), user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
    finally:
        db.close()
    return raw_token


@pytest.fixture()
def user_and_headers(client):
    """A freshly-created (unverified) user, logged in — same shape as
    tests/test_email_verification.py's own fixture."""
    _cleanup()
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=TENANT_NAME))
        user = auth_service.create_user(
            db,
            tenant_id=tenant.id,
            name="Pytest User",
            email=USER_EMAIL,
            password=PASSWORD,
            role="Owner",
            email_verified=False,
        )
    finally:
        db.close()
    r = client.post("/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    yield user, headers
    _cleanup()


class TestResendIsHonestAboutWhatItDid:
    """The core defect: a resend's HTTP 200 must let the caller tell
    "a new email was actually queued" apart from "no-op, you're already
    verified" — the owner's exact live-staging confusion."""

    def test_resend_while_unverified_reports_not_already_verified(
        self, client, user_and_headers
    ):
        _, headers = user_and_headers
        r = client.post("/api/v1/auth/email/verify/resend", headers=headers)
        assert r.status_code == 200
        assert r.json()["already_verified"] is False

    def test_resend_after_verification_reports_already_verified_and_sends_nothing_new(
        self, client, user_and_headers
    ):
        user, headers = user_and_headers
        raw_token = _issue_raw_token(
            user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        confirm = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
        assert confirm.status_code == 200

        db = SessionLocal()
        try:
            tokens_before = (
                db.query(EmailVerificationToken)
                .filter(EmailVerificationToken.user_id == user.id)
                .count()
            )
        finally:
            db.close()

        r = client.post("/api/v1/auth/email/verify/resend", headers=headers)
        assert r.status_code == 200
        assert r.json()["already_verified"] is True

        db = SessionLocal()
        try:
            tokens_after = (
                db.query(EmailVerificationToken)
                .filter(EmailVerificationToken.user_id == user.id)
                .count()
            )
        finally:
            db.close()
        # No new token row — a truthful "no-op", matching the honest
        # already_verified=True the caller just received.
        assert tokens_after == tokens_before


class TestReplayOfASuccessfulTokenStaysRejected:
    """Explicitly NOT relaxed by this hotfix — single-use/replay-
    rejection is a security invariant, not a UX bug. The fix is in how
    the frontend interprets this 400 (covered by apps/web's own test
    suite), never in the backend's contract."""

    def test_replaying_an_already_verified_tokens_second_use_stays_400(
        self, client, user_and_headers
    ):
        user, headers = user_and_headers
        raw_token = _issue_raw_token(
            user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        first = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
        assert first.status_code == 200
        second = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
        assert second.status_code == 400


class TestTokenCoexistenceContract:
    """The explicitly chosen contract (unchanged by this hotfix, now
    regression-tested rather than merely accidental): resend never
    invalidates a still-valid prior token. Every issued token remains
    independently usable until it is itself used or naturally expires."""

    def test_resend_success_the_new_token_works(self, client, user_and_headers):
        user, headers = user_and_headers
        r = client.post("/api/v1/auth/email/verify/resend", headers=headers)
        assert r.status_code == 200
        assert r.json()["already_verified"] is False

        db = SessionLocal()
        try:
            row = (
                db.query(EmailVerificationToken)
                .filter(EmailVerificationToken.user_id == user.id)
                .order_by(EmailVerificationToken.expires_at.desc())
                .first()
            )
        finally:
            db.close()
        assert row is not None

        # Confirm via a freshly-minted raw token bound to the same row
        # shape resend just created (raw token itself is never
        # recoverable from the DB — same reasoning as every other test
        # in this suite that exercises confirm()).
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        db = SessionLocal()
        try:
            db.query(EmailVerificationToken).filter(
                EmailVerificationToken.id == row.id
            ).update({"token_hash": token_hash})
            db.commit()
        finally:
            db.close()

        confirm = client.post("/api/v1/auth/email/verify/confirm", json={"token": raw_token})
        assert confirm.status_code == 200

    def test_previous_token_still_works_after_a_resend(self, client, user_and_headers):
        """The owner's exact "repeated clicks cannot silently invalidate
        a valid link" requirement: issue token A, resend (issues token
        B), then confirm with A — A must still be valid."""
        user, headers = user_and_headers
        token_a = _issue_raw_token(
            user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

        r = client.post("/api/v1/auth/email/verify/resend", headers=headers)
        assert r.status_code == 200
        assert r.json()["already_verified"] is False

        confirm_a = client.post("/api/v1/auth/email/verify/confirm", json={"token": token_a})
        assert confirm_a.status_code == 200

    def test_cooldown_rejection_does_not_touch_the_existing_valid_token(
        self, client, user_and_headers
    ):
        user, headers = user_and_headers
        token_a = _issue_raw_token(
            user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

        first = client.post("/api/v1/auth/email/verify/resend", headers=headers)
        assert first.status_code == 200
        second = client.post("/api/v1/auth/email/verify/resend", headers=headers)
        assert second.status_code == 429

        confirm_a = client.post("/api/v1/auth/email/verify/confirm", json={"token": token_a})
        assert confirm_a.status_code == 200

    def test_repeated_resend_attempts_do_not_destroy_a_usable_token(
        self, client, user_and_headers
    ):
        user, headers = user_and_headers
        token_a = _issue_raw_token(
            user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        for _ in range(3):
            client.post("/api/v1/auth/email/verify/resend", headers=headers)

        confirm_a = client.post("/api/v1/auth/email/verify/confirm", json={"token": token_a})
        assert confirm_a.status_code == 200


class TestResendDeliveryFailureCannotStrandAccount:
    def test_a_provider_failure_during_resend_still_leaves_a_usable_token(
        self, client, user_and_headers
    ):
        user, headers = user_and_headers

        class _AlwaysFailsProvider:
            def send(self, message):
                raise EmailProviderUnavailable("simulated provider outage")

        from app.auth import verification_service as verification_service_module

        original = verification_service_module.email_verification_service._delivery
        verification_service_module.email_verification_service._delivery = DeliveryService(
            provider=_AlwaysFailsProvider()
        )
        try:
            r = client.post("/api/v1/auth/email/verify/resend", headers=headers)
            assert r.status_code == 200
            assert r.json()["already_verified"] is False
        finally:
            verification_service_module.email_verification_service._delivery = original

        db = SessionLocal()
        try:
            row = (
                db.query(EmailVerificationToken)
                .filter(EmailVerificationToken.user_id == user.id)
                .order_by(EmailVerificationToken.expires_at.desc())
                .first()
            )
        finally:
            db.close()
        assert row is not None
        assert row.used_at is None
        assert row.expires_at > datetime.now(timezone.utc)
