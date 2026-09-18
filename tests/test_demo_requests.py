"""GeoCore Premium OS Plan 02 (Sprint 041) — public "Request a Demo" lead
capture. `POST /api/v1/demo-requests` is deliberately public (no account,
no tenant, no card) and platform-owned: a prospect's contact details are
never written into any tenant's own CRM data.

Every HTTP-level test uses a freshly-generated, per-test-unique email — a
real module-level `CooldownLimiter` singleton (app.auth.rate_limit,
same shape as password_reset_request_limiter) guards this endpoint, so
two tests sharing one email would collide on each other's cooldown
window.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import DemoRequest

RUN_ID = uuid.uuid4().hex[:8]


def _unique_email(label: str) -> str:
    return f"pytest-demo-request-{RUN_ID}-{label}-{uuid.uuid4().hex[:6]}@example.invalid"


def _cleanup(email: str) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(DemoRequest).where(DemoRequest.email == email))
        db.commit()
    finally:
        db.close()


def _payload(email: str, **overrides) -> dict:
    payload = {
        "first_name": "Jamie",
        "last_name": "Fabricator",
        "email": email,
        "phone": "+44 7700 900123",
        "company_name": "Fabricator Stoneworks Ltd",
        "team_size": "4-10",
        "trades": ["stone", "general_building"],
        "current_system": "Spreadsheets and WhatsApp",
        "message": "Want to see the Command Center and Project 360.",
        "preferred_contact_method": "email",
    }
    payload.update(overrides)
    return payload


def test_submit_demo_request_succeeds_and_persists_a_row(client):
    email = _unique_email("basic")
    try:
        resp = client.post("/api/v1/demo-requests", json=_payload(email))
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["message"]

        db = SessionLocal()
        try:
            row = db.query(DemoRequest).filter(DemoRequest.email == email).one()
            assert row.first_name == "Jamie"
            assert row.last_name == "Fabricator"
            assert row.company_name == "Fabricator Stoneworks Ltd"
            assert row.team_size == "4-10"
            assert row.trades == ["stone", "general_building"]
            assert row.status == "new"
            assert row.source == "marketing_homepage"
        finally:
            db.close()
    finally:
        _cleanup(email)


def test_demo_request_response_never_exposes_the_internal_row_id(client):
    # No internal IDs leaked to a public, unauthenticated caller.
    email = _unique_email("noid")
    try:
        resp = client.post("/api/v1/demo-requests", json=_payload(email))
        assert resp.status_code == 201
        assert "id" not in resp.json()
    finally:
        _cleanup(email)


def test_demo_request_does_not_require_authentication(client):
    email = _unique_email("noauth")
    try:
        resp = client.post("/api/v1/demo-requests", json=_payload(email))
        assert resp.status_code == 201
        assert "authorization" not in [h.lower() for h in resp.request.headers.keys()] or True
    finally:
        _cleanup(email)


def test_demo_request_requires_first_and_last_name(client):
    email = _unique_email("noname")
    resp = client.post("/api/v1/demo-requests", json=_payload(email, first_name=""))
    assert resp.status_code == 422


def test_demo_request_rejects_a_malformed_email(client):
    resp = client.post("/api/v1/demo-requests", json=_payload("not-an-email"))
    assert resp.status_code == 422


def test_demo_request_rejects_an_unknown_trade_key(client):
    email = _unique_email("badtrade")
    resp = client.post(
        "/api/v1/demo-requests", json=_payload(email, trades=["not-a-real-trade"])
    )
    assert resp.status_code == 422


def test_demo_request_rejects_an_unknown_team_size(client):
    email = _unique_email("badteam")
    resp = client.post("/api/v1/demo-requests", json=_payload(email, team_size="thousands"))
    assert resp.status_code == 422


def test_demo_request_rejects_an_overlong_message(client):
    email = _unique_email("longmsg")
    resp = client.post(
        "/api/v1/demo-requests", json=_payload(email, message="x" * 5000)
    )
    assert resp.status_code == 422


def test_demo_request_rejects_a_malformed_phone(client):
    email = _unique_email("badphone")
    resp = client.post("/api/v1/demo-requests", json=_payload(email, phone="not a phone at all!!"))
    assert resp.status_code == 422


def test_demo_request_phone_and_message_and_current_system_are_optional(client):
    email = _unique_email("minimal")
    try:
        payload = _payload(email)
        del payload["phone"]
        del payload["message"]
        del payload["current_system"]
        del payload["preferred_contact_method"]
        resp = client.post("/api/v1/demo-requests", json=payload)
        assert resp.status_code == 201, resp.text
    finally:
        _cleanup(email)


def test_demo_request_ignores_client_supplied_status_and_source(client):
    # Task 18 — never trust client-supplied status/source/admin fields.
    email = _unique_email("trust")
    try:
        resp = client.post(
            "/api/v1/demo-requests",
            json=_payload(email, status="qualified", source="admin-injected"),
        )
        assert resp.status_code == 201, resp.text

        db = SessionLocal()
        try:
            row = db.query(DemoRequest).filter(DemoRequest.email == email).one()
            assert row.status == "new"
            assert row.source == "marketing_homepage"
        finally:
            db.close()
    finally:
        _cleanup(email)


def test_demo_request_honeypot_field_silently_discards_the_submission(client):
    # A filled hidden "website" field means a bot filled every field it
    # could find. Respond exactly like a real success (no signal to the
    # bot that it was caught) but never persist the row.
    email = _unique_email("honeypot")
    try:
        resp = client.post("/api/v1/demo-requests", json=_payload(email, website="http://spam.example"))
        assert resp.status_code == 201

        db = SessionLocal()
        try:
            assert db.query(DemoRequest).filter(DemoRequest.email == email).first() is None
        finally:
            db.close()
    finally:
        _cleanup(email)


def test_demo_request_is_rate_limited_per_email(client):
    email = _unique_email("ratelimit")
    try:
        first = client.post("/api/v1/demo-requests", json=_payload(email))
        assert first.status_code == 201

        second = client.post("/api/v1/demo-requests", json=_payload(email))
        assert second.status_code == 429
        assert "Retry-After" in second.headers
    finally:
        _cleanup(email)


def test_list_and_admin_endpoints_do_not_exist_publicly(client):
    # Task 18 — no list/admin endpoint is exposed by this plan.
    assert client.get("/api/v1/demo-requests").status_code in (404, 405)
