import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import User

TEST_EMAIL = "pytest-auth-test@example.invalid"
TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture()
def test_user():
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == TEST_EMAIL))
        db.commit()
        user = auth_service.create_user(
            db, name="Pytest User", email=TEST_EMAIL, password=TEST_PASSWORD, role="Staff"
        )
        yield user
    finally:
        db.execute(delete(User).where(User.email == TEST_EMAIL))
        db.commit()
        db.close()


def test_login_success(client, test_user):
    r = client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == TEST_EMAIL
    assert body["access_token"]


def test_login_wrong_password(client, test_user):
    r = client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": "wrong"}
    )
    assert r.status_code == 401


def test_login_unknown_email(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.invalid", "password": "x"},
    )
    assert r.status_code == 401


def test_me_with_valid_token(client, test_user):
    login = client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    token = login.json()["access_token"]

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == TEST_EMAIL


def test_me_without_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_with_garbage_token(client):
    r = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert r.status_code == 401
