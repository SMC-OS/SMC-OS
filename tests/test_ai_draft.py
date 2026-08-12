"""AI Quotation Generator v1 tests — fully mocked, zero real OpenAI calls
or API key required. ai_draft_service._client is injected directly with a
MagicMock per test, bypassing the lazy real-client construction entirely.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog
from app.quotes.ai_draft import _AIExtraction, ai_draft_service

TEST_TEXT = "3.5m kitchen in calacatta gold with an island, customer is Pytest AI Customer"


def _fake_completion(extraction, refusal=None):
    message = MagicMock()
    message.parsed = extraction
    message.refusal = refusal
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.fixture(autouse=True)
def _reset_ai_client():
    """Every test starts and ends with no client injected, so the 'no key
    configured' test is never accidentally affected by a previous test's
    mock, regardless of execution order."""
    ai_draft_service._client = None
    yield
    ai_draft_service._client = None


def _cleanup_activity():
    db = SessionLocal()
    try:
        db.execute(delete(ActivityLog).where(ActivityLog.description == TEST_TEXT))
        db.commit()
    finally:
        db.close()


def test_ai_draft_requires_auth(client):
    r = client.post("/api/v1/quotes/ai-draft", json={"text": TEST_TEXT})
    assert r.status_code == 401


def test_ai_draft_empty_text_returns_422(client, auth_headers):
    r = client.post("/api/v1/quotes/ai-draft", json={"text": ""}, headers=auth_headers)
    assert r.status_code == 422


def test_ai_draft_no_key_configured_returns_503(client, auth_headers):
    # ai_draft_service._client is None (reset by the fixture above) and no
    # real OPENAI_API_KEY is configured in this test environment — the
    # exact "ships dark until you add a key" scenario this design targets.
    r = client.post(
        "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
    )
    assert r.status_code == 503


def test_ai_draft_successful_extraction(client, auth_headers):
    extraction = _AIExtraction(
        customer="Pytest AI Customer",
        material="Calacatta Gold",
        thickness="20mm",
        kitchen_length=3.5,
        island=True,
    )
    mock_client = MagicMock()
    mock_client.chat.completions.parse.return_value = _fake_completion(extraction)
    ai_draft_service._client = mock_client

    _cleanup_activity()
    try:
        r = client.post(
            "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert body["customer"] == "Pytest AI Customer"
        assert body["material"] == "Calacatta Gold"
        assert body["thickness"] == "20mm"
        assert body["kitchen_length"] == 3.5
        assert body["island"] is True
        assert body["warnings"] == []

        activity = client.get("/api/v1/activity?limit=50").json()
        descriptions = [e["description"] for e in activity]
        assert TEST_TEXT in descriptions
    finally:
        _cleanup_activity()


def test_ai_draft_unrecognised_material_is_flagged(client, auth_headers):
    extraction = _AIExtraction(
        customer="Pytest AI Customer",
        material="Unobtainium Deluxe",
        thickness="20mm",
        kitchen_length=3.5,
    )
    mock_client = MagicMock()
    mock_client.chat.completions.parse.return_value = _fake_completion(extraction)
    ai_draft_service._client = mock_client

    _cleanup_activity()
    try:
        r = client.post(
            "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert body["material"] is None
        assert body["material_raw"] == "Unobtainium Deluxe"
        assert any("Unobtainium Deluxe" in w for w in body["warnings"])
    finally:
        _cleanup_activity()


def test_ai_draft_missing_fields_produce_warnings(client, auth_headers):
    extraction = _AIExtraction(customer=None, material=None, thickness=None, kitchen_length=None)
    mock_client = MagicMock()
    mock_client.chat.completions.parse.return_value = _fake_completion(extraction)
    ai_draft_service._client = mock_client

    _cleanup_activity()
    try:
        r = client.post(
            "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
        )
        assert r.status_code == 200
        body = r.json()
        # customer, material, thickness, kitchen_length all missing -> 4 warnings
        assert len(body["warnings"]) == 4
    finally:
        _cleanup_activity()


def test_ai_draft_client_exception_returns_502(client, auth_headers):
    mock_client = MagicMock()
    mock_client.chat.completions.parse.side_effect = RuntimeError("simulated network failure")
    ai_draft_service._client = mock_client

    r = client.post(
        "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
    )
    assert r.status_code == 502


def test_ai_draft_refusal_returns_502(client, auth_headers):
    mock_client = MagicMock()
    mock_client.chat.completions.parse.return_value = _fake_completion(None, refusal="policy")
    ai_draft_service._client = mock_client

    r = client.post(
        "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
    )
    assert r.status_code == 502
