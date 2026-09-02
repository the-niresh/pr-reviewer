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
from fastapi.responses import HTMLResponse, RedirectResponse

from pr_reviewer.config import get_settings
from pr_reviewer.control_plane.github_auth import ReturnToRejected, SignInDenied
from pr_reviewer.control_plane.github_oauth import (
    LIVE_SIGN_IN_COOKIE_NAME,
    STATE_TTL_SECONDS,
    begin_sign_in,
    capture_live_assertion,
    complete_sign_in,
    issue_live_sign_in,
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


# Installing the App sends the user here with a code and an installation_id but no
# state, because that redirect starts at GitHub rather than at our /sign-in. State is
# CSRF protection and is not optional, so the code is still refused. What changes is
# that the person sees a sentence and a link instead of a raw validation dump. The
# durable fix is the App's Setup URL pointing at /sign-in; this is the safety net for
# anyone who reaches the callback cold.
_NO_STATE_PAGE = """<!doctype html>
<title>Start sign-in again</title>
<body style="font:16px/1.6 system-ui;max-width:34rem;margin:12vh auto;padding:0 1.5rem">
<h1 style="font-size:1.4rem">Start sign-in from the beginning</h1>
<p>This link is missing the one-time value that proves the sign-in started here, so it
was not accepted. That is expected if you arrived straight from installing the App.</p>
<p><a href="/api/auth/github/sign-in?return_to=/dashboard">Sign in with GitHub</a></p>
</body>"""


# response_model=None: the union return is a deliberate two-outcome signature, and
# FastAPI would otherwise try to build a Pydantic model from a Response type.
@router.get("/callback", response_model=None)
def callback_route(
    code: str, request: Request, state: str | None = None
) -> RedirectResponse | HTMLResponse:
    if state is None:
        return HTMLResponse(_NO_STATE_PAGE, status_code=400)
    binding_secret = request.cookies.get(BINDING_SECRET_COOKIE_NAME, "")
    result = complete_sign_in(code, state, binding_secret)
    if isinstance(result, SignInDenied):
        raise HTTPException(status_code=401, detail=result.reason)

    assertion = capture_live_assertion(result)
    response = RedirectResponse(url=result.return_to, status_code=302)
    response.delete_cookie(BINDING_SECRET_COOKIE_NAME, path=CALLBACK_PATH)
    response.set_cookie(
        key=LIVE_SIGN_IN_COOKIE_NAME,
        value=issue_live_sign_in(assertion),
        max_age=STATE_TTL_SECONDS,
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response
