"""Sprint 017 acceptance tests for approved client-portal messaging."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Message, NotificationRecord, PortalLink

TEST_CUSTOMER_NAME = "Pytest Messages Customer"
OTHER_CUSTOMER_NAME = "Pytest Messages Other Customer"


def _cleanup() -> None:
    with SessionLocal() as db:
        customers = list(db.scalars(select(Customer).where(Customer.name.in_([TEST_CUSTOMER_NAME, OTHER_CUSTOMER_NAME]))))
        customer_ids = [customer.id for customer in customers]
        tenant_ids = [customer.tenant_id for customer in customers]
        if customer_ids:
            db.execute(delete(Message).where(Message.customer_id.in_(customer_ids)))
            db.execute(delete(PortalLink).where(PortalLink.customer_id.in_(customer_ids)))
        if tenant_ids:
            db.execute(delete(NotificationRecord).where(NotificationRecord.tenant_id.in_(tenant_ids), NotificationRecord.title == "New message"))
        db.execute(delete(ActivityLog).where(ActivityLog.description.in_([TEST_CUSTOMER_NAME, OTHER_CUSTOMER_NAME])))
        db.execute(delete(Customer).where(Customer.name.in_([TEST_CUSTOMER_NAME, OTHER_CUSTOMER_NAME])))
        db.commit()


@pytest.fixture()
def created_customer(client, auth_headers):
    _cleanup()
    response = client.post("/api/v1/customers", json={"name": TEST_CUSTOMER_NAME}, headers=auth_headers)
    assert response.status_code == 201
    yield response.json()
    _cleanup()


@pytest.fixture()
def created_portal_link(client, auth_headers, created_customer):
    response = client.post("/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers)
    assert response.status_code == 201
    return response.json()


def _post_staff(client, auth_headers, customer_id: str, body: str):
    return client.post(f"/api/v1/messages?customer_id={customer_id}", json={"body": body}, headers=auth_headers)


def _tenant_id(customer_id: str):
    with SessionLocal() as db:
        return db.get(Customer, uuid.UUID(customer_id)).tenant_id


def test_staff_post_uses_required_customer_query_parameter(client, auth_headers, created_customer):
    missing = client.post("/api/v1/messages", json={"customer_id": created_customer["id"], "body": "hello"}, headers=auth_headers)
    assert missing.status_code == 422
    assert _post_staff(client, auth_headers, created_customer["id"], "hello").status_code == 201


def test_staff_message_exposes_authenticated_sender_user_id(client, auth_headers, created_customer):
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    response = _post_staff(client, auth_headers, created_customer["id"], "Staff update")
    assert response.status_code == 201
    assert response.json()["sender_type"] == "staff"
    assert response.json()["sender_user_id"] == me["id"]


@pytest.mark.parametrize("body", ["", "   ", "\n\t"])
def test_staff_rejects_empty_or_whitespace_only_body(client, auth_headers, created_customer, body):
    assert _post_staff(client, auth_headers, created_customer["id"], body).status_code == 422


def test_staff_accepts_5000_characters_and_rejects_5001(client, auth_headers, created_customer):
    assert _post_staff(client, auth_headers, created_customer["id"], "x" * 5000).status_code == 201
    assert _post_staff(client, auth_headers, created_customer["id"], "x" * 5001).status_code == 422


def test_staff_post_cross_tenant_customer_returns_404(client, other_tenant_auth_headers, created_customer):
    assert _post_staff(client, other_tenant_auth_headers, created_customer["id"], "not allowed").status_code == 404


def test_staff_list_requires_customer_id(client, auth_headers):
    assert client.get("/api/v1/messages", headers=auth_headers).status_code == 422


def test_staff_list_is_tenant_scoped(client, auth_headers, other_tenant_auth_headers, created_customer):
    _post_staff(client, auth_headers, created_customer["id"], "Tenant A only")
    response = client.get(f"/api/v1/messages?customer_id={created_customer['id']}", headers=other_tenant_auth_headers)
    assert response.status_code == 404


def test_messages_are_listed_oldest_to_newest(client, auth_headers, created_customer):
    _post_staff(client, auth_headers, created_customer["id"], "first")
    _post_staff(client, auth_headers, created_customer["id"], "second")
    response = client.get(f"/api/v1/messages?customer_id={created_customer['id']}", headers=auth_headers)
    assert [message["body"] for message in response.json()] == ["first", "second"]


def test_staff_message_creates_no_activity_or_notification(client, auth_headers, created_customer):
    tenant_id = _tenant_id(created_customer["id"])
    with SessionLocal() as db:
        activity_count_before = db.query(ActivityLog).filter_by(tenant_id=tenant_id).count()
        notification_count_before = db.query(NotificationRecord).filter_by(tenant_id=tenant_id).count()
    assert _post_staff(client, auth_headers, created_customer["id"], "No side effects").status_code == 201
    with SessionLocal() as db:
        assert db.query(ActivityLog).filter_by(tenant_id=tenant_id).count() == activity_count_before
        assert db.query(NotificationRecord).filter_by(tenant_id=tenant_id).count() == notification_count_before


def test_portal_lists_only_its_customer_thread(client, auth_headers, created_customer, created_portal_link):
    _post_staff(client, auth_headers, created_customer["id"], "visible")
    other = client.post("/api/v1/customers", json={"name": OTHER_CUSTOMER_NAME}, headers=auth_headers).json()
    _post_staff(client, auth_headers, other["id"], "hidden")
    response = client.get(f"/api/v1/portal-links/token/{created_portal_link['token']}/messages")
    assert response.status_code == 200
    assert [message["body"] for message in response.json()] == ["visible"]


def test_portal_message_has_null_sender_user_id_and_exact_side_effects(client, auth_headers, created_customer, created_portal_link):
    tenant_id = _tenant_id(created_customer["id"])
    with SessionLocal() as db:
        activity_count_before = db.query(ActivityLog).filter_by(tenant_id=tenant_id).count()
        notification_count_before = db.query(NotificationRecord).filter_by(tenant_id=tenant_id).count()
    response = client.post(f"/api/v1/portal-links/token/{created_portal_link['token']}/messages", json={"body": "Customer reply"})
    assert response.status_code == 201
    assert response.json()["sender_type"] == "customer"
    assert response.json()["sender_user_id"] is None
    with SessionLocal() as db:
        activities = list(db.scalars(select(ActivityLog).where(ActivityLog.tenant_id == tenant_id).order_by(ActivityLog.timestamp.desc())))
        notifications = list(db.scalars(select(NotificationRecord).where(NotificationRecord.tenant_id == tenant_id).order_by(NotificationRecord.timestamp.desc())))
    assert len(activities) == activity_count_before + 1
    assert activities[0].type == "customer_message_received"
    assert activities[0].title == "New message from a customer"
    assert activities[0].description == TEST_CUSTOMER_NAME
    assert len(notifications) == notification_count_before + 1
    assert notifications[0].title == "New message"
    assert notifications[0].type == "info"


@pytest.mark.parametrize("body", ["   ", "x" * 5001])
def test_invalid_portal_message_creates_no_rows_or_side_effects(client, created_customer, created_portal_link, body):
    tenant_id = _tenant_id(created_customer["id"])
    with SessionLocal() as db:
        before = (db.query(Message).filter_by(customer_id=uuid.UUID(created_customer["id"])).count(), db.query(ActivityLog).filter_by(tenant_id=tenant_id).count(), db.query(NotificationRecord).filter_by(tenant_id=tenant_id).count())
    response = client.post(f"/api/v1/portal-links/token/{created_portal_link['token']}/messages", json={"body": body})
    assert response.status_code == 422
    with SessionLocal() as db:
        after = (db.query(Message).filter_by(customer_id=uuid.UUID(created_customer["id"])).count(), db.query(ActivityLog).filter_by(tenant_id=tenant_id).count(), db.query(NotificationRecord).filter_by(tenant_id=tenant_id).count())
    assert after == before


@pytest.mark.parametrize("method", ["get", "post"])
def test_revoked_portal_token_cannot_list_or_post(client, auth_headers, created_portal_link, method):
    client.delete(f"/api/v1/portal-links/{created_portal_link['id']}", headers=auth_headers)
    url = f"/api/v1/portal-links/token/{created_portal_link['token']}/messages"
    response = client.get(url) if method == "get" else client.post(url, json={"body": "hi"})
    assert response.status_code == 404


@pytest.mark.parametrize("method", ["get", "post"])
def test_expired_portal_token_cannot_list_or_post(client, created_portal_link, method):
    with SessionLocal() as db:
        link = db.get(PortalLink, uuid.UUID(created_portal_link["id"]))
        link.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    url = f"/api/v1/portal-links/token/{created_portal_link['token']}/messages"
    response = client.get(url) if method == "get" else client.post(url, json={"body": "hi"})
    assert response.status_code == 404


def test_portal_messages_are_not_rate_limited(client, created_portal_link):
    url = f"/api/v1/portal-links/token/{created_portal_link['token']}/messages"
    responses = [client.post(url, json={"body": f"message {index}"}) for index in range(11)]
    assert all(response.status_code == 201 for response in responses)


def test_message_body_round_trips_as_plain_text(client, created_portal_link):
    payload = '<script>alert("xss")</script>'
    url = f"/api/v1/portal-links/token/{created_portal_link['token']}/messages"
    response = client.post(url, json={"body": payload})
    assert response.status_code == 201
    assert response.json()["body"] == payload
