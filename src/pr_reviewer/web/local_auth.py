"""Loopback dashboard session and CSRF. No runner or hosted imports."""

from __future__ import annotations

import hashlib
import hmac
import secrets as secrets_lib

from fastapi import Request
from fastapi.responses import JSONResponse

SESSION_COOKIE = "pr_reviewer_dashboard_session"
CSRF_COOKIE = "pr_reviewer_csrf"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOOPBACK_UI_ORIGINS = ("http://127.0.0.1:3000",)


class DashboardBindError(RuntimeError):
    """The dashboard app cannot start or cannot accept the requested bind."""


def require_loopback_bind(host: str, session_secret: str) -> bytes:
    if host != "127.0.0.1":
        raise DashboardBindError(f"dashboard binds 127.0.0.1 only, not {host!r}")
    if not session_secret:
        raise DashboardBindError("a random local session secret is required")
    return session_secret.encode("utf-8")


def client_is_loopback(request: Request) -> bool:
    host = request.client.host if request.client is not None else ""
    return host in LOOPBACK_HOSTS


def sign(secret: bytes, token: str) -> str:
    digest = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{token}.{digest}"


def signed_value_matches(secret: bytes, cookie: str, token: str | None = None) -> bool:
    if "." not in cookie:
        return False
    raw, digest = cookie.rsplit(".", 1)
    expected = hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        return False
    if token is not None:
        return hmac.compare_digest(raw, token)
    return True


def session_is_valid(secret: bytes, request: Request) -> bool:
    cookie = request.cookies.get(SESSION_COOKIE, "")
    return bool(cookie) and signed_value_matches(secret, cookie)


def csrf_is_valid(secret: bytes, request: Request, header: str | None) -> bool:
    if not header:
        return False
    cookie = request.cookies.get(CSRF_COOKIE, "")
    return signed_value_matches(secret, cookie, header)


def new_session_response(secret: bytes) -> JSONResponse:
    session_token = secrets_lib.token_urlsafe(32)
    csrf_token = secrets_lib.token_urlsafe(32)
    response = JSONResponse({"csrf_token": csrf_token})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=sign(secret, session_token),
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=sign(secret, csrf_token),
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response
