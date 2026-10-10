"""SEC001: browser credentials are HttpOnly, CSRF protected and revocable."""
import uuid
from fastapi import Response
from app.core.config import settings

ORIGIN = "http://localhost:3000"
BROWSER_HEADERS = {"Origin": ORIGIN, "X-Geocore-Session": "cookie"}


def browser_login(client):
    response = client.post("/api/v1/auth/login", headers=BROWSER_HEADERS,
        json={"email": settings.seed_admin_email, "password": settings.seed_admin_password})
    assert response.status_code == 200, response.text
    return response


def test_browser_login_does_not_expose_a_bearer_token_and_restores_session_after_refresh(client):
    response = browser_login(client)
    assert "access_token" not in response.json()
    assert response.json()["token_type"] == "cookie"
    cookies = response.headers.get_list("set-cookie")
    assert any("HttpOnly" in cookie and "SameSite=lax" in cookie for cookie in cookies)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.headers.get("X-CSRF-Token")
    assert me.json()["email"] == settings.seed_admin_email


def test_browser_cookie_login_rejects_untrusted_or_absent_origin(client):
    for origin in [None, "https://untrusted.example.invalid"]:
        headers = {"X-Geocore-Session": "cookie"}
        if origin:
            headers["Origin"] = origin
        response = client.post("/api/v1/auth/login", headers=headers,
            json={"email": settings.seed_admin_email, "password": settings.seed_admin_password})
        assert response.status_code == 403
        assert not response.headers.get_list("set-cookie")


def test_cookie_writes_require_both_trusted_origin_and_matching_csrf(client):
    browser_login(client)
    csrf = client.get("/api/v1/auth/me").headers["X-CSRF-Token"]
    for headers in [{"Origin": ORIGIN}, {"Origin": ORIGIN, "X-CSRF-Token": "wrong"}, {"Origin": "https://untrusted.example.invalid", "X-CSRF-Token": csrf}]:
        response = client.post("/api/v1/customers", headers=headers, json={"name": "Synthetic CSRF rejected"})
        assert response.status_code == 403
    response = client.post("/api/v1/customers", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}, json={"name": "Synthetic cookie customer " + uuid.uuid4().hex})
    assert response.status_code == 201
    from sqlalchemy import delete
    from app.database.database import SessionLocal
    from app.database.models import Customer
    with SessionLocal() as db:
        db.execute(delete(Customer).where(Customer.id == uuid.UUID(response.json()["id"])))
        db.commit()


def test_logout_revokes_the_current_session_and_clears_cookies(client):
    browser_login(client)
    csrf = client.get("/api/v1/auth/me").headers["X-CSRF-Token"]
    from app.auth.cookie_sessions import session_cookie_name
    token = client.cookies.get(session_cookie_name())
    response = client.post("/api/v1/auth/logout", headers={**BROWSER_HEADERS, "X-CSRF-Token": csrf})
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_explicit_api_bearer_clients_remain_supported_without_browser_cookies(client):
    response = client.post("/api/v1/auth/login", json={"email": settings.seed_admin_email, "password": settings.seed_admin_password})
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert not response.headers.get_list("set-cookie")
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + response.json()["access_token"]}).status_code == 200


def test_production_cookies_are_host_only_secure_httponly_and_lax(monkeypatch):
    from app.auth.cookie_sessions import establish_browser_session
    from app.core.config import AppEnvironment
    monkeypatch.setattr(settings, "app_env", AppEnvironment.PRODUCTION)
    response = Response()
    establish_browser_session(response, "synthetic-test-token")
    cookies = response.headers.getlist("set-cookie")
    assert len(cookies) == 2
    for cookie in cookies:
        assert cookie.startswith("__Host-")
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
        assert "Domain=" not in cookie


def test_cookie_quote_creation_keeps_workspace_ownership_and_csrf(client):
    browser_login(client)
    me = client.get("/api/v1/auth/me")
    headers = {"Origin": ORIGIN, "X-CSRF-Token": me.headers["X-CSRF-Token"]}
    payload = {"customer": "Synthetic cookie quote", "material": "Calacatta Gold", "thickness": "20mm", "kitchen_length": 3, "postcode": "QA-cookie"}
    rejected = client.post("/api/v1/quote", headers={"Origin": ORIGIN}, json=payload)
    assert rejected.status_code == 403
    created = client.post("/api/v1/quote", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    quote_id = created.json()["id"]
    try:
        saved = client.get(f"/api/v1/quotes/{quote_id}")
        assert saved.status_code == 200
        assert saved.json()["id"] == quote_id
    finally:
        from sqlalchemy import delete
        from app.database.database import SessionLocal
        from app.database.models import Quote, QuoteItem
        with SessionLocal() as db:
            db.execute(delete(QuoteItem).where(QuoteItem.quote_id == uuid.UUID(quote_id)))
            db.execute(delete(Quote).where(Quote.id == uuid.UUID(quote_id)))
            db.commit()


def test_cookie_password_change_rotates_session_and_revokes_old_credentials(client, other_tenant_auth_headers):
    from conftest import OTHER_TENANT_EMAIL, OTHER_TENANT_PASSWORD
    from app.auth.cookie_sessions import session_cookie_name
    signed_in = client.post("/api/v1/auth/login", headers=BROWSER_HEADERS,
        json={"email": OTHER_TENANT_EMAIL, "password": OTHER_TENANT_PASSWORD})
    assert signed_in.status_code == 200
    old_cookie = client.cookies.get(session_cookie_name())
    changed = client.post("/api/v1/auth/password/change",
        headers={**BROWSER_HEADERS, "X-CSRF-Token": signed_in.headers["X-CSRF-Token"]},
        json={"current_password": OTHER_TENANT_PASSWORD, "new_password": "Synthetic-New-Password-2026!"})
    assert changed.status_code == 200, changed.text
    assert "access_token" not in changed.json()
    assert client.cookies.get(session_cookie_name()) != old_cookie
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_cookie}"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers=other_tenant_auth_headers).status_code == 401
    assert client.post("/api/v1/auth/logout", headers={**BROWSER_HEADERS, "X-CSRF-Token": changed.headers["X-CSRF-Token"]}).status_code == 204


def test_cookie_csrf_unicode_input_is_rejected_without_server_error():
    import pytest
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.auth.cookie_sessions import validate_cookie_write
    request = Request({"type": "http", "method": "POST", "path": "/",
        "headers": [(b"origin", ORIGIN.encode()), (b"cookie", b"geocore_csrf=expected"),
                    (b"x-csrf-token", "unexpected-\u00e9".encode("latin1"))]})
    with pytest.raises(HTTPException) as error:
        validate_cookie_write(request)
    assert error.value.status_code == 403
