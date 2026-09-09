"""Sprint 038, Phase 3 — real quote delivery
(POST /quotes/{id}/send-email, app/quotes/service.py's
send_and_mark_sent), alongside the untouched manual mark_sent() from
Sprint 007 (POST /quotes/{id}/send).

Only the outbound EmailProvider is faked (swapped onto the real
delivery_service singleton) — DeliveryService's own send()/retry() logic,
and every database write it makes, run for real. This is deliberate: the
retry-not-resend behaviour under test here lives in the interaction
between quote_service.send_and_mark_sent's dedupe_key lookup and a real,
persisted Communication row, which a fully-mocked DeliveryService would
never exercise.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select

import app.communications.service as communications_service_module
from app.communications.provider import EmailMessage, EmailProvider, SendOutcome, SendResult
from app.database.database import SessionLocal
from app.database.models import Communication, Project, Quote, QuoteItem

RUN_ID = uuid.uuid4().hex[:8]
TEST_POSTCODE = f"PYD38{RUN_ID[:5]}".upper()


def _cleanup():
    db = SessionLocal()
    try:
        quote_ids = select(Quote.id).where(Quote.site_postcode == TEST_POSTCODE)
        db.execute(delete(Communication).where(Communication.quote_id.in_(quote_ids)))
        db.execute(delete(Project).where(Project.quote_id.in_(quote_ids)))
        db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
        db.execute(delete(Quote).where(Quote.site_postcode == TEST_POSTCODE))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


class _ScriptedProvider(EmailProvider):
    """Returns each queued result in order, then repeats the last one.
    `calls` records every message actually handed to the provider, so a
    test can assert exactly how many real send attempts happened."""

    def __init__(self):
        self.results: list[SendResult] = []
        self.calls: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> SendResult:
        self.calls.append(message)
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


@pytest.fixture()
def scripted_provider(monkeypatch):
    provider = _ScriptedProvider()
    monkeypatch.setattr(communications_service_module.delivery_service, "_provider", provider)
    return provider


def _customer(client, auth_headers, *, email: str | None = "customer@example.invalid"):
    payload = {"name": f"Pytest 038 quote delivery customer {RUN_ID}"}
    if email is not None:
        payload["email"] = email
    r = client.post("/api/v1/customers", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def _quote(client, auth_headers, **overrides):
    payload = {
        "title": f"Pytest 038 quote {RUN_ID}",
        "trade": "bathroom",
        "site_postcode": TEST_POSTCODE,
        "valid_until": (date.today() + timedelta(days=30)).isoformat(),
        "lines": [{"description": "Labour", "quantity": 1, "unit": "day", "unit_price": 500}],
    }
    payload.update(overrides)
    r = client.post("/api/v1/quotes", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


class TestSendQuoteEmail:
    def test_accepted_send_marks_the_quote_sent(self, client, auth_headers, scripted_provider):
        scripted_provider.results = [SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1")]
        customer = _customer(client, auth_headers)
        quote = _quote(client, auth_headers, customer_id=customer["id"])

        r = client.post(f"/api/v1/quotes/{quote['id']}/send-email", headers=auth_headers)

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["quote"]["status"] == "sent"
        assert body["communication"]["status"] == "sent"
        assert len(scripted_provider.calls) == 1
        assert scripted_provider.calls[0].recipient == customer["email"]

    def test_failed_send_does_not_mark_the_quote_sent(self, client, auth_headers, scripted_provider):
        scripted_provider.results = [
            SendResult(outcome=SendOutcome.TRANSIENT_FAILURE, detail="temporary provider error")
        ]
        customer = _customer(client, auth_headers)
        quote = _quote(client, auth_headers, customer_id=customer["id"])

        r = client.post(f"/api/v1/quotes/{quote['id']}/send-email", headers=auth_headers)

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["quote"]["status"] == "draft"
        assert body["quote"]["sent_at"] is None
        assert body["communication"]["status"] == "failed"
        assert body["communication"]["failure_category"] == "transient"

    def test_quote_with_no_linked_customer_returns_422(self, client, auth_headers, scripted_provider):
        quote = _quote(client, auth_headers)

        r = client.post(f"/api/v1/quotes/{quote['id']}/send-email", headers=auth_headers)

        assert r.status_code == 422
        assert scripted_provider.calls == []

    def test_customer_with_no_email_returns_422(self, client, auth_headers, scripted_provider):
        customer = _customer(client, auth_headers, email=None)
        quote = _quote(client, auth_headers, customer_id=customer["id"])

        r = client.post(f"/api/v1/quotes/{quote['id']}/send-email", headers=auth_headers)

        assert r.status_code == 422
        assert scripted_provider.calls == []

    def test_clicking_again_after_a_transient_failure_retries_rather_than_resends(
        self, client, auth_headers, scripted_provider
    ):
        scripted_provider.results = [
            SendResult(outcome=SendOutcome.TRANSIENT_FAILURE, detail="temporary provider error")
        ]
        customer = _customer(client, auth_headers)
        quote = _quote(client, auth_headers, customer_id=customer["id"])

        first = client.post(f"/api/v1/quotes/{quote['id']}/send-email", headers=auth_headers)
        assert first.json()["quote"]["status"] == "draft"
        assert len(scripted_provider.calls) == 1

        # The provider now accepts — simulating the underlying transient
        # condition having cleared between the two clicks.
        scripted_provider.results = [SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_2")]
        second = client.post(f"/api/v1/quotes/{quote['id']}/send-email", headers=auth_headers)

        assert second.json()["quote"]["status"] == "sent"
        # A real second provider call happened (the retry), but against
        # the *same* communications row/dedupe_key — never a second,
        # independent one.
        assert len(scripted_provider.calls) == 2

        db = SessionLocal()
        try:
            rows = db.query(Communication).filter(Communication.quote_id == uuid.UUID(quote["id"])).all()
            assert len(rows) == 1
            assert rows[0].attempt_count == 2
        finally:
            db.close()

    def test_third_click_after_success_does_not_send_again(self, client, auth_headers, scripted_provider):
        scripted_provider.results = [SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1")]
        customer = _customer(client, auth_headers)
        quote = _quote(client, auth_headers, customer_id=customer["id"])

        client.post(f"/api/v1/quotes/{quote['id']}/send-email", headers=auth_headers)
        assert len(scripted_provider.calls) == 1

        again = client.post(f"/api/v1/quotes/{quote['id']}/send-email", headers=auth_headers)
        assert again.json()["quote"]["status"] == "sent"
        assert len(scripted_provider.calls) == 1  # no new attempt — already sent

    def test_approved_quote_cannot_be_sent(self, client, auth_headers, scripted_provider):
        scripted_provider.results = [SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id="msg_1")]
        customer = _customer(client, auth_headers)
        quote = _quote(client, auth_headers, customer_id=customer["id"])
        client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

        r = client.post(f"/api/v1/quotes/{quote['id']}/send-email", headers=auth_headers)

        assert r.status_code == 409

    def test_manual_send_endpoint_is_unaffected_and_still_transmits_nothing(
        self, client, auth_headers, scripted_provider
    ):
        """The Sprint 007 fallback (POST /send) must keep working exactly
        as it always has, whether or not real delivery is configured —
        the sprint's own contract (docs/SPRINTS/sprint-038.md §3)."""
        quote = _quote(client, auth_headers)

        r = client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)

        assert r.status_code == 200
        assert r.json()["status"] == "sent"
        assert scripted_provider.calls == []
