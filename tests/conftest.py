import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.database.database import SessionLocal
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db():
    """A plain DB session for tests that call service-layer code directly
    (not through the HTTP client) — reusable by any module's tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def auth_headers(client):
    """Bearer header for the seeded owner — reusable by any module's tests
    that need to call an authenticated route (customers, and beyond)."""
    r = client.post(
        "/api/v1/auth/login",
        json={"email": settings.seed_admin_email, "password": settings.seed_admin_password},
    )
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
