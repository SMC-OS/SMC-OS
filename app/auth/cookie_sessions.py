"""Browser-only HttpOnly sessions. Explicit API bearer clients stay supported."""
import secrets
from fastapi import HTTPException, Request, Response
from app.auth.models import TokenResponse
from app.core.config import AppEnvironment, settings

SESSION_MODE_HEADER = "X-Geocore-Session"
CSRF_HEADER = "X-CSRF-Token"


def session_cookie_name() -> str:
    return "__Host-geocore_session" if settings.app_env is AppEnvironment.PRODUCTION else "geocore_session"


def csrf_cookie_name() -> str:
    return "__Host-geocore_csrf" if settings.app_env is AppEnvironment.PRODUCTION else "geocore_csrf"


def validate_origin(request: Request) -> None:
    if request.headers.get("Origin") not in settings.cors_allowed_origins:
        raise HTTPException(status_code=403, detail="Browser session origin is not allowed")


def validate_browser_session_request(request: Request) -> None:
    if request.headers.get(SESSION_MODE_HEADER) == "cookie":
        validate_origin(request)


def validate_cookie_write(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    validate_origin(request)
    cookie = request.cookies.get(csrf_cookie_name())
    supplied = request.headers.get(CSRF_HEADER)
    if not cookie or not supplied or not secrets.compare_digest(cookie.encode("utf-8"), supplied.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Browser session CSRF check failed")


def _set_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(name, value, max_age=settings.jwt_expire_minutes * 60,
        httponly=True, secure=settings.app_env is AppEnvironment.PRODUCTION,
        samesite="lax", path="/")


def establish_browser_session(response: Response, token: str) -> None:
    _set_cookie(response, session_cookie_name(), token)
    csrf = secrets.token_urlsafe(32)
    _set_cookie(response, csrf_cookie_name(), csrf)
    response.headers[CSRF_HEADER] = csrf
    response.headers["Cache-Control"] = "no-store"


def session_token_response(request: Request, response: Response, token: str, user) -> TokenResponse:
    if request.headers.get(SESSION_MODE_HEADER) == "cookie":
        establish_browser_session(response, token)
        return TokenResponse(token_type="cookie", user=user)
    return TokenResponse(access_token=token, user=user)


def expose_session_csrf(request: Request, response: Response) -> None:
    if request.cookies.get(session_cookie_name()):
        csrf = request.cookies.get(csrf_cookie_name()) or secrets.token_urlsafe(32)
        if not request.cookies.get(csrf_cookie_name()):
            _set_cookie(response, csrf_cookie_name(), csrf)
        response.headers[CSRF_HEADER] = csrf
        response.headers["Cache-Control"] = "no-store"


def clear_browser_session(response: Response) -> None:
    for name in [session_cookie_name(), csrf_cookie_name()]:
        response.delete_cookie(name, path="/", secure=settings.app_env is AppEnvironment.PRODUCTION, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
