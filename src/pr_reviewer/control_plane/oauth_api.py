"""HTTP surface for hosted GitHub sign-in (Runtime Task 2A).

The binding_secret cookie is the whole reason this task exists as more than a state parameter:
Lax, not Strict, because Strict is not sent on the top-level navigation back from github.com to
this callback, and a cookie that silently never arrives makes every real sign-in look identical to
an attack. Scoped to the callback path only, so nothing else on this host ever sees it, and its
Max-Age matches the state's own expiry so the cookie cannot outlive the row it authenticates.
"""

from __future__ import annotations

import html
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from pr_reviewer.config import get_settings
from pr_reviewer.contracts.runner import PairingApproved, PairingDenied
from pr_reviewer.control_plane.github_auth import (
    AccessDenied,
    LiveInstallationAssertion,
    ReturnToRejected,
    SignInDenied,
    VerifiedGitHubUser,
)
from pr_reviewer.control_plane.github_oauth import (
    LIVE_SIGN_IN_COOKIE_NAME,
    STATE_TTL_SECONDS,
    begin_sign_in,
    capture_live_assertion,
    complete_sign_in,
    issue_live_sign_in,
    verify_installation_access,
)
from pr_reviewer.control_plane.pairing import approve_pairing_by_hash
from pr_reviewer.control_plane.repository_policy import hash_runner_credential

router = APIRouter(prefix="/api/auth/github", tags=["github-oauth"])

CALLBACK_PATH = "/api/auth/github/callback"
BINDING_SECRET_COOKIE_NAME = "gh_oauth_binding"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


@router.get("/sign-in")
def begin_sign_in_route(
    return_to: str, request: Request, pairing_code: str | None = None
) -> RedirectResponse:
    # Hashed here, at the door: nothing past this point, including the oauth_states row itself,
    # ever holds the plaintext pairing code the TUI put in this link.
    pairing_code_hash = hash_runner_credential(pairing_code) if pairing_code else None
    challenge = begin_sign_in(return_to, pairing_code_hash=pairing_code_hash)
    if isinstance(challenge, ReturnToRejected):
        raise HTTPException(status_code=400, detail=challenge.reason)

    # request.base_url reports http behind Traefik, which terminates TLS and forwards
    # plain HTTP, so GitHub would receive an http redirect_uri that does not match the
    # App's https callback. The hosted origin is the authoritative answer, it is
    # validated as https and non-loopback, and unlike a Host header it cannot be
    # spoofed by the caller.
    origin = get_settings().hosted_origin
    if not origin.startswith("https://"):
        raise HTTPException(status_code=500, detail="hosted_origin_not_configured")
    redirect_uri = origin + CALLBACK_PATH
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


@router.post("/sign-out")
def sign_out_route() -> JSONResponse:
    """Deletes the live sign-in cookie. There is no server-side session to invalidate --
    LIVE_SIGN_IN_COOKIE_NAME is the whole session, sealed by issue_live_sign_in -- so
    discarding it here is the entire logout.
    """
    response = JSONResponse({"signed_out": True})
    response.delete_cookie(LIVE_SIGN_IN_COOKIE_NAME, path="/")
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


# Every reason PairingDenialReason can carry, in words a person waiting in a browser
# understands, without repeating the security reasoning collapsed into "invalid_or_expired_code"
# (see github_auth.PairingDenialReason) -- that reasoning is for callers guessing codes, not for
# a person reading a page after a real attempt.
_PAIRING_DENIED_MESSAGES: dict[str, str] = {
    "invalid_or_expired_code": (
        "The pairing code your terminal is waiting on has expired, was already used, or "
        "was never issued. Go back to the terminal and press Sign in to get a new link."
    ),
    "unknown_installation": (
        "This GitHub App installation is not known here yet. Install the App on GitHub, "
        "then go back to the terminal and press Sign in to get a new link."
    ),
    "revoked_installation": (
        "This GitHub App installation was revoked. Reinstall the App, then go back to the "
        "terminal and press Sign in to get a new link."
    ),
    "repository_not_in_installation": (
        "One of the repositories this pairing needs is not covered by this GitHub App "
        "installation. Go back to the terminal and press Sign in to get a new link."
    ),
}


def _pairing_denied_page(reason: str) -> HTMLResponse:
    message = html.escape(
        _PAIRING_DENIED_MESSAGES.get(
            reason,
            "Sign-in worked, but pairing did not complete. Go back to the terminal and "
            "press Sign in to get a new link.",
        )
    )
    return HTMLResponse(
        f"""<!doctype html>
<title>Pairing not completed</title>
<body style="font:16px/1.6 system-ui;max-width:34rem;margin:12vh auto;padding:0 1.5rem">
<h1 style="font-size:1.4rem">Sign-in worked, but pairing did not complete</h1>
<p>{message}</p>
</body>"""
    )


def _pairing_approved_page(return_to: str) -> HTMLResponse:
    # Meta-refresh, not JS: this must still redirect even under a strict CSP with no
    # script-src for inline scripts, and the person only needs to see this once, not
    # interact with it.
    destination = html.escape(return_to, quote=True)
    return HTMLResponse(
        f"""<!doctype html>
<title>Terminal signed in</title>
<meta http-equiv="refresh" content="5;url={destination}">
<body style="font:16px/1.6 system-ui;max-width:34rem;margin:12vh auto;padding:0 1.5rem">
<h1 style="font-size:1.4rem">Your terminal is signed in</h1>
<p>The runner waiting in your terminal is now paired with this GitHub App
installation. You can go back to it, or wait a moment to continue here.</p>
<p><a href="{destination}">Continue now</a></p>
</body>"""
    )


def _auto_approve_waiting_pairing(
    pairing_code_hash: str,
    user: VerifiedGitHubUser,
    assertion: LiveInstallationAssertion,
) -> PairingApproved | PairingDenied | None:
    """Link the terminal's waiting pairing to the installation this sign-in just proved control
    of, the same way the manual /dashboard approval flow already does (control_plane/pairing.py's
    approve_pairing). Returns None, rather than a denial, when there is nothing safe to decide
    automatically: with zero installations there is nothing to grant, and with more than one,
    guessing which the terminal should get would be a silent cross-account grant. Either way the
    existing manual approval on /dashboard still works; this is strictly an added shortcut for
    the common single-installation case.
    """
    if len(assertion.installations) != 1:
        return None
    installation_id = next(iter(assertion.installations))
    access = verify_installation_access(user, installation_id, assertion=assertion)
    if isinstance(access, AccessDenied):
        return None
    return approve_pairing_by_hash(pairing_code_hash, access, list(access.repositories))


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
    user, pairing_code_hash = result

    assertion = capture_live_assertion(user)

    response: RedirectResponse | HTMLResponse
    if pairing_code_hash is not None:
        outcome = _auto_approve_waiting_pairing(pairing_code_hash, user, assertion)
        if isinstance(outcome, PairingDenied):
            response = _pairing_denied_page(outcome.reason)
        elif isinstance(outcome, PairingApproved):
            # A person who just watched a "sign in with GitHub" button turn into a
            # 302 with no other feedback has no way to tell the terminal actually
            # received anything -- this is that confirmation, not just a redirect.
            response = _pairing_approved_page(user.return_to)
        else:
            response = RedirectResponse(url=user.return_to, status_code=302)
    else:
        response = RedirectResponse(url=user.return_to, status_code=302)

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
