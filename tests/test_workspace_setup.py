"""Workspace configuration, onboarding and branding — Sprint 036,
Workstreams I and J.

The regression this file guards hardest: a business that is already using
GeoCore must never be sent back through a setup wizard. Every tenant that
existed before Sprint 036 has a NULL onboarding_completed_at, so
"required" has to be computed from whether the workspace is actually being
used, not read straight off the column.
"""

import io
import uuid

import pytest

from app.tenants.branding import ALLOWED_LOGO_EXTENSIONS, MAX_LOGO_BYTES

RUN_ID = uuid.uuid4().hex[:8]

# A real 1x1 PNG. Small enough to inline, and genuinely a PNG so the
# upload path is exercised rather than a rename of some other bytes.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100fdff03fa0000000049454e44ae426082"
)


# --- Onboarding -----------------------------------------------------------


def test_an_established_workspace_is_never_asked_to_onboard(client, auth_headers):
    # The seeded tenant has real customers, quotes and projects from the
    # rest of this suite. Whatever the column says, it is not a new
    # workspace, and sending it to a setup wizard would be a regression
    # dressed as a feature.
    r = client.get("/api/v1/tenants/me/onboarding", headers=auth_headers)
    assert r.status_code == 200, r.text
    state = r.json()

    assert state["workspace_has_data"] is True
    assert state["required"] is False
    assert state["currency"] == "GBP"


def test_a_brand_new_workspace_is_asked_to_onboard(client, other_tenant_auth_headers):
    state = client.get(
        "/api/v1/tenants/me/onboarding", headers=other_tenant_auth_headers
    ).json()

    assert state["workspace_has_data"] is False
    assert state["required"] is True
    assert state["trades"] == []
    assert state["completed_at"] is None


def test_completing_onboarding_records_trades_and_currency(
    client, other_tenant_auth_headers
):
    r = client.patch(
        "/api/v1/tenants/me/onboarding",
        json={"trades": ["roofing", "kitchen", "general_building"], "complete": True},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 200, r.text
    profile = r.json()

    # Stored in catalogue order, not click order, so the value is stable.
    assert profile["trades"] == ["general_building", "kitchen", "roofing"]
    assert profile["onboarding_completed_at"] is not None

    state = client.get(
        "/api/v1/tenants/me/onboarding", headers=other_tenant_auth_headers
    ).json()
    assert state["required"] is False


def test_re_running_onboarding_does_not_rewrite_the_completion_date(
    client, other_tenant_auth_headers
):
    first = client.patch(
        "/api/v1/tenants/me/onboarding",
        json={"trades": ["roofing"], "complete": True},
        headers=other_tenant_auth_headers,
    ).json()

    second = client.patch(
        "/api/v1/tenants/me/onboarding",
        json={"trades": ["roofing", "flooring"], "complete": True},
        headers=other_tenant_auth_headers,
    ).json()

    # Catalogue order, not click order: roofing precedes flooring in
    # app/trades/catalogue.py.
    assert second["trades"] == ["roofing", "flooring"]
    # Changing a trade selection is not setting the workspace up again.
    assert second["onboarding_completed_at"] == first["onboarding_completed_at"]


def test_rejects_an_unknown_trade(client, other_tenant_auth_headers):
    r = client.patch(
        "/api/v1/tenants/me/onboarding",
        json={"trades": ["roofing", "time_travel"]},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 422


def test_onboarding_never_clears_company_identity(client, other_tenant_auth_headers):
    client.patch(
        "/api/v1/tenants/me/profile",
        json={"legal_name": f"Pytest Setup {RUN_ID} Ltd", "vat_number": "GB123456789"},
        headers=other_tenant_auth_headers,
    )
    profile = client.patch(
        "/api/v1/tenants/me/onboarding",
        json={"trades": ["roofing"], "complete": True},
        headers=other_tenant_auth_headers,
    ).json()

    # The two bodies are separate models precisely so that completing
    # onboarding can never blank a VAT number.
    assert profile["legal_name"] == f"Pytest Setup {RUN_ID} Ltd"
    assert profile["vat_number"] == "GB123456789"


# --- Currency -------------------------------------------------------------


def test_currency_defaults_to_gbp_and_can_be_changed_to_a_supported_one(
    client, other_tenant_auth_headers
):
    profile = client.get(
        "/api/v1/tenants/me/profile", headers=other_tenant_auth_headers
    ).json()
    assert profile["currency"] == "GBP"

    updated = client.patch(
        "/api/v1/tenants/me/profile",
        json={"currency": "eur"},
        headers=other_tenant_auth_headers,
    ).json()
    assert updated["currency"] == "EUR"


def test_rejects_an_unsupported_currency(client, other_tenant_auth_headers):
    r = client.patch(
        "/api/v1/tenants/me/profile",
        json={"currency": "XYZ"},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 422


def test_a_quote_is_denominated_in_the_workspace_currency_at_creation(
    client, other_tenant_auth_headers
):
    client.patch(
        "/api/v1/tenants/me/profile",
        json={"currency": "EUR"},
        headers=other_tenant_auth_headers,
    )
    quote = client.post(
        "/api/v1/quotes",
        json={
            "title": f"Pytest currency {RUN_ID}",
            "lines": [{"description": "Work", "quantity": 1, "unit": "job", "unit_price": 100}],
        },
        headers=other_tenant_auth_headers,
    ).json()
    assert quote["currency"] == "EUR"

    # Changing the workspace currency afterwards must not re-denominate a
    # document a customer already holds.
    client.patch(
        "/api/v1/tenants/me/profile",
        json={"currency": "GBP"},
        headers=other_tenant_auth_headers,
    )
    reread = client.get(
        f"/api/v1/quotes/{quote['id']}", headers=other_tenant_auth_headers
    ).json()
    assert reread["currency"] == "EUR"


# --- Logo upload ----------------------------------------------------------


def test_uploads_serves_and_deletes_a_logo(client, other_tenant_auth_headers):
    before = client.get(
        "/api/v1/tenants/me/profile", headers=other_tenant_auth_headers
    ).json()
    assert before["has_uploaded_logo"] is False
    assert client.get("/api/v1/tenants/me/logo", headers=other_tenant_auth_headers).status_code == 404

    uploaded = client.post(
        "/api/v1/tenants/me/logo",
        files={"file": ("logo.png", io.BytesIO(_PNG), "image/png")},
        headers=other_tenant_auth_headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["has_uploaded_logo"] is True
    # The storage filename must never reach a client.
    assert "logo_storage_filename" not in uploaded.json()

    served = client.get("/api/v1/tenants/me/logo", headers=other_tenant_auth_headers)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == _PNG
    assert "private" in served.headers.get("cache-control", "")

    removed = client.delete("/api/v1/tenants/me/logo", headers=other_tenant_auth_headers)
    assert removed.status_code == 200
    assert removed.json()["has_uploaded_logo"] is False


@pytest.mark.parametrize("filename", ["logo.svg", "logo.html", "logo.exe", "logo"])
def test_rejects_disallowed_logo_types(client, other_tenant_auth_headers, filename):
    # SVG especially: it is the obvious logo format and is also XML that
    # can carry script, served back to browsers.
    r = client.post(
        "/api/v1/tenants/me/logo",
        files={"file": (filename, io.BytesIO(_PNG), "image/png")},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 422
    assert ".svg" not in ALLOWED_LOGO_EXTENSIONS


def test_rejects_an_oversized_logo(client, other_tenant_auth_headers):
    oversized = b"\x00" * (MAX_LOGO_BYTES + 1024)
    r = client.post(
        "/api/v1/tenants/me/logo",
        files={"file": ("big.png", io.BytesIO(oversized), "image/png")},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 413


# Role gating for every route added this sprint — including these logo
# endpoints — lives in tests/test_rbac_matrix.py, which is this repo's
# single source of truth for who may call what.
