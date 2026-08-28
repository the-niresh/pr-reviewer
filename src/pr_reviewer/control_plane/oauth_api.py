"""HTTP surface for hosted GitHub sign-in (Runtime Task 2A).

The binding_secret cookie is the whole reason this task exists as more than a state parameter:
Lax, not Strict, because Strict is not sent on the top-level navigation back from github.com to
this callback, and a cookie that silently never arrives makes every real sign-in look identical to
an attack. Scoped to the callback path only, so nothing else on this host ever sees it, and its
Max-Age matches the state's own expiry so the cookie cannot outlive the row it authenticates.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from pr_reviewer.config import get_settings
from pr_reviewer.control_plane.github_auth import ReturnToRejected, SignInDenied
from pr_reviewer.control_plane.github_oauth import (
    STATE_TTL_SECONDS,
    begin_sign_in,
    complete_sign_in,
)

router = APIRouter(prefix="/api/auth/github", tags=["github-oauth"])

CALLBACK_PATH = "/api/auth/github/callback"
BINDING_SECRET_COOKIE_NAME = "gh_oauth_binding"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


@router.get("/sign-in")
def begin_sign_in_route(return_to: str, request: Request) -> RedirectResponse:
    challenge = begin_sign_in(return_to)
    if isinstance(challenge, ReturnToRejected):
        raise HTTPException(status_code=400, detail=challenge.reason)

    redirect_uri = str(request.base_url).rstrip("/") + CALLBACK_PATH
    query = urlencode(
        {
            "client_id": get_settings().github_oauth_client_id,
            "state": challenge.state,
            "redirect_uri": redirect_uri,
        }
    )
    response = RedirectResponse(url=f"{GITHUB_AUTHORIZE_URL}?{query}", status_code=302)
    response.set_cookie(
        key=BINDING_SECRET_COOKIE_NAME,
        value=challenge.binding_secret,
        max_age=STATE_TTL_SECONDS,
        path=CALLBACK_PATH,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.get("/callback")
def callback_route(code: str, state: str, request: Request) -> RedirectResponse:
    binding_secret = request.cookies.get(BINDING_SECRET_COOKIE_NAME, "")
    result = complete_sign_in(code, state, binding_secret)
    if isinstance(result, SignInDenied):
        raise HTTPException(status_code=401, detail=result.reason)

    response = RedirectResponse(url=result.return_to, status_code=302)
    response.delete_cookie(BINDING_SECRET_COOKIE_NAME, path=CALLBACK_PATH)
    return response
