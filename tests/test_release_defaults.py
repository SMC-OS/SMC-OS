"""Release defaults: financial approval authority, quote revisions, invoice supplier settings and snapshots."""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select

from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import User
from tests.conftest import make_supplier_ready
from tests.test_tenant_identity import _pdf_text

QUOTE = {"title": "Release default quote", "vat_rate": 0.2, "lines": [
    {"line_kind": "labour", "description": "Fitting", "quantity": 2, "unit": "item", "unit_price": 500.0}]}


@pytest.fixture()
def staff(client, auth_headers):
    """A Staff user in the seeded owner's workspace."""
    owner = client.get("/api/v1/auth/me", headers=auth_headers).json()
    email, password = f"release-staff-{uuid.uuid4().hex[:8]}@example.invalid", "Release-Staff-Password-1!"
    db = SessionLocal()
    try:
        user = auth_service.create_user(db, tenant_id=uuid.UUID(owner["tenant_id"]), name="Release Staff", email=email,
                                        password=password, role="Staff")
        user_id = str(user.id)
    finally:
        db.close()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    yield {"id": user_id, "headers": {"Authorization": f"Bearer {token}"}}
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == email))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _quote(client, headers, **over):
    r = client.post("/api/v1/quotes", headers=headers, json={**QUOTE, **over})
    assert r.status_code == 201, r.text
    return r.json()


def _project(client, headers):
    r = client.post("/api/v1/projects", headers=headers, json={"name": f"Release project {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    return r.json()


def _variation(client, headers, project_id):
    r = client.post(f"/api/v1/projects/{project_id}/variations", headers=headers,
                    json={"title": "Extra", "items": [{"description": "Extra work", "quantity": 1, "unit": "item", "unit_price": 250.0}]})
    assert r.status_code == 201, r.text
    client.post(f"/api/v1/variations/{r.json()['id']}/send", headers=headers)
    return r.json()


def _po(client, headers):
    r = client.post("/api/v1/purchase-orders", headers=headers,
                    json={"items": [{"description": "Slab", "quantity": 2, "unit": "slab", "unit_cost": 300.0}]})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- financial approval authority
def test_staff_prepare_but_cannot_approve_by_default(client, auth_headers, staff):
    q = _quote(client, staff["headers"])
    assert client.post(f"/api/v1/quotes/{q['id']}/approve", headers=staff["headers"]).status_code == 403
    project = _project(client, staff["headers"])
    v = _variation(client, staff["headers"], project["id"])
    assert client.post(f"/api/v1/variations/{v['id']}/approve", headers=staff["headers"]).status_code == 403
    po = _po(client, staff["headers"])
    assert client.post(f"/api/v1/purchase-orders/{po['id']}/approve", headers=staff["headers"]).status_code == 403
    # nothing changed
    assert client.get(f"/api/v1/quotes/{q['id']}", headers=auth_headers).json()["status"] != "approved"


def test_owner_approval_records_actor_amount_and_time(client, auth_headers):
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    q = _quote(client, auth_headers)
    approved = client.post(f"/api/v1/quotes/{q['id']}/approve", headers=auth_headers).json()
    assert approved["approved_by_user_id"] == me["id"] and approved["approved_at"]
    assert approved["approved_amount"] == pytest.approx(1200.0)
    project = _project(client, auth_headers)
    v = _variation(client, auth_headers, project["id"])
    av = client.post(f"/api/v1/variations/{v['id']}/approve", headers=auth_headers)
    assert av.status_code == 200
    po = _po(client, auth_headers)
    ap = client.post(f"/api/v1/purchase-orders/{po['id']}/approve", headers=auth_headers)
    assert ap.status_code == 200
    db = SessionLocal()
    try:
        from app.database.models import PurchaseOrder, Variation
        assert db.get(Variation, uuid.UUID(v["id"])).approved_amount == pytest.approx(300.0)
        assert db.get(PurchaseOrder, uuid.UUID(po["id"])).approved_amount == pytest.approx(720.0)
    finally:
        db.close()


def test_owner_can_delegate_and_withdraw_authority(client, auth_headers, staff):
    r = client.patch(f"/api/v1/users/{staff['id']}/approval-authority", headers=auth_headers, json={"can_approve_financials": True})
    assert r.status_code == 200 and r.json()["can_approve_financials"] is True
    q = _quote(client, staff["headers"])
    ok = client.post(f"/api/v1/quotes/{q['id']}/approve", headers=staff["headers"])
    assert ok.status_code == 200 and ok.json()["approved_by_user_id"] == staff["id"]
    client.patch(f"/api/v1/users/{staff['id']}/approval-authority", headers=auth_headers, json={"can_approve_financials": False})
    q2 = _quote(client, staff["headers"])
    assert client.post(f"/api/v1/quotes/{q2['id']}/approve", headers=staff["headers"]).status_code == 403


def test_staff_cannot_escalate_and_cross_tenant_is_denied(client, auth_headers, staff, other_tenant_auth_headers):
    own = client.patch(f"/api/v1/users/{staff['id']}/approval-authority", headers=staff["headers"], json={"can_approve_financials": True})
    assert own.status_code == 403
    cross = client.patch(f"/api/v1/users/{staff['id']}/approval-authority", headers=other_tenant_auth_headers, json={"can_approve_financials": True})
    assert cross.status_code == 404
    q = _quote(client, auth_headers)
    assert client.post(f"/api/v1/quotes/{q['id']}/approve", headers=other_tenant_auth_headers).status_code == 404
    # the failed escalation did not stick
    q2 = _quote(client, staff["headers"])
    assert client.post(f"/api/v1/quotes/{q2['id']}/approve", headers=staff["headers"]).status_code == 403


def test_delegation_applies_to_staff_only(client, auth_headers):
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    r = client.patch(f"/api/v1/users/{me['id']}/approval-authority", headers=auth_headers, json={"can_approve_financials": True})
    assert r.status_code == 409


def test_unauthenticated_approval_is_refused(client, auth_headers):
    q = _quote(client, auth_headers)
    assert client.post(f"/api/v1/quotes/{q['id']}/approve").status_code == 401


# ---------------------------------------------------------------- quote revisions
def test_revision_preserves_the_approved_original(client, auth_headers):
    original = _quote(client, auth_headers)
    approved = client.post(f"/api/v1/quotes/{original['id']}/approve", headers=auth_headers).json()
    r = client.post(f"/api/v1/quotes/{original['id']}/revise", headers=auth_headers)
    assert r.status_code == 201, r.text
    rev = r.json()
    assert rev["id"] != original["id"] and rev["status"] == "draft" and rev["revision_number"] == 2
    assert rev["revision_of_quote_id"] == original["id"] and rev["total"] == approved["total"]
    assert rev["approved_at"] is None and rev["invoice_number"] is None
    # edit the revision: the original is untouched
    assert client.patch(f"/api/v1/quotes/{rev['id']}", headers=auth_headers, json={"discount_amount": 100.0}).status_code == 200
    again = client.get(f"/api/v1/quotes/{original['id']}", headers=auth_headers).json()
    assert again["status"] == "approved" and again["total"] == approved["total"] and again["approved_at"] == approved["approved_at"]
    assert len(again["items"]) == len(original["items"])
    # still cannot silently overwrite the approved original
    assert client.patch(f"/api/v1/quotes/{original['id']}", headers=auth_headers, json={"title": "x"}).status_code == 409


def test_revision_history_chain_and_states(client, auth_headers, other_tenant_auth_headers):
    q = _quote(client, auth_headers)
    assert client.post(f"/api/v1/quotes/{q['id']}/revise", headers=auth_headers).status_code == 409  # draft: just edit
    client.post(f"/api/v1/quotes/{q['id']}/approve", headers=auth_headers)
    rev2 = client.post(f"/api/v1/quotes/{q['id']}/revise", headers=auth_headers).json()
    client.post(f"/api/v1/quotes/{rev2['id']}/approve", headers=auth_headers)
    rev3 = client.post(f"/api/v1/quotes/{rev2['id']}/revise", headers=auth_headers).json()
    assert rev3["revision_number"] == 3 and rev3["revision_of_quote_id"] == q["id"]
    chain = client.get(f"/api/v1/quotes/{rev3['id']}/revisions", headers=auth_headers).json()
    assert [c["revision_number"] for c in chain] == [1, 2, 3]
    assert [c["status"] for c in chain] == ["approved", "approved", "draft"]
    assert chain[0]["approved_amount"] is not None
    assert client.get(f"/api/v1/quotes/{q['id']}/revisions", headers=other_tenant_auth_headers).status_code == 404
    assert client.post(f"/api/v1/quotes/{q['id']}/revise", headers=other_tenant_auth_headers).status_code == 404


# ---------------------------------------------------------------- invoice supplier settings
@pytest.fixture()
def clean_supplier(client, auth_headers):
    original = client.get("/api/v1/tenants/me/profile", headers=auth_headers).json()
    blank = {k: "" for k in ("legal_name", "address_line1", "postcode", "vat_number", "bank_account_name", "bank_sort_code",
                             "bank_account_number", "payment_instructions")}
    client.patch("/api/v1/tenants/me/profile", headers=auth_headers, json={**blank, "vat_registered": False})
    yield
    keys = ("legal_name", "trading_name", "address_line1", "address_line2", "city", "postcode", "vat_number", "bank_account_name",
            "bank_sort_code", "bank_account_number", "payment_instructions")
    client.patch("/api/v1/tenants/me/profile", headers=auth_headers,
                 json={**{k: original.get(k) or "" for k in keys}, "vat_registered": original.get("vat_registered", False),
                       "payment_terms_days": original.get("payment_terms_days", 30)})


def test_issuing_requires_complete_supplier_details_and_invents_nothing(client, auth_headers, clean_supplier):
    q = _quote(client, auth_headers)
    r = client.get(f"/api/v1/quotes/{q['id']}/invoice", headers=auth_headers)
    assert r.status_code == 422
    fields = {m["field"] for m in r.json()["detail"]["missing"]}
    assert {"legal_name", "address", "vat_registered", "payment_details"} <= fields
    # nothing was issued, so the number was not consumed
    assert client.get(f"/api/v1/quotes/{q['id']}", headers=auth_headers).json()["invoice_number"] is None


def test_vat_status_rules(client, auth_headers, clean_supplier):
    base = {"legal_name": "Rules Ltd", "address_line1": "1 Rule St", "postcode": "SW1A 1AA", "bank_account_name": "Rules Ltd",
            "bank_sort_code": "12-34-56", "bank_account_number": "12345678"}
    client.patch("/api/v1/tenants/me/profile", headers=auth_headers, json={**base, "vat_registered": True})
    q = _quote(client, auth_headers)
    miss = client.get(f"/api/v1/quotes/{q['id']}/invoice", headers=auth_headers).json()["detail"]["missing"]
    assert [m["field"] for m in miss] == ["vat_number"]
    # not registered: VAT may not be charged...
    client.patch("/api/v1/tenants/me/profile", headers=auth_headers, json={"vat_registered": False})
    assert client.get(f"/api/v1/quotes/{q['id']}/invoice", headers=auth_headers).status_code == 422
    # ...but a 0% quote is fine
    zero = _quote(client, auth_headers, vat_rate=0.0)
    assert client.get(f"/api/v1/quotes/{zero['id']}/invoice", headers=auth_headers).status_code == 200


def test_invalid_bank_and_vat_formats_are_rejected(client, auth_headers):
    for body in ({"bank_sort_code": "12"}, {"bank_account_number": "123"}, {"vat_number": "ABC"}, {"payment_terms_days": 999}):
        assert client.patch("/api/v1/tenants/me/profile", headers=auth_headers, json=body).status_code == 422


def test_issued_invoice_snapshot_is_frozen_and_due_date_calculated(client, auth_headers, clean_supplier):
    make_supplier_ready(client, auth_headers, legal_name="Frozen Original Ltd", payment_terms_days=14)
    q = _quote(client, auth_headers)
    first = client.get(f"/api/v1/quotes/{q['id']}/invoice", headers=auth_headers)
    assert first.status_code == 200
    text1 = _pdf_text(first.content)
    assert "FROZEN ORIGINAL LTD" in text1 and "Sort code: 12-34-56" in text1 and "Payment terms: 14 days" in text1
    due = (date.today() + timedelta(days=14)).strftime("%d %B %Y")
    assert f"Payment due: {due}" in text1 or (date.today() + timedelta(days=14)).strftime("%d %B %Y") in text1
    # change every supplier setting afterwards
    make_supplier_ready(client, auth_headers, legal_name="Changed Later Ltd", bank_sort_code="99-88-77", payment_terms_days=60)
    second = client.get(f"/api/v1/quotes/{q['id']}/invoice", headers=auth_headers)
    text2 = _pdf_text(second.content)
    assert "FROZEN ORIGINAL LTD" in text2 and "CHANGED LATER" not in text2
    assert "99-88-77" not in text2 and "Payment terms: 14 days" in text2
    # a new invoice uses the new settings and terms
    q2 = _quote(client, auth_headers)
    text3 = _pdf_text(client.get(f"/api/v1/quotes/{q2['id']}/invoice", headers=auth_headers).content)
    assert "CHANGED LATER LTD" in text3 and "99-88-77" in text3 and "Payment terms: 60 days" in text3


def test_numbering_and_arithmetic_are_unchanged(client, auth_headers, clean_supplier):
    make_supplier_ready(client, auth_headers)
    prefix = f"RD{uuid.uuid4().hex[:6].upper()}"
    client.patch("/api/v1/tenants/me/profile", headers=auth_headers, json={"invoice_prefix": prefix, "invoice_next_number": 7})
    try:
        q = _quote(client, auth_headers, discount_amount=100.0)
        assert q["price_before_vat"] == pytest.approx(900.0) and q["vat"] == pytest.approx(180.0) and q["total"] == pytest.approx(1080.0)
        r = client.get(f"/api/v1/quotes/{q['id']}/invoice", headers=auth_headers)
        assert f'filename="{prefix}-000007.pdf"' in r.headers["content-disposition"]
        text = _pdf_text(r.content)
        assert "£1,080.00" in text and "VAT (20%)" in text and "£180.00" in text
    finally:
        client.patch("/api/v1/tenants/me/profile", headers=auth_headers, json={"invoice_prefix": "Invoice", "invoice_next_number": 1})


def test_long_names_accents_and_pound_signs_render(client, auth_headers, clean_supplier):
    long_name = "Müller-Ó Briain & Þórsdóttir Construction, Stonework and Renovation Services (Greater Manchester) Limited"
    make_supplier_ready(client, auth_headers, legal_name=long_name, address_line1="Unit 12, Zażółć Gęślą Business Park, Façade Road",
                        payment_instructions="Pay by BACS. Please quote the invoice number.\nQuestions: accounts@example.invalid")
    q = _quote(client, auth_headers, title="Café extension — £ and € and ½ job")
    r = client.get(f"/api/v1/quotes/{q['id']}/invoice", headers=auth_headers)
    assert r.status_code == 200
    text = _pdf_text(r.content)
    assert "MÜLLER" in text.upper() and "£1,200.00" in text and "Pay by BACS" in text
