"""Sprint 038, Phase 2 — the Resend webhook (app/communications/webhooks.py,
app/communications/router.py's POST /communications/webhook).

Every request here is a fabricated, locally-signed payload — no real
network call to Resend/Svix anywhere, same "sign it ourselves the same
way the verifier expects" approach tests/test_billing.py uses for Stripe
(there, a mocked stripe.Webhook.construct_event; here, the actual HMAC
computation, since Svix's algorithm is simple enough to do directly and
this is exactly what proves the verifier's own math is right).
"""

import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest

from app.communications.webhooks import WebhookSignatureError, verify_svix_signature
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Communication, EmailSuppression, Tenant
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service
from sqlalchemy import delete

TEST_SECRET = "whsec_" + base64.b64encode(b"pytest-communications-webhook-secret-32b").decode()
TENANT_NAME = "Pytest Communications Webhook Tenant"


def _sign(*, body: bytes, svix_id: str, timestamp: str, secret: str = TEST_SECRET) -> str:
    key = base64.b64decode(secret[len("whsec_"):])
    signed_content = f"{svix_id}.{timestamp}.".encode() + body
    digest = base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode()
    return f"v1,{digest}"


def _cleanup():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            db.execute(delete(EmailSuppression).where(EmailSuppression.tenant_id == tenant.id))
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
            # TenantService.create() logs a real ActivityLog row against the
            # new tenant's own id (ADR-029) — must go before the Tenant row
            # or the FK constraint rejects the delete. Same requirement
            # every other test file's cleanup already follows.
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def tenant():
    _cleanup()
    db = SessionLocal()
    try:
        yield tenant_service.create(db, TenantCreate(name=TENANT_NAME))
    finally:
        db.close()
        _cleanup()


class TestVerifySvixSignature:
    def test_valid_signature_is_accepted(self):
        body = b'{"type":"email.sent"}'
        svix_id = "msg_test1"
        timestamp = str(int(time.time()))
        signature = _sign(body=body, svix_id=svix_id, timestamp=timestamp)

        result = verify_svix_signature(
            body=body, svix_id=svix_id, svix_timestamp=timestamp, svix_signature=signature,
            secret=TEST_SECRET,
        )
        assert result.svix_id == svix_id
        assert result.body == body

    def test_wrong_signature_is_rejected(self):
        body = b'{"type":"email.sent"}'
        with pytest.raises(WebhookSignatureError):
            verify_svix_signature(
                body=body, svix_id="msg_test1", svix_timestamp=str(int(time.time())),
                svix_signature="v1,not-the-real-signature", secret=TEST_SECRET,
            )

    def test_tampered_body_is_rejected(self):
        svix_id, timestamp = "msg_test1", str(int(time.time()))
        signature = _sign(body=b'{"type":"email.sent"}', svix_id=svix_id, timestamp=timestamp)
        with pytest.raises(WebhookSignatureError):
            verify_svix_signature(
                body=b'{"type":"email.bounced"}', svix_id=svix_id, svix_timestamp=timestamp,
                svix_signature=signature, secret=TEST_SECRET,
            )

    def test_missing_headers_are_rejected(self):
        with pytest.raises(WebhookSignatureError):
            verify_svix_signature(
                body=b"{}", svix_id=None, svix_timestamp=None, svix_signature=None, secret=TEST_SECRET
            )

    def test_stale_timestamp_is_rejected(self):
        body = b'{"type":"email.sent"}'
        svix_id = "msg_test1"
        old_timestamp = str(int(time.time()) - 3600)  # one hour old
        signature = _sign(body=body, svix_id=svix_id, timestamp=old_timestamp)
        with pytest.raises(WebhookSignatureError):
            verify_svix_signature(
                body=body, svix_id=svix_id, svix_timestamp=old_timestamp, svix_signature=signature,
                secret=TEST_SECRET,
            )

    def test_one_of_multiple_space_separated_signatures_can_match(self):
        body = b'{"type":"email.sent"}'
        svix_id, timestamp = "msg_test1", str(int(time.time()))
        real = _sign(body=body, svix_id=svix_id, timestamp=timestamp)
        combined = f"v1,bogus {real}"
        result = verify_svix_signature(
            body=body, svix_id=svix_id, svix_timestamp=timestamp, svix_signature=combined,
            secret=TEST_SECRET,
        )
        assert result.svix_id == svix_id


class TestWebhookRoute:
    def _post_event(self, client, monkeypatch, event: dict, *, svix_id: str | None = None):
        monkeypatch.setattr(settings, "resend_webhook_secret", TEST_SECRET)
        body = json.dumps(event).encode()
        svix_id = svix_id or f"msg_{uuid.uuid4().hex}"
        timestamp = str(int(time.time()))
        signature = _sign(body=body, svix_id=svix_id, timestamp=timestamp)
        return client.post(
            "/api/v1/communications/webhook",
            content=body,
            headers={
                "svix-id": svix_id,
                "svix-timestamp": timestamp,
                "svix-signature": signature,
                "content-type": "application/json",
            },
        )

    def test_returns_503_when_webhook_secret_not_configured(self, client, monkeypatch):
        monkeypatch.setattr(settings, "resend_webhook_secret", None)
        r = client.post("/api/v1/communications/webhook", content=b"{}")
        assert r.status_code == 503

    def test_invalid_signature_returns_400(self, client, monkeypatch):
        monkeypatch.setattr(settings, "resend_webhook_secret", TEST_SECRET)
        r = client.post(
            "/api/v1/communications/webhook",
            content=b'{"type":"email.sent"}',
            headers={
                "svix-id": "msg_bad",
                "svix-timestamp": str(int(time.time())),
                "svix-signature": "v1,wrong",
            },
        )
        assert r.status_code == 400

    def test_delivered_event_marks_the_communication_delivered(self, client, monkeypatch, tenant):
        db = SessionLocal()
        try:
            row = crud.create_communication(
                db, id=uuid.uuid4(), tenant_id=tenant.id, message_type="quote_sent",
                recipient="customer@example.invalid", sender_identity="x", subject="x",
                body_html="x", body_text="x", dedupe_key=f"test:{uuid.uuid4()}", status="sent",
            )
            crud.update_communication_result(db, row.id, status="sent", provider="resend",
                                              provider_message_id="resend_evt_1")
        finally:
            db.close()

        r = self._post_event(
            client, monkeypatch,
            {"type": "email.delivered", "data": {"email_id": "resend_evt_1"}},
        )
        assert r.status_code == 200

        db = SessionLocal()
        try:
            updated = db.get(Communication, row.id)
            assert updated.status == "delivered"
        finally:
            db.close()

    def test_bounced_event_marks_bounced_and_suppresses(self, client, monkeypatch, tenant):
        db = SessionLocal()
        try:
            row = crud.create_communication(
                db, id=uuid.uuid4(), tenant_id=tenant.id, message_type="quote_sent",
                recipient="bounced@example.invalid", sender_identity="x", subject="x",
                body_html="x", body_text="x", dedupe_key=f"test:{uuid.uuid4()}", status="sent",
            )
            crud.update_communication_result(db, row.id, status="sent", provider="resend",
                                              provider_message_id="resend_evt_2")
        finally:
            db.close()

        r = self._post_event(
            client, monkeypatch,
            {"type": "email.bounced", "data": {"email_id": "resend_evt_2"}},
        )
        assert r.status_code == 200

        db = SessionLocal()
        try:
            updated = db.get(Communication, row.id)
            assert updated.status == "bounced"
            suppression = crud.get_email_suppression(db, tenant.id, "bounced@example.invalid")
            assert suppression is not None
            assert suppression.reason == "hard_bounce"
        finally:
            db.close()

    def test_complained_event_suppresses_without_changing_status(self, client, monkeypatch, tenant):
        db = SessionLocal()
        try:
            row = crud.create_communication(
                db, id=uuid.uuid4(), tenant_id=tenant.id, message_type="quote_sent",
                recipient="complainer@example.invalid", sender_identity="x", subject="x",
                body_html="x", body_text="x", dedupe_key=f"test:{uuid.uuid4()}", status="sent",
            )
            crud.update_communication_result(db, row.id, status="delivered", provider="resend",
                                              provider_message_id="resend_evt_3")
        finally:
            db.close()

        r = self._post_event(
            client, monkeypatch,
            {"type": "email.complained", "data": {"email_id": "resend_evt_3"}},
        )
        assert r.status_code == 200

        db = SessionLocal()
        try:
            updated = db.get(Communication, row.id)
            assert updated.status == "delivered"  # unchanged
            suppression = crud.get_email_suppression(db, tenant.id, "complainer@example.invalid")
            assert suppression is not None
            assert suppression.reason == "complaint"
        finally:
            db.close()

    def test_unknown_event_type_is_acknowledged_without_error(self, client, monkeypatch, tenant):
        r = self._post_event(client, monkeypatch, {"type": "email.opened", "data": {"email_id": "x"}})
        assert r.status_code == 200

    def test_duplicate_delivery_is_processed_only_once(self, client, monkeypatch, tenant):
        from unittest.mock import MagicMock

        import app.communications.router as router_module

        fake_delivery = MagicMock()
        fake_delivery.record_webhook_event.return_value = "marked delivered"
        monkeypatch.setattr(router_module, "delivery_service", fake_delivery)

        svix_id = f"msg_{uuid.uuid4().hex}"
        event = {"type": "email.delivered", "data": {"email_id": "resend_evt_dup"}}

        first = self._post_event(client, monkeypatch, event, svix_id=svix_id)
        second = self._post_event(client, monkeypatch, event, svix_id=svix_id)

        assert first.status_code == 200
        assert second.status_code == 200
        fake_delivery.record_webhook_event.assert_called_once()
