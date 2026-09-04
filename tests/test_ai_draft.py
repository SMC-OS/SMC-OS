"""AI Quotation Generator tests — fully mocked, zero real OpenAI calls or
API key required. ai_draft_service._client is injected directly with a
MagicMock per test, bypassing the lazy real-client construction entirely.

Sprint 033 (Workstream C): the LLM mock only ever supplies entities and
per-item text spans (never numbers) — every dimension and every material
resolution comes from real, deterministic code running against the real
seeded catalogue, so these tests exercise that code for real, not a mock.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog
from app.quotes.ai_draft import _AIExtraction, _AIItemExtraction, ai_draft_service

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


def _mock_draft(extraction):
    mock_client = MagicMock()
    mock_client.chat.completions.parse.return_value = _fake_completion(extraction)
    ai_draft_service._client = mock_client


@pytest.fixture(autouse=True)
def _reset_ai_client():
    """Every test starts and ends with no client injected, so the 'no key
    configured' test is never accidentally affected by a previous test's
    mock, regardless of execution order."""
    ai_draft_service._client = None
    yield
    ai_draft_service._client = None


def _cleanup_activity(text=TEST_TEXT):
    db = SessionLocal()
    try:
        db.execute(delete(ActivityLog).where(ActivityLog.description == text))
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
    r = client.post(
        "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
    )
    assert r.status_code == 503


def test_ai_draft_successful_single_item_extraction(client, auth_headers):
    extraction = _AIExtraction(
        customer="Pytest AI Customer",
        shared_material="Calacatta Gold",
        shared_thickness="20mm",
        items=[_AIItemExtraction(item_type="worktop", text_span="3.5m")],
    )
    _mock_draft(extraction)

    _cleanup_activity()
    try:
        r = client.post(
            "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert body["customer"] == "Pytest AI Customer"
        assert body["warnings"] == []
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["material"] == "Calacatta Gold"
        assert item["material_match_status"] == "found"
        assert item["thickness"] == "20mm"
        assert item["length_mm"] == 3500
        assert item["unit_input"] == "m"

        activity = client.get("/api/v1/activity?limit=50", headers=auth_headers).json()
        descriptions = [e["description"] for e in activity]
        assert TEST_TEXT in descriptions
    finally:
        _cleanup_activity()


def test_ai_draft_unrecognised_material_is_flagged(client, auth_headers):
    extraction = _AIExtraction(
        customer="Pytest AI Customer",
        items=[
            _AIItemExtraction(
                item_type="worktop", material="Unobtainium Deluxe", thickness="20mm", text_span="3.5m"
            )
        ],
    )
    _mock_draft(extraction)

    _cleanup_activity()
    try:
        r = client.post(
            "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
        )
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["material"] is None
        assert item["material_raw"] == "Unobtainium Deluxe"
        assert item["material_match_status"] == "not_found"
        assert any("Unobtainium Deluxe" in w for w in item["warnings"])
    finally:
        _cleanup_activity()


def test_ai_draft_ambiguous_material_returns_real_candidates_never_fabricated(
    client, auth_headers
):
    # No thickness stated -> "Calacatta Gold" ties across its own two
    # thickness rows in the real seeded catalogue -> multiple, not a guess.
    extraction = _AIExtraction(
        customer="Pytest AI Customer",
        items=[_AIItemExtraction(item_type="worktop", material="Calacatta Gold", text_span="3.5m")],
    )
    _mock_draft(extraction)

    _cleanup_activity()
    try:
        r = client.post(
            "/api/v1/quotes/ai-draft", json={"text": TEST_TEXT}, headers=auth_headers
        )
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["material"] is None
        assert item["material_match_status"] == "multiple"
        assert len(item["material_candidates"]) == 2
        assert any("pick one manually" in w for w in item["warnings"])
    finally:
        _cleanup_activity()


def test_ai_draft_missing_fields_produce_warnings(client, auth_headers):
    text = "Please could you help me with a quote"
    extraction = _AIExtraction(customer=None, items=[])
    _mock_draft(extraction)

    _cleanup_activity(text)
    try:
        r = client.post(
            "/api/v1/quotes/ai-draft", json={"text": text}, headers=auth_headers
        )
        assert r.status_code == 200
        body = r.json()
        # no customer, no items -> 2 quote-level warnings
        assert len(body["warnings"]) == 2
        assert body["items"] == []
    finally:
        _cleanup_activity(text)


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


# --- Multi-item generation (Sprint 033, Workstream C) -----------------------


def test_ai_draft_generates_three_independent_items_from_one_request(client, auth_headers):
    """The sprint's own worked example: a worktop, an island, and two
    splashbacks, one shared material/thickness for the whole quote."""
    text = (
        "Create a quote using Calacatta Oro 20mm for a 2400 x 600 worktop, "
        "a 2200 x 1000 island and two 1200 x 600 splashbacks."
    )
    extraction = _AIExtraction(
        customer=None,
        shared_material="Calacatta Oro",
        shared_thickness="20mm",
        items=[
            _AIItemExtraction(item_type="worktop", text_span="2400 x 600"),
            _AIItemExtraction(item_type="island", text_span="2200 x 1000"),
            _AIItemExtraction(item_type="splashback", text_span="two 1200 x 600"),
        ],
    )
    _mock_draft(extraction)

    _cleanup_activity(text)
    try:
        r = client.post("/api/v1/quotes/ai-draft", json={"text": text}, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 3

        worktop, island, splashback = body["items"]
        assert worktop["item_type"] == "worktop"
        assert worktop["material"] == "Calacatta Oro"
        assert worktop["material_match_status"] == "found"
        assert worktop["length_mm"] == 2400
        assert worktop["width_mm"] == 600

        assert island["item_type"] == "island"
        assert island["material"] == "Calacatta Oro"
        assert island["length_mm"] == 2200
        assert island["width_mm"] == 1000

        assert splashback["item_type"] == "splashback"
        assert splashback["material"] == "Calacatta Oro"
        assert splashback["quantity"] == 2
        assert splashback["length_mm"] == 1200
        assert splashback["width_mm"] == 600
    finally:
        _cleanup_activity(text)


def test_ai_draft_per_item_material_overrides_shared_material(client, auth_headers):
    text = "A 2400 x 600 worktop in Calacatta Oro 20mm and a 2200 x 1000 island in Nero Marquina 20mm"
    extraction = _AIExtraction(
        customer=None,
        items=[
            _AIItemExtraction(
                item_type="worktop", material="Calacatta Oro", thickness="20mm", text_span="2400 x 600"
            ),
            _AIItemExtraction(
                item_type="island", material="Nero Marquina", thickness="20mm", text_span="2200 x 1000"
            ),
        ],
    )
    _mock_draft(extraction)

    _cleanup_activity(text)
    try:
        r = client.post("/api/v1/quotes/ai-draft", json={"text": text}, headers=auth_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items[0]["material"] == "Calacatta Oro"
        assert items[1]["material"] == "Nero Marquina"
    finally:
        _cleanup_activity(text)


def test_ai_draft_missing_product_never_fabricated_end_to_end(client, auth_headers):
    text = "Create a quote for SuperGalaxy Diamond Quartz 2400 x 600"
    extraction = _AIExtraction(
        customer=None,
        items=[
            _AIItemExtraction(
                item_type="worktop", material="SuperGalaxy Diamond Quartz", text_span="2400 x 600"
            )
        ],
    )
    _mock_draft(extraction)

    _cleanup_activity(text)
    try:
        r = client.post("/api/v1/quotes/ai-draft", json={"text": text}, headers=auth_headers)
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["material"] is None
        assert item["material_match_status"] == "not_found"
        assert item["material_raw"] == "SuperGalaxy Diamond Quartz"
        # Dimensions are still parsed and shown even though the product
        # doesn't exist — never blocked, never silently dropped.
        assert item["length_mm"] == 2400
        assert item["width_mm"] == 600
    finally:
        _cleanup_activity(text)


def test_ai_draft_missing_dimension_flags_the_specific_item(client, auth_headers):
    text = "A worktop in Calacatta Oro 20mm, and a splashback 1200 x 600"
    extraction = _AIExtraction(
        customer=None,
        items=[
            _AIItemExtraction(item_type="worktop", material="Calacatta Oro", thickness="20mm", text_span=""),
            _AIItemExtraction(item_type="splashback", text_span="1200 x 600"),
        ],
    )
    _mock_draft(extraction)

    _cleanup_activity(text)
    try:
        r = client.post("/api/v1/quotes/ai-draft", json={"text": text}, headers=auth_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert any("length" in w.lower() for w in items[0]["warnings"])
        assert any("material" in w.lower() for w in items[1]["warnings"])
    finally:
        _cleanup_activity(text)
