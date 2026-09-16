"""Sprint 034 — tenant-configurable company identity on customer-facing PDFs.

The defect this covers: until this sprint app/quotes/pdf.py hardcoded one
company's letterhead ("SIMO MARBLE & CONSTRUCTION LTD / Unit 4, Riverside
Trade Park, London") into every invoice the platform produced, for every
tenant. Tenant B downloading Tenant B's own invoice got Tenant A's trading
identity printed on it — a cross-tenant leak in the one artefact that
actually reaches a customer.

Two independent layers are tested here, deliberately:

  * `app/tenants/identity.py` — the pure fallback/formatting rules, tested
    directly against plain objects (no database, no HTTP).
  * The two invoice endpoints — tested end-to-end by extracting the real
    rendered text back out of the generated PDF bytes (`_pdf_text` below),
    because "the right dict reached PDFGenerator" is not the same claim as
    "the right name is on the page a customer opens".
"""

import base64
import datetime
import re
import uuid
import zlib

import pytest
from sqlalchemy import delete, select

from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Quote, QuoteItem, Subscription, Tenant, User
from app.quotes.pdf import PDFGenerator
from app.tenants.identity import CompanyIdentity, resolve
from app.tenants.models import TenantCreate, TenantProfileUpdate
from app.tenants.service import tenant_service

RUN_ID = uuid.uuid4().hex[:10]
OTHER_TENANT_NAME = f"Pytest Identity Co {RUN_ID}"
OTHER_OWNER_EMAIL = f"pytest-identity-owner-{RUN_ID}@example.invalid"
PASSWORD = "pytest-identity-pw-123"
OTHER_POSTCODE = f"PYTID{RUN_ID[:5].upper()}"

# The exact strings that used to be hardcoded. Asserted *absent* below —
# this is the regression guard, not decoration.
LEGACY_NAME_FRAGMENT = "SIMO MARBLE"
LEGACY_ADDRESS_FRAGMENT = "Riverside Trade Park"


class _FakeTenant:
    """A stand-in for a Tenant row. `resolve()` reads attributes only, so
    testing it against the ORM would test SQLAlchemy, not the rules."""

    def __init__(self, **kwargs):
        for field in (
            "name", "legal_name", "trading_name", "address_line1", "address_line2",
            "city", "postcode", "country", "contact_email", "contact_phone",
            "website", "company_number", "vat_number", "logo_url", "document_footer",
        ):
            setattr(self, field, kwargs.get(field))


def _pdf_text(pdf: bytes) -> str:
    """Read the rendered text back out of a ReportLab PDF.

    ReportLab writes content streams as ASCII85-then-Flate, so the visible
    text is not present in the raw bytes — a naive `b"Acme" in pdf` assert
    would pass vacuously against *any* document, including a wrong one.
    Decoding both layers keeps these assertions honest without adding a
    PDF-parsing dependency to the project for one test module.
    """
    chunks = []
    for match in re.finditer(rb"stream(.*?)endstream", pdf, re.S):
        raw = match.group(1).strip()
        if raw.endswith(b"~>"):
            raw = raw[:-2]
        try:
            raw = base64.a85decode(raw)
        except Exception:
            pass
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        chunks.append(raw.decode("latin-1", "replace"))
    return "\n".join(chunks)


def _invoice(company: CompanyIdentity | None) -> dict:
    return {
        "id": uuid.uuid4(),
        "customer": "Jane & Sons",
        "company": company,
        "line_items": [{"description": "Worktop", "amount": 100.0}],
        "price_before_vat": 100.0,
        "vat": 20.0,
        "total": 120.0,
        "created_at": datetime.datetime(2026, 1, 2),
    }


# --------------------------------------------------------------------------
# identity.resolve() — the fallback and formatting rules
# --------------------------------------------------------------------------


def test_display_name_prefers_trading_name():
    identity = resolve(
        _FakeTenant(name="Workspace", legal_name="Legal Ltd", trading_name="Trading Co")
    )
    assert identity.display_name == "Trading Co"
    # Legal entity still shown, but only because it differs from the heading.
    assert identity.legal_name == "Legal Ltd"


def test_display_name_falls_back_to_legal_name_then_workspace_name():
    assert resolve(_FakeTenant(name="Workspace", legal_name="Legal Ltd")).display_name == "Legal Ltd"
    assert resolve(_FakeTenant(name="Workspace")).display_name == "Workspace"


def test_legal_name_not_repeated_when_it_matches_the_heading():
    identity = resolve(_FakeTenant(name="Workspace", legal_name="Legal Ltd"))
    assert identity.display_name == "Legal Ltd"
    assert identity.legal_name is None


def test_unconfigured_tenant_never_inherits_the_old_hardcoded_identity():
    """The whole point of the sprint: a tenant that has configured nothing
    gets its own workspace name, not the company that used to be baked in."""
    identity = resolve(_FakeTenant(name="Some Other Builder Ltd"))
    assert identity.display_name == "Some Other Builder Ltd"
    assert identity.address_lines == ()
    assert identity.registration_lines == ()


def test_resolve_none_tenant_yields_empty_identity():
    identity = resolve(None)
    assert identity.display_name == ""
    assert identity.address_lines == ()


def test_address_lines_join_city_and_postcode_and_skip_blanks():
    identity = resolve(
        _FakeTenant(
            name="X",
            address_line1="Unit 4, Riverside Trade Park",
            address_line2="   ",
            city="London",
            postcode="E1 1AA",
            country="United Kingdom",
        )
    )
    assert identity.address_lines == (
        "Unit 4, Riverside Trade Park",
        "London, E1 1AA",
        "United Kingdom",
    )


def test_registration_lines_only_render_supplied_numbers():
    """A missing VAT number means the line is absent — never a placeholder.
    A fabricated registration number on a UK invoice is a legal defect."""
    assert resolve(_FakeTenant(name="X")).registration_lines == ()

    only_company = resolve(_FakeTenant(name="X", company_number="12345678"))
    assert only_company.registration_lines == ("Company registration no. 12345678",)

    both = resolve(_FakeTenant(name="X", company_number="12345678", vat_number="GB999"))
    assert both.registration_lines == (
        "Company registration no. 12345678",
        "VAT registration no. GB999",
    )


def test_whitespace_only_fields_are_treated_as_absent():
    identity = resolve(_FakeTenant(name="X", trading_name="   ", vat_number="  "))
    assert identity.display_name == "X"
    assert identity.registration_lines == ()


# --------------------------------------------------------------------------
# PDFGenerator — what actually lands on the page
# --------------------------------------------------------------------------


def test_pdf_renders_the_supplied_company_and_not_the_old_hardcoded_one():
    pdf = PDFGenerator().create(
        _invoice(
            CompanyIdentity(
                display_name="Northern Granite Ltd",
                address_lines=("2 Quarry Road", "Leeds, LS1 1AA"),
                registration_lines=("VAT registration no. GB123456789",),
            )
        )
    )
    text = _pdf_text(pdf)
    assert "NORTHERN GRANITE LTD" in text
    assert "GB123456789" in text
    assert LEGACY_NAME_FRAGMENT not in text
    assert LEGACY_ADDRESS_FRAGMENT not in text


def test_pdf_with_no_company_has_no_letterhead_rather_than_a_wrong_one():
    text = _pdf_text(PDFGenerator().create(_invoice(None)))
    assert LEGACY_NAME_FRAGMENT not in text
    # The invoice body itself still renders — an unattributed document is
    # recoverable; one carrying the wrong company's name is not.
    assert "Worktop" in text


def test_pdf_escapes_ampersands_in_tenant_supplied_text():
    """ReportLab paragraphs are mini-HTML. "Simo Marble & Construction Ltd"
    is an ordinary company name that would otherwise abort the render — and
    naive escaping would leave a literal "&amp;" on the customer's invoice."""
    text = _pdf_text(
        PDFGenerator().create(_invoice(CompanyIdentity(display_name="Stone & Slate Ltd")))
    )
    assert "STONE & SLATE LTD" in text
    assert "&amp;" not in text


def test_pdf_survives_angle_brackets_in_tenant_supplied_text():
    """Separate from the ampersand case: `<`/`>` would be parsed as markup
    and raise. They render as themselves — ReportLab emits them as their own
    text runs, so assert on the pieces rather than one contiguous string."""
    text = _pdf_text(
        PDFGenerator().create(_invoice(CompanyIdentity(display_name="Stone <Ltd>")))
    )
    assert "STONE <" in text and "LTD" in text
    assert "&lt;" not in text


def test_pdf_renders_the_document_footer_when_configured():
    pdf = PDFGenerator().create(
        _invoice(
            CompanyIdentity(
                display_name="Footer Co",
                document_footer="Payment due within 30 days. Registered in England.",
            )
        )
    )
    assert "Payment due within 30 days" in _pdf_text(pdf)


# --------------------------------------------------------------------------
# The API: company profile round-trip and PATCH semantics
# --------------------------------------------------------------------------


def test_get_company_profile_returns_the_callers_own_tenant(client, auth_headers):
    r = client.get("/api/v1/tenants/me/profile", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "legal_name" in body and "vat_number" in body and "logo_url" in body
    assert body["id"] and body["slug"]


def test_patch_company_profile_round_trips(client, auth_headers):
    original = client.get("/api/v1/tenants/me/profile", headers=auth_headers).json()
    try:
        r = client.patch(
            "/api/v1/tenants/me/profile",
            headers=auth_headers,
            json={
                "legal_name": "Pytest Identity Ltd",
                "trading_name": "Pytest Identity",
                "address_line1": "9 Test Street",
                "city": "Manchester",
                "postcode": "M1 1AA",
                "company_number": "09876543",
                "vat_number": "GB111222333",
                "document_footer": "Thanks for your business.",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["legal_name"] == "Pytest Identity Ltd"
        assert body["vat_number"] == "GB111222333"

        # And it is actually persisted, not just echoed back.
        again = client.get("/api/v1/tenants/me/profile", headers=auth_headers).json()
        assert again["trading_name"] == "Pytest Identity"
        assert again["company_number"] == "09876543"
    finally:
        _restore_profile(client, auth_headers, original)


def test_patch_only_writes_the_fields_it_was_sent(client, auth_headers):
    """PATCH semantics matter here: an older client that doesn't know about
    `vat_number` must not silently wipe a tenant's VAT registration."""
    original = client.get("/api/v1/tenants/me/profile", headers=auth_headers).json()
    try:
        client.patch(
            "/api/v1/tenants/me/profile",
            headers=auth_headers,
            json={"legal_name": "Keep Me Ltd", "vat_number": "GB555"},
        )
        r = client.patch(
            "/api/v1/tenants/me/profile",
            headers=auth_headers,
            json={"contact_phone": "0161 000 0000"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["contact_phone"] == "0161 000 0000"
        assert body["legal_name"] == "Keep Me Ltd"
        assert body["vat_number"] == "GB555"
    finally:
        _restore_profile(client, auth_headers, original)


def test_patch_empty_string_clears_a_field(client, auth_headers):
    original = client.get("/api/v1/tenants/me/profile", headers=auth_headers).json()
    try:
        client.patch(
            "/api/v1/tenants/me/profile", headers=auth_headers, json={"vat_number": "GB777"}
        )
        r = client.patch(
            "/api/v1/tenants/me/profile", headers=auth_headers, json={"vat_number": ""}
        )
        assert r.status_code == 200
        assert r.json()["vat_number"] is None
    finally:
        _restore_profile(client, auth_headers, original)


def _restore_profile(client, headers, original: dict) -> None:
    """Put the seeded tenant back exactly as it was — these tests mutate the
    one shared seeded tenant every other test file's fixtures also use."""
    client.patch(
        "/api/v1/tenants/me/profile",
        headers=headers,
        json={
            key: original.get(key) or ""
            for key in (
                "legal_name", "trading_name", "address_line1", "address_line2",
                "city", "postcode", "country", "contact_email", "contact_phone",
                "website", "company_number", "vat_number", "logo_url",
                "document_footer",
            )
        },
    )


# --------------------------------------------------------------------------
# The regression that started the sprint: two tenants, two letterheads
# --------------------------------------------------------------------------


def _cleanup_other_tenant():
    db = SessionLocal()
    try:
        # Order matters — every FK below points at the Tenant row, which
        # cannot be deleted while a child row still references it (ADR-025).
        db.execute(
            delete(QuoteItem).where(
                QuoteItem.quote_id.in_(select(Quote.id).where(Quote.postcode == OTHER_POSTCODE))
            )
        )
        db.execute(delete(Quote).where(Quote.postcode == OTHER_POSTCODE))
        db.execute(delete(Customer).where(Customer.name == OTHER_TENANT_NAME))
        tenant = db.query(Tenant).filter(Tenant.name == OTHER_TENANT_NAME).first()
        if tenant is not None:
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
        db.execute(delete(User).where(User.email == OTHER_OWNER_EMAIL))
        db.execute(delete(Tenant).where(Tenant.name == OTHER_TENANT_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def other_tenant_headers(client):
    """A second, genuinely separate tenant with its own configured identity."""
    _cleanup_other_tenant()
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=OTHER_TENANT_NAME))
        auth_service.create_user(
            db,
            tenant_id=tenant.id,
            name="Identity Owner",
            email=OTHER_OWNER_EMAIL,
            password=PASSWORD,
            role="Owner",
        )
        tenant_service.update_identity(
            db,
            tenant.id,
            TenantProfileUpdate(
                legal_name="Second Tenant Stoneworks Ltd",
                address_line1="7 Elsewhere Lane",
                city="Bristol",
                vat_number="GB000111222",
            ),
        )
    finally:
        db.close()

    r = client.post(
        "/api/v1/auth/login", json={"email": OTHER_OWNER_EMAIL, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    yield {"Authorization": f"Bearer {r.json()['access_token']}"}
    _cleanup_other_tenant()


def test_second_tenants_invoice_carries_its_own_identity_not_another_tenants(
    client, other_tenant_headers
):
    """The original bug, stated as a test: a tenant's own invoice must show
    that tenant's business, never the one that used to be hardcoded and
    never the tenant next door."""
    # POST /quote stays deliberately public (ADR-023) but tags the quote
    # with the caller's tenant when a token is presented — which is exactly
    # what this test needs: a quote owned by the *second* tenant.
    quote = client.post(
        "/api/v1/quote",
        headers=other_tenant_headers,
        json={
            "customer": OTHER_TENANT_NAME,
            "material": "calacatta gold",
            "thickness": "20mm",
            "kitchen_length": 3.0,
            "postcode": OTHER_POSTCODE,
        },
    )
    assert quote.status_code in (200, 201), quote.text

    r = client.get(
        f"/api/v1/quotes/{quote.json()['id']}/invoice", headers=other_tenant_headers
    )
    assert r.status_code == 200
    text = _pdf_text(r.content)

    assert "SECOND TENANT STONEWORKS LTD" in text
    assert "GB000111222" in text
    assert LEGACY_NAME_FRAGMENT not in text
    assert LEGACY_ADDRESS_FRAGMENT not in text
