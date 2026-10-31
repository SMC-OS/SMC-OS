"""Delivery failures must not become verification success; no provider/network calls."""
from types import SimpleNamespace
from unittest.mock import Mock
import uuid
import pytest
from app.auth import router as routes
from app.auth.verification_service import email_verification_service

@pytest.mark.parametrize("outcome,expected", [("sent", "sent"), ("delivered", "sent"), ("failed", "failed"), ("suppressed", "suppressed"), ("queued", "pending")])
def test_resend_reports_delivery_outcome(monkeypatch, outcome, expected):
    user = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4(), email="audit@example.invalid", email_verified_at=None, name="Audit")
    create_token = Mock(return_value=SimpleNamespace(id=uuid.uuid4()))
    monkeypatch.setattr(routes.crud, "create_email_verification_token", create_token)
    monkeypatch.setattr(routes.crud, "get_tenant_by_id", lambda *a: SimpleNamespace(name="Audit"))
    monkeypatch.setattr(routes.activity_service, "log", Mock())
    monkeypatch.setattr(routes.email_verification_resend_limiter, "check_and_record", Mock())
    monkeypatch.setattr(email_verification_service._delivery, "send", lambda *a, **kw: SimpleNamespace(status=outcome))
    result = routes.resend_verification_email(current_user=user, db=Mock())
    assert result.delivery_status == expected
    assert create_token.call_count == 1
    if expected != "sent":
        assert "sent." not in result.message.lower()


def test_unexpected_exception_returns_failure_without_losing_token(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4(), email="audit@example.invalid", email_verified_at=None, name="Audit")
    token = Mock(return_value=SimpleNamespace(id=uuid.uuid4()))
    monkeypatch.setattr(routes.crud, "create_email_verification_token", token)
    monkeypatch.setattr(routes.crud, "get_tenant_by_id", lambda *a: SimpleNamespace(name="Audit"))
    monkeypatch.setattr(routes.activity_service, "log", Mock())
    monkeypatch.setattr(routes.email_verification_resend_limiter, "check_and_record", Mock())
    def broken_send(*a, **kw):
        raise RuntimeError("private provider detail")
    monkeypatch.setattr(email_verification_service._delivery, "send", broken_send)
    result = routes.resend_verification_email(current_user=user, db=Mock())
    assert result.delivery_status == "failed"
    assert "private provider detail" not in result.message
    assert token.call_count == 1
