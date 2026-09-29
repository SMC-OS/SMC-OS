import pytest
from fastapi import HTTPException

from app.compliance.internal_auth import require_internal_compliance_auth
from app.core.config import settings


def test_internal_compliance_auth_fails_closed_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "internal_compliance_token", None)
    with pytest.raises(HTTPException) as error:
        require_internal_compliance_auth(None)
    assert error.value.status_code == 403


def test_internal_compliance_auth_rejects_invalid_credential(monkeypatch):
    monkeypatch.setattr(settings, "internal_compliance_token", "a" * 32)
    with pytest.raises(HTTPException) as error:
        require_internal_compliance_auth("b" * 32)
    assert error.value.status_code == 403


def test_internal_compliance_auth_accepts_matching_credential(monkeypatch):
    secret = "a" * 32
    monkeypatch.setattr(settings, "internal_compliance_token", secret)
    assert require_internal_compliance_auth(secret) is None
