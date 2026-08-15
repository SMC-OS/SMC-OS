import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Project, Quote

TEST_CUSTOMER_NAME = "Pytest Dashboard Customer"
TEST_PROJECT_NAME = "Pytest Dashboard Project"
TEST_QUOTE_POSTCODE = "PYTESTDASH1"


def _cleanup():
    db = SessionLocal()
    try:
        db.execute(delete(Quote).where(Quote.postcode == TEST_QUOTE_POSTCODE))
        db.execute(delete(Project).where(Project.name == TEST_PROJECT_NAME))
        db.execute(delete(Customer).where(Customer.name == TEST_CUSTOMER_NAME))
        db.execute(
            delete(ActivityLog).where(
                ActivityLog.description.in_([TEST_CUSTOMER_NAME, TEST_PROJECT_NAME])
                | ActivityLog.description.like("Pytest Dashboard Quote%")
            )
        )
        db.commit()
    finally:
        db.close()


def test_dashboard_requires_auth(client):
    # Sprint 012 (ADR-029): /dashboard had no auth at all before this sprint.
    assert client.get("/api/v1/dashboard").status_code == 401


def test_dashboard_reflects_real_data(client, auth_headers):
    _cleanup()
    try:
        before = client.get("/api/v1/dashboard", headers=auth_headers).json()

        client.post(
            "/api/v1/customers", json={"name": TEST_CUSTOMER_NAME}, headers=auth_headers
        )
        client.post(
            "/api/v1/projects", json={"name": TEST_PROJECT_NAME}, headers=auth_headers
        )
        quote = client.post(
            "/api/v1/quote",
            json={
                "customer": "Pytest Dashboard Quote",
                "material": "calacatta gold",
                "thickness": "20mm",
                "kitchen_length": 2.0,
                "postcode": TEST_QUOTE_POSTCODE,
            },
            headers=auth_headers,
        ).json()

        after = client.get("/api/v1/dashboard", headers=auth_headers).json()

        assert after["customers"] == before["customers"] + 1
        assert after["projects"] == before["projects"] + 1
        assert after["quotes_today"] == before["quotes_today"] + 1
        assert after["revenue"] == pytest.approx(before["revenue"] + quote["total"])
    finally:
        _cleanup()


def test_dashboard_counts_are_tenant_scoped(
    client, auth_headers, other_tenant_auth_headers
):
    _cleanup()
    try:
        before_other = client.get(
            "/api/v1/dashboard", headers=other_tenant_auth_headers
        ).json()

        client.post(
            "/api/v1/customers", json={"name": TEST_CUSTOMER_NAME}, headers=auth_headers
        )
        client.post(
            "/api/v1/projects", json={"name": TEST_PROJECT_NAME}, headers=auth_headers
        )
        client.post(
            "/api/v1/quote",
            json={
                "customer": "Pytest Dashboard Quote",
                "material": "calacatta gold",
                "thickness": "20mm",
                "kitchen_length": 2.0,
                "postcode": TEST_QUOTE_POSTCODE,
            },
            headers=auth_headers,
        )

        # None of Tenant A's newly created records move Tenant B's counts.
        after_other = client.get(
            "/api/v1/dashboard", headers=other_tenant_auth_headers
        ).json()
        assert after_other == before_other
    finally:
        _cleanup()
