"""Sprint 038 — app/communications/ (docs/SPRINTS/sprint-038.md §2-6).

Every send here goes through a fake EmailProvider (never real HTTP) except
the ResendEmailProvider-specific tests, which fake the httpx client
directly — the same "swap the module-level client" pattern
tests/test_billing.py already uses for Stripe. No real network call is
ever made by this file.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.communications.models import CommunicationType
from app.communications.provider import (
    EmailMessage,
    EmailProvider,
    EmailProviderUnavailable,
    ResendEmailProvider,
    SendOutcome,
    SendResult,
    resolve_sender_identity,
)
from app.communications.service import DeliveryService
from app.communications.templates import render_invitation
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Communication, EmailSuppression, Subscription, Tenant
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

TENANT_NAME = "Pytest Communications Tenant"
OTHER_TENANT_NAME = "Pytest Communications Other Tenant"


def _cleanup():
    db = SessionLocal()
    try:
        for name in (TENANT_NAME, OTHER_TENANT_NAME):
            tenant = db.query(Tenant).filter(Tenant.name == name).first()
            if tenant is not None:
                db.execute(delete(EmailSuppression).where(EmailSuppression.tenant_id == tenant.id))
                db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
                db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
                db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
                db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def db():
    _cleanup()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        _cleanup()


@pytest.fixture()
def tenant(db):
    return tenant_service.create(db, TenantCreate(name=TENANT_NAME))


class FakeProvider(EmailProvider):
    """A hand-rolled EmailProvider double — records every call it receives
    and returns a pre-programmed result, so a test can assert both the
    outcome AND that the provider was (or was not) actually invoked."""

    def __init__(self, result: SendResult | Exception):
        self.result = result
        self.calls: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> SendResult:
        self.calls.append(message)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _send(db, tenant, delivery: DeliveryService, *, dedupe_key: str, recipient: str = "customer@example.invalid"):
    return delivery.send(
        db,
        tenant=tenant,
        message_type=CommunicationType.QUOTE_SENT,
        recipient=recipient,
        subject="Your quote",
        html="<p>hello</p>",
        text="hello",
        dedupe_key=dedupe_key,
    )


class TestDeliveryServiceSend:
    def test_accepted_marks_sent_with_provider_message_id(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_123"))
        delivery = DeliveryService(provider=provider)

        row = _send(db, tenant, delivery, dedupe_key="test:accepted")

        assert row.status == "sent"
        assert row.provider_message_id == "msg_123"
        assert row.attempt_count == 1
        assert row.failure_category is None
        assert len(provider.calls) == 1

    def test_transient_failure_marks_failed_transient(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.TRANSIENT_FAILURE, detail="temporary"))
        delivery = DeliveryService(provider=provider)

        row = _send(db, tenant, delivery, dedupe_key="test:transient")

        assert row.status == "failed"
        assert row.failure_category == "transient"
        assert row.failure_detail == "temporary"

    def test_permanent_failure_marks_failed_permanent(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.PERMANENT_FAILURE, detail="rejected"))
        delivery = DeliveryService(provider=provider)

        row = _send(db, tenant, delivery, dedupe_key="test:permanent")

        assert row.status == "failed"
        assert row.failure_category == "permanent"

    def test_unavailable_provider_marks_failed_unavailable_not_transient(self, db, tenant):
        provider = FakeProvider(EmailProviderUnavailable("no key configured"))
        delivery = DeliveryService(provider=provider)

        row = _send(db, tenant, delivery, dedupe_key="test:unavailable")

        assert row.status == "failed"
        assert row.failure_category == "unavailable"
        # The provider's own send() raised before doing anything — still
        # recorded as one call attempted, since FakeProvider.send() is what
        # raises (mirrors ResendEmailProvider._get_client() raising from
        # inside send()).
        assert len(provider.calls) == 1

    def test_dedupe_key_returns_existing_row_without_calling_provider_again(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1"))
        delivery = DeliveryService(provider=provider)

        first = _send(db, tenant, delivery, dedupe_key="test:dedupe")
        second = _send(db, tenant, delivery, dedupe_key="test:dedupe")

        assert first.id == second.id
        assert len(provider.calls) == 1, "a retried send with the same dedupe_key must not call the provider twice"

    def test_dedupe_key_is_scoped_per_tenant(self, db, tenant):
        other_tenant = tenant_service.create(db, TenantCreate(name=OTHER_TENANT_NAME))
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1"))
        delivery = DeliveryService(provider=provider)

        first = _send(db, tenant, delivery, dedupe_key="test:shared-key")
        second = _send(db, other_tenant, delivery, dedupe_key="test:shared-key")

        assert first.id != second.id
        assert len(provider.calls) == 2, "the same dedupe_key in a different tenant must still send"

    def test_suppressed_recipient_is_never_sent_to(self, db, tenant):
        crud.create_email_suppression(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="blocked@example.invalid",
            reason="hard_bounce",
        )
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1"))
        delivery = DeliveryService(provider=provider)

        row = _send(db, tenant, delivery, dedupe_key="test:suppressed", recipient="blocked@example.invalid")

        assert row.status == "suppressed"
        assert row.failure_category == "suppressed"
        assert len(provider.calls) == 0, "a suppressed recipient must never reach the provider"

    def test_recipient_is_normalized_for_suppression_matching(self, db, tenant):
        crud.create_email_suppression(
            db, id=uuid.uuid4(), tenant_id=tenant.id, email="blocked@example.invalid", reason="manual"
        )
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1"))
        delivery = DeliveryService(provider=provider)

        row = _send(
            db, tenant, delivery, dedupe_key="test:suppressed-case", recipient="  Blocked@Example.Invalid  "
        )

        assert row.status == "suppressed"


class TestCommunicationHistoryTenantIsolation:
    def test_list_history_never_returns_another_tenants_rows(self, db, tenant):
        other_tenant = tenant_service.create(db, TenantCreate(name=OTHER_TENANT_NAME))
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1"))
        delivery = DeliveryService(provider=provider)

        _send(db, tenant, delivery, dedupe_key="test:isolation-a")
        _send(db, other_tenant, delivery, dedupe_key="test:isolation-b")

        tenant_a_history = delivery.list_history(db, tenant.id)
        tenant_b_history = delivery.list_history(db, other_tenant.id)

        assert len(tenant_a_history) == 1
        assert len(tenant_b_history) == 1
        assert tenant_a_history[0].tenant_id == tenant.id
        assert tenant_b_history[0].tenant_id == other_tenant.id


class TestSenderIdentity:
    def test_uses_trading_name_when_set(self, db, tenant):
        tenant.trading_name = "The Trading Name"
        tenant.contact_email = "hello@business.example"
        db.commit()

        from_header, reply_to = resolve_sender_identity(tenant)

        assert "The Trading Name via GeoCore" in from_header
        assert f"@{settings.email_sending_domain}" in from_header
        assert reply_to == "hello@business.example"

    def test_falls_back_to_workspace_name_when_nothing_configured(self, db, tenant):
        from_header, reply_to = resolve_sender_identity(tenant)

        assert TENANT_NAME in from_header
        assert reply_to is None

    def test_never_sends_from_the_tenants_own_domain(self, db, tenant):
        tenant.contact_email = "owner@tenants-own-business.example"
        db.commit()

        from_header, _ = resolve_sender_identity(tenant)

        assert "tenants-own-business.example" not in from_header
        assert settings.email_sending_domain in from_header

    def test_handles_none_tenant_without_raising(self):
        from_header, reply_to = resolve_sender_identity(None)
        assert "GeoCore" in from_header
        assert reply_to is None


class TestTemplateEscaping:
    def test_invitation_template_escapes_hostile_inviter_name(self):
        rendered = render_invitation(
            tenant_display_name="Acme Ltd",
            inviter_name='<script>alert(1)</script>',
            accept_url="https://app.geocore.one/invite/abc123",
        )
        assert "<script>alert(1)</script>" not in rendered.html
        assert "&lt;script&gt;" in rendered.html
        # Plain text has no markup to break out of, so the raw text is
        # preserved there rather than double-escaped.
        assert "<script>alert(1)</script>" in rendered.text

    def test_invitation_template_escapes_hostile_tenant_name(self):
        rendered = render_invitation(
            tenant_display_name='Acme" onmouseover="alert(1)',
            inviter_name="Sam",
            accept_url="https://app.geocore.one/invite/abc123",
        )
        # html.escape() turns the payload's `"` into `&quot;` before it
        # reaches the markup — proves the escaping call actually ran,
        # rather than asserting the harder-to-state negative "no unescaped
        # quote anywhere" (the template's own static markup legitimately
        # contains plenty of quoted attributes).
        assert "&quot;" in rendered.html
        assert 'onmouseover="alert(1)' not in rendered.html
        assert "Acme" in rendered.subject

    def test_invitation_template_contains_the_accept_link(self):
        rendered = render_invitation(
            tenant_display_name="Acme Ltd",
            inviter_name="Sam",
            accept_url="https://app.geocore.one/invite/abc123",
        )
        assert "https://app.geocore.one/invite/abc123" in rendered.html
        assert "https://app.geocore.one/invite/abc123" in rendered.text


class _FakeHttpResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeHttpClient:
    def __init__(self, response: _FakeHttpResponse | Exception):
        self._response = response
        self.calls: list[dict] = []

    def post(self, path, *, json, headers):
        self.calls.append({"path": path, "json": json, "headers": headers})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class TestResendEmailProvider:
    def _message(self) -> EmailMessage:
        return EmailMessage(
            recipient="customer@example.invalid",
            sender_identity='"Acme via GeoCore" <noreply@send.geocore.one>',
            subject="Hi",
            html="<p>hi</p>",
            text="hi",
            idempotency_key="tenant:key",
        )

    def test_2xx_is_accepted(self):
        client = _FakeHttpClient(_FakeHttpResponse(200, {"id": "resend_msg_1"}))
        provider = ResendEmailProvider(http_client=client)

        result = provider.send(self._message())

        assert result.outcome == SendOutcome.ACCEPTED
        assert result.provider_message_id == "resend_msg_1"
        assert client.calls[0]["headers"]["Idempotency-Key"] == "tenant:key"

    def test_429_is_transient(self):
        client = _FakeHttpClient(_FakeHttpResponse(429))
        provider = ResendEmailProvider(http_client=client)

        result = provider.send(self._message())

        assert result.outcome == SendOutcome.TRANSIENT_FAILURE

    def test_5xx_is_transient(self):
        client = _FakeHttpClient(_FakeHttpResponse(503))
        provider = ResendEmailProvider(http_client=client)

        result = provider.send(self._message())

        assert result.outcome == SendOutcome.TRANSIENT_FAILURE

    def test_4xx_other_than_429_is_permanent(self):
        client = _FakeHttpClient(_FakeHttpResponse(422))
        provider = ResendEmailProvider(http_client=client)

        result = provider.send(self._message())

        assert result.outcome == SendOutcome.PERMANENT_FAILURE

    def test_network_error_is_transient(self):
        client = _FakeHttpClient(ConnectionError("boom"))
        provider = ResendEmailProvider(http_client=client)

        result = provider.send(self._message())

        assert result.outcome == SendOutcome.TRANSIENT_FAILURE

    def test_raises_unavailable_when_no_api_key_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "resend_api_key", None)
        provider = ResendEmailProvider()

        with pytest.raises(EmailProviderUnavailable):
            provider.send(self._message())


class TestRetry:
    def test_retry_succeeds_after_a_transient_failure_updates_the_same_row(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.TRANSIENT_FAILURE, detail="temporary"))
        delivery = DeliveryService(provider=provider)
        first = _send(db, tenant, delivery, dedupe_key="test:retry-succeeds")
        assert first.status == "failed"

        provider.result = SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_retry_1")
        retried = delivery.retry(db, first.id)

        assert retried.id == first.id
        assert retried.status == "sent"
        assert retried.provider_message_id == "msg_retry_1"
        assert retried.attempt_count == 2
        assert len(provider.calls) == 2

    def test_retry_on_a_permanent_failure_is_a_no_op(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.PERMANENT_FAILURE, detail="rejected"))
        delivery = DeliveryService(provider=provider)
        first = _send(db, tenant, delivery, dedupe_key="test:retry-permanent")
        assert first.failure_category == "permanent"

        retried = delivery.retry(db, first.id)

        assert retried.status == "failed"
        assert retried.failure_category == "permanent"
        assert len(provider.calls) == 1  # no second provider call

    def test_retry_on_a_suppressed_send_is_a_no_op(self, db, tenant):
        crud.create_email_suppression(
            db, id=uuid.uuid4(), tenant_id=tenant.id, email="blocked@example.invalid", reason="manual"
        )
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1"))
        delivery = DeliveryService(provider=provider)
        first = _send(db, tenant, delivery, dedupe_key="test:retry-suppressed", recipient="blocked@example.invalid")
        assert first.status == "suppressed"

        retried = delivery.retry(db, first.id)

        assert retried.status == "suppressed"
        assert len(provider.calls) == 0

    def test_retry_stops_after_max_attempts(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.TRANSIENT_FAILURE, detail="temporary"))
        delivery = DeliveryService(provider=provider)
        row = _send(db, tenant, delivery, dedupe_key="test:retry-bounded")

        for _ in range(delivery.MAX_ATTEMPTS + 2):
            row = delivery.retry(db, row.id)

        assert row.attempt_count == delivery.MAX_ATTEMPTS
        assert row.status == "failed"

    def test_retry_of_unknown_id_returns_none(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED))
        delivery = DeliveryService(provider=provider)
        assert delivery.retry(db, uuid.uuid4()) is None

    def test_retry_of_an_already_sent_row_is_a_no_op(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1"))
        delivery = DeliveryService(provider=provider)
        row = _send(db, tenant, delivery, dedupe_key="test:retry-already-sent")
        assert row.status == "sent"

        retried = delivery.retry(db, row.id)

        assert retried.status == "sent"
        assert len(provider.calls) == 1  # unchanged


class TestRetryPending:
    def test_retry_pending_only_touches_transient_and_unavailable_failures(self, db, tenant):
        transient_provider = FakeProvider(SendResult(outcome=SendOutcome.TRANSIENT_FAILURE, detail="x"))
        delivery = DeliveryService(provider=transient_provider)
        transient_row = _send(db, tenant, delivery, dedupe_key="test:pending-transient")

        permanent_provider = FakeProvider(SendResult(outcome=SendOutcome.PERMANENT_FAILURE, detail="x"))
        delivery_permanent = DeliveryService(provider=permanent_provider)
        permanent_row = _send(db, tenant, delivery_permanent, dedupe_key="test:pending-permanent")

        succeeding_provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="m"))
        sweep_delivery = DeliveryService(provider=succeeding_provider)
        result = sweep_delivery.retry_pending(db)

        # Sprint 039 Production Readiness Defect Gate, Blockers 1 and 2 —
        # retry_pending() sweeps *every* tenant by design (its own
        # docstring), so ">=" rather than "==": a real signup or
        # password-reset request elsewhere in the same run (any test, or
        # an E2E spec against this same dev database) now also leaves an
        # "unavailable"-failed Communication row behind for its own send
        # attempt (Resend is unconfigured in dev/test), which is just as
        # retryable and just as real as this test's own two rows. The
        # specific-row assertions below are what actually verifies this
        # test's own behavior. (Fixed independently and identically on
        # both sibling branches for the same underlying reason.)
        assert result["retried"] >= 1
        assert result["succeeded"] >= 1

        db.refresh(transient_row)
        db.refresh(permanent_row)
        assert transient_row.status == "sent"
        assert permanent_row.status == "failed"  # untouched
        assert permanent_row.failure_category == "permanent"


class TestWebhookEventRecording:
    def test_delivered_event_with_no_matching_communication_is_a_safe_no_op(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED))
        delivery = DeliveryService(provider=provider)
        outcome = delivery.record_webhook_event(
            db, {"type": "email.delivered", "data": {"email_id": "nonexistent"}}
        )
        assert "no communication found" in outcome

    def test_event_with_no_email_id_is_a_safe_no_op(self, db, tenant):
        provider = FakeProvider(SendResult(outcome=SendOutcome.ACCEPTED))
        delivery = DeliveryService(provider=provider)
        outcome = delivery.record_webhook_event(db, {"type": "email.delivered", "data": {}})
        assert "no email_id" in outcome
