"""Communications Centre — Sprint 039, Workstream A.

Sprint 038 built a complete, production-verified communications ledger and
one authenticated read endpoint. Nothing in the product ever showed it. This
covers what Sprint 039 adds so a user can actually see and act on it:

  * a central, tenant-scoped listing with paging;
  * the derived `complained` flag (§4 Decision 1 — a complaint is proof of
    *delivery*, so it is never written over the row's status);
  * a user-initiated retry that reuses `DeliveryService.retry()` and so
    can never send twice or resurrect a delivered message;
  * the tenant boundary on every one of them.

Every send goes through a fake `EmailProvider`. No real network call is
made by this file, and nothing here claims a provider did anything.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.communications.models import CommunicationType
from app.communications.provider import (
    EmailMessage,
    EmailProvider,
    SendOutcome,
    SendResult,
)
from app.communications.service import DeliveryService
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailSuppression,
    NotificationRecord,
    Tenant,
    User,
)

RUN_ID = uuid.uuid4().hex[:8]
TENANT_NAME = f"Pytest Comms Centre {RUN_ID}"
OWNER_EMAIL = f"pytest-comms-centre-{RUN_ID}@example.invalid"
OWNER_PASSWORD = "pytest-comms-centre-password-1"


def _cleanup():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            # Sprint 039 — a failed send now notifies the workspace
            # (app/notifications/delivery_alerts.py), so these tests
            # produce notification rows they did not before. Deleted
            # before their recipient, children-before-parents, same
            # convention as tests/conftest.py's own teardown.
            db.execute(
                delete(NotificationRecord).where(NotificationRecord.tenant_id == tenant.id)
            )
            db.execute(delete(EmailSuppression).where(EmailSuppression.tenant_id == tenant.id))
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(User).where(User.tenant_id == tenant.id))
            db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


class _AcceptingProvider(EmailProvider):
    """Accepts every send and hands back a provider message id, exactly as
    a healthy provider would. Never touches the network."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> SendResult:
        self.sent.append(message)
        return SendResult(
            outcome=SendOutcome.ACCEPTED,
            provider_message_id=f"pytest-{uuid.uuid4().hex[:12]}",
        )


class _TransientlyFailingProvider(EmailProvider):
    """Fails transiently until `succeed_from` attempts have been made —
    the exact shape a retry is supposed to recover from."""

    def __init__(self, succeed_from: int = 2) -> None:
        self.attempts = 0
        self.succeed_from = succeed_from

    def send(self, message: EmailMessage) -> SendResult:
        self.attempts += 1
        if self.attempts < self.succeed_from:
            return SendResult(
                outcome=SendOutcome.TRANSIENT_FAILURE,
                detail="The mail provider was briefly unreachable.",
            )
        return SendResult(
            outcome=SendOutcome.ACCEPTED,
            provider_message_id=f"pytest-{uuid.uuid4().hex[:12]}",
        )


@pytest.fixture()
def workspace(client):
    """A real signed-up workspace plus its bearer header."""
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": TENANT_NAME,
            "name": "Comms Centre Owner",
            "email": OWNER_EMAIL,
            "password": OWNER_PASSWORD,
        },
    )
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        tenant_id = tenant.id
    finally:
        db.close()
    return headers, tenant_id


def _send(db, tenant, *, provider=None, recipient="someone@example.invalid", dedupe=None):
    service = DeliveryService(provider=provider or _AcceptingProvider())
    return service.send(
        db,
        tenant=tenant,
        message_type=CommunicationType.PROJECT_UPDATE,
        recipient=recipient,
        subject="Your project",
        html="<p>Hello</p>",
        text="Hello",
        dedupe_key=dedupe or f"pytest-comms-{uuid.uuid4().hex}",
    )


# --- The central listing --------------------------------------------------


def test_the_centre_lists_this_tenant_s_communications_newest_first(client, workspace):
    headers, tenant_id = workspace
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        _send(db, tenant, recipient="first@example.invalid")
        _send(db, tenant, recipient="second@example.invalid")
    finally:
        db.close()

    r = client.get("/api/v1/communications", headers=headers)

    assert r.status_code == 200, r.text
    recipients = [row["recipient"] for row in r.json()]
    assert recipients[:2] == ["second@example.invalid", "first@example.invalid"]


def test_the_centre_never_shows_another_tenant_s_communications(
    client, workspace, other_tenant_auth_headers
):
    headers, tenant_id = workspace
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        _send(db, tenant, recipient="mine@example.invalid")
    finally:
        db.close()

    r = client.get("/api/v1/communications", headers=other_tenant_auth_headers)

    assert r.status_code == 200
    assert all(row["recipient"] != "mine@example.invalid" for row in r.json())


def test_the_centre_pages_through_history(client, workspace):
    headers, tenant_id = workspace
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        for index in range(3):
            _send(db, tenant, recipient=f"page{index}@example.invalid")
    finally:
        db.close()

    first = client.get("/api/v1/communications?limit=2", headers=headers).json()
    second = client.get("/api/v1/communications?limit=2&offset=2", headers=headers).json()

    assert len(first) == 2
    assert len(second) >= 1
    # No row appears on both pages.
    assert {row["id"] for row in first}.isdisjoint({row["id"] for row in second})


def test_the_listing_never_exposes_provider_internals_or_message_bodies(client, workspace):
    """Sprint 038's `CommunicationOut` contract, re-asserted here because
    Sprint 039 is the first sprint to put this data in front of a user and
    is therefore the first that could widen it by accident."""
    headers, tenant_id = workspace
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        _send(db, tenant)
    finally:
        db.close()

    row = client.get("/api/v1/communications", headers=headers).json()[0]

    for leaked in ("body_html", "body_text", "provider_message_id", "sender_identity", "provider"):
        assert leaked not in row, leaked


# --- "Complained", derived rather than stored (§4 Decision 1) -------------


def test_a_normal_communication_is_not_marked_as_complained(client, workspace):
    headers, tenant_id = workspace
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        _send(db, tenant)
    finally:
        db.close()

    row = client.get("/api/v1/communications", headers=headers).json()[0]

    assert row["complained"] is False


def test_a_complaint_is_surfaced_without_overwriting_the_delivered_status(
    client, workspace
):
    """The whole point of Decision 1: a complaint proves the message
    reached the inbox, so the status must keep saying so. Sprint 038's
    webhook handler is left untouched — the flag is derived from the
    suppression row it writes."""
    headers, tenant_id = workspace
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        communication = _send(db, tenant, recipient="complainer@example.invalid")
        crud.update_communication_result(
            db,
            communication.id,
            status="delivered",
            increment_attempt=False,
        )
        DeliveryService(provider=_AcceptingProvider()).suppress(
            db,
            tenant_id=tenant_id,
            email="complainer@example.invalid",
            reason="complaint",
            source_communication_id=communication.id,
        )
        communication_id = str(communication.id)
    finally:
        db.close()

    row = next(
        item
        for item in client.get("/api/v1/communications", headers=headers).json()
        if item["id"] == communication_id
    )

    assert row["complained"] is True
    assert row["status"] == "delivered"


def test_a_bounce_suppression_does_not_read_as_a_complaint(client, workspace):
    """Both write an EmailSuppression; only one of them is a complaint."""
    headers, tenant_id = workspace
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        communication = _send(db, tenant, recipient="bouncer@example.invalid")
        DeliveryService(provider=_AcceptingProvider()).suppress(
            db,
            tenant_id=tenant_id,
            email="bouncer@example.invalid",
            reason="hard_bounce",
            source_communication_id=communication.id,
        )
        communication_id = str(communication.id)
    finally:
        db.close()

    row = next(
        item
        for item in client.get("/api/v1/communications", headers=headers).json()
        if item["id"] == communication_id
    )

    assert row["complained"] is False


# --- User-initiated retry -------------------------------------------------


def test_a_user_retry_re_attempts_the_same_failed_message(client, workspace):
    """Over HTTP the retry runs through the application's own configured
    provider — which, in this environment, is none. So this asserts what
    is actually true and observable: the endpoint accepted the retry, it
    re-attempted the *same* row (attempt_count moved), and the outcome it
    reports is the honest one for a workspace with no email provider
    configured. It deliberately does not assert "sent": nothing here may
    imply a provider accepted a message when no provider was called.

    That a *successful* retry reaches "sent" is proven separately, at the
    service level, against an injected provider —
    test_a_recovering_provider_turns_a_retry_into_a_real_send below.
    """
    headers, tenant_id = workspace
    provider = _TransientlyFailingProvider(succeed_from=99)
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        communication = _send(db, tenant, provider=provider)
        assert communication.status == "failed"
        communication_id = str(communication.id)
        attempts_before = communication.attempt_count
    finally:
        db.close()

    r = client.post(f"/api/v1/communications/{communication_id}/retry", headers=headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == communication_id
    assert body["attempt_count"] == attempts_before + 1
    # No provider is configured in this environment, so the honest outcome
    # is a recorded failure with a user-appropriate reason — never a
    # fabricated success.
    assert body["status"] == "failed"
    assert body["failure_category"] == "unavailable"


def test_a_recovering_provider_turns_a_retry_into_a_real_send(workspace):
    """The service-level half of the pair above: given a provider that
    fails once and then accepts, retry() genuinely reaches "sent" — and
    still on the same row."""
    _, tenant_id = workspace
    provider = _TransientlyFailingProvider(succeed_from=2)
    service = DeliveryService(provider=provider)
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        communication = service.send(
            db,
            tenant=tenant,
            message_type=CommunicationType.PROJECT_UPDATE,
            recipient="recovering@example.invalid",
            subject="Your project",
            html="<p>Hello</p>",
            text="Hello",
            dedupe_key=f"pytest-comms-{uuid.uuid4().hex}",
        )
        assert communication.status == "failed"

        retried = service.retry(db, communication.id)

        assert retried.id == communication.id
        assert retried.status == "sent"
        assert provider.attempts == 2
    finally:
        db.close()


def test_retrying_never_creates_a_second_communication(client, workspace):
    """Retry updates the same row in place, so `dedupe_key`'s uniqueness is
    never at risk and a customer never receives two copies."""
    headers, tenant_id = workspace
    provider = _TransientlyFailingProvider(succeed_from=2)
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        communication = _send(db, tenant, provider=provider)
        communication_id = str(communication.id)
    finally:
        db.close()

    before = len(client.get("/api/v1/communications", headers=headers).json())
    client.post(f"/api/v1/communications/{communication_id}/retry", headers=headers)
    after = client.get("/api/v1/communications", headers=headers).json()

    assert len(after) == before
    assert sum(1 for row in after if row["id"] == communication_id) == 1


def test_retrying_a_delivered_message_never_re_sends_it(client, workspace):
    """The one thing a retry button must never do."""
    headers, tenant_id = workspace
    provider = _AcceptingProvider()
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        communication = _send(db, tenant, provider=provider)
        crud.update_communication_result(
            db, communication.id, status="delivered", increment_attempt=False
        )
        communication_id = str(communication.id)
        sends_before = len(provider.sent)
    finally:
        db.close()

    r = client.post(f"/api/v1/communications/{communication_id}/retry", headers=headers)

    assert r.status_code == 409
    assert len(provider.sent) == sends_before


def test_retrying_a_suppressed_send_is_refused(client, workspace):
    """Retrying past a suppression would defeat the list's whole purpose."""
    headers, tenant_id = workspace
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        service = DeliveryService(provider=_AcceptingProvider())
        service.suppress(
            db, tenant_id=tenant_id, email="blocked@example.invalid", reason="hard_bounce"
        )
        communication = _send(db, tenant, recipient="blocked@example.invalid")
        assert communication.status == "suppressed"
        communication_id = str(communication.id)
    finally:
        db.close()

    r = client.post(f"/api/v1/communications/{communication_id}/retry", headers=headers)

    assert r.status_code == 409


def test_one_tenant_can_never_retry_another_tenant_s_communication(
    client, workspace, other_tenant_auth_headers
):
    """The write-path tenant check: knowing an id must not be enough."""
    headers, tenant_id = workspace
    db = SessionLocal()
    try:
        tenant = crud.get_tenant_by_id(db, tenant_id)
        communication = _send(db, tenant, provider=_TransientlyFailingProvider(succeed_from=99))
        communication_id = str(communication.id)
    finally:
        db.close()

    r = client.post(
        f"/api/v1/communications/{communication_id}/retry",
        headers=other_tenant_auth_headers,
    )

    assert r.status_code == 404


def test_retrying_an_unknown_communication_returns_404(client, workspace):
    headers, _ = workspace

    r = client.post(f"/api/v1/communications/{uuid.uuid4()}/retry", headers=headers)

    assert r.status_code == 404


def test_the_centre_requires_authentication(client):
    assert client.get("/api/v1/communications").status_code in (401, 403)
