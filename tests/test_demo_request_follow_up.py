"""Phase B — demo request follow-up: GeoCore's own sales workspace gets a
CRM customer record, an activity entry and an Owner notification, and the
prospect gets a confirmation. With no sales workspace configured, nothing
is written anywhere but the demo_requests table and nobody is emailed."""

import uuid

import pytest
from sqlalchemy import delete, func, select

from app.auth.service import auth_service
from app.communications.provider import SendOutcome, SendResult
from app.communications.service import DeliveryService
from app.core.config import settings
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Communication, Customer, DemoRequest, Subscription, Tenant, User
from app.demo_requests import service as demo_service
from app.demo_requests.models import DemoRequestCreate
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

RUN = uuid.uuid4().hex[:8]


class _FakeProvider:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        return SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id=f"msg-{len(self.sent)}")


def _email(label):
    return f"demo-follow-up-{RUN}-{label}-{uuid.uuid4().hex[:6]}@example.invalid"


def _payload(email, **overrides):
    data = {
        "first_name": "Jamie",
        "last_name": "Fabricator",
        "email": email,
        "phone": "+44 7700 900123",
        "company_name": f"Fabricator Stoneworks {RUN}",
        "team_size": "4-10",
        "trades": ["stone"],
        "current_system": "Spreadsheets",
        "message": "Keen to see quoting.",
        "preferred_contact_method": "email",
    }
    data.update(overrides)
    return data


@pytest.fixture()
def sales_workspace(monkeypatch):
    db = SessionLocal()
    tenant = tenant_service.create(db, TenantCreate(name=f"GeoCore Sales {RUN} {uuid.uuid4().hex[:4]}"))
    owner = auth_service.create_user(
        db, tenant_id=tenant.id, name="Sales Owner", email=_email("owner"), password="Sales-Owner-Pass-1!", role="Owner"
    )
    auth_service.create_user(
        db, tenant_id=tenant.id, name="Sales Staff", email=_email("staff"), password="Sales-Staff-Pass-1!", role="Staff"
    )
    tenant_id, owner_email = tenant.id, owner.email
    db.close()
    monkeypatch.setattr(settings, "platform_sales_tenant_id", str(tenant_id))
    provider = _FakeProvider()
    monkeypatch.setattr(demo_service, "delivery_service", DeliveryService(provider=provider))
    yield tenant_id, owner_email, provider
    db = SessionLocal()
    try:
        db.execute(delete(Communication).where(Communication.tenant_id == tenant_id))
        db.execute(delete(Customer).where(Customer.tenant_id == tenant_id))
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
        db.execute(delete(User).where(User.tenant_id == tenant_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.execute(delete(DemoRequest).where(DemoRequest.company_name.like(f"%{RUN}%")))
        db.commit()
    finally:
        db.close()


def test_demo_request_lands_in_the_sales_workspace_crm_with_notifications(client, sales_workspace):
    tenant_id, owner_email, provider = sales_workspace
    prospect = _email("prospect")
    assert client.post("/api/v1/demo-requests", json=_payload(prospect)).status_code == 201

    db = SessionLocal()
    try:
        customer = db.scalars(select(Customer).where(Customer.tenant_id == tenant_id)).one()
        assert customer.email == prospect
        assert customer.customer_type == "company"
        assert customer.company_name == f"Fabricator Stoneworks {RUN}"
        assert "Keen to see quoting." in customer.notes
        activity = db.scalars(select(ActivityLog).where(ActivityLog.tenant_id == tenant_id)).all()
        assert any(a.type == "demo_request_received" for a in activity)
    finally:
        db.close()

    recipients = {m.recipient: m.subject for m in provider.sent}
    # Only the verified Owner is notified — never Staff.
    assert recipients == {
        owner_email.lower(): "New GeoCore demo request",
        prospect.lower(): "We've received your GeoCore demo request",
    }


def test_a_repeat_request_updates_the_same_customer_not_a_duplicate(sales_workspace):
    tenant_id, _, provider = sales_workspace
    prospect = _email("repeat")
    db = SessionLocal()
    try:
        demo_service.create_demo_request(db, DemoRequestCreate(**_payload(prospect)))
        demo_service.create_demo_request(db, DemoRequestCreate(**_payload(prospect.upper(), message="Second note.")))
        customers = db.scalars(select(Customer).where(Customer.tenant_id == tenant_id)).all()
        assert len(customers) == 1
        assert "Keen to see quoting." in customers[0].notes and "Second note." in customers[0].notes
    finally:
        db.close()
    assert len([m for m in provider.sent if "received your" in m.subject]) == 2


def test_honeypot_submission_writes_nothing_and_emails_nobody(client, sales_workspace):
    tenant_id, _, provider = sales_workspace
    assert client.post("/api/v1/demo-requests", json=_payload(_email("bot"), website="spam")).status_code == 201
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)) == 0
    finally:
        db.close()
    assert provider.sent == []


def test_without_a_sales_workspace_only_the_request_is_stored(client, monkeypatch):
    monkeypatch.setattr(settings, "platform_sales_tenant_id", None)
    provider = _FakeProvider()
    monkeypatch.setattr(demo_service, "delivery_service", DeliveryService(provider=provider))
    prospect = _email("unconfigured")
    try:
        assert client.post("/api/v1/demo-requests", json=_payload(prospect)).status_code == 201
        db = SessionLocal()
        try:
            assert db.scalar(select(func.count(DemoRequest.id)).where(DemoRequest.email == prospect)) == 1
            assert db.scalar(select(func.count(Customer.id)).where(Customer.email == prospect)) == 0
        finally:
            db.close()
        assert provider.sent == []
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(DemoRequest).where(DemoRequest.email == prospect))
            db.commit()
        finally:
            db.close()


@pytest.mark.parametrize("bad_value", ["not-a-uuid", str(uuid.uuid4())])
def test_a_misconfigured_sales_workspace_never_breaks_the_public_form(client, monkeypatch, bad_value):
    monkeypatch.setattr(settings, "platform_sales_tenant_id", bad_value)
    prospect = _email("misconfigured")
    try:
        assert client.post("/api/v1/demo-requests", json=_payload(prospect)).status_code == 201
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(DemoRequest).where(DemoRequest.email == prospect))
            db.commit()
        finally:
            db.close()


def test_a_follow_up_failure_still_keeps_the_request(client, sales_workspace, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(demo_service, "_follow_up", boom)
    prospect = _email("failure")
    assert client.post("/api/v1/demo-requests", json=_payload(prospect)).status_code == 201
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(DemoRequest.id)).where(DemoRequest.email == prospect)) == 1
    finally:
        db.close()


def test_same_email_typed_differently_maps_to_one_customer(client, sales_workspace):
    tenant_id, _, _ = sales_workspace
    prospect = _email("normalise")
    assert client.post("/api/v1/demo-requests", json=_payload(f"  {prospect.upper()}  ")).status_code == 201
    db = SessionLocal()
    try:
        demo_service.create_demo_request(db, DemoRequestCreate(**_payload(prospect, message="Follow-up.")))
        customers = db.scalars(select(Customer).where(Customer.tenant_id == tenant_id)).all()
        assert [c.email for c in customers] == [prospect]
    finally:
        db.close()


def test_a_rapid_double_submission_creates_one_customer(client, sales_workspace):
    tenant_id, _, provider = sales_workspace
    prospect = _email("double-click")
    first = client.post("/api/v1/demo-requests", json=_payload(prospect))
    second = client.post("/api/v1/demo-requests", json=_payload(prospect))
    assert (first.status_code, second.status_code) == (201, 429)
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)) == 1
    finally:
        db.close()
    assert len([m for m in provider.sent if "received your" in m.subject]) == 1


def test_two_people_from_the_same_company_are_two_contacts(sales_workspace):
    """A customer record is a person you deal with (see CustomerCreate):
    two colleagues from one company are two contacts, not a duplicate."""
    tenant_id, _, _ = sales_workspace
    db = SessionLocal()
    try:
        demo_service.create_demo_request(db, DemoRequestCreate(**_payload(_email("colleague-a"))))
        demo_service.create_demo_request(db, DemoRequestCreate(**_payload(_email("colleague-b"), first_name="Sam")))
        customers = db.scalars(select(Customer).where(Customer.tenant_id == tenant_id)).all()
        assert len(customers) == 2
        assert {c.company_name for c in customers} == {f"Fabricator Stoneworks {RUN}"}
    finally:
        db.close()
