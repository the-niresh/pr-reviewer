"""Hosted pairing approval and the /dashboard landing (Runtime Task 2B).

GitHub cannot redirect to 127.0.0.1. ALLOWED_RETURN_TO_PATHS and the local onboarding sign-in URL
already send the user here after OAuth. This page is that landing: a signed-in user picks
repositories and approves a waiting pairing. The callback uses the OAuth token once, in memory,
then seals a LiveInstallationAssertion into the cookie. The token is discarded before the
response returns. The cookie carries github_user_id and the installation map, not a credential.

The approve route consumes that signed assertion. It never takes github_user_id as a parameter.
Installation id in the body is the dashboard selection, proved by verify_installation_access,
which remains the only construction site for VerifiedInstallationAccess.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from pr_reviewer.contracts.runner import PairingApproved, PairingDenied
from pr_reviewer.control_plane.github_auth import (
    AccessDenied,
    LiveInstallationAssertion,
    VerifiedGitHubUser,
)
from pr_reviewer.control_plane.github_oauth import (
    LIVE_SIGN_IN_COOKIE_NAME,
    HttpClient,
    read_live_sign_in,
    verify_installation_access,
)
from pr_reviewer.control_plane.pairing import approve_pairing

router = APIRouter(tags=["pairing-approval"])


class ApprovePairingBody(BaseModel):
    code: str = Field(min_length=1)
    installation_id: int
    repository_ids: list[int] = Field(default_factory=list)


def submit_pairing_approval(
    *,
    code: str,
    installation_id: int,
    repository_ids: Sequence[int],
    user: VerifiedGitHubUser | None = None,
    assertion: LiveInstallationAssertion | None = None,
    http_client: HttpClient | None = None,
) -> PairingApproved | PairingDenied | AccessDenied:
    access = verify_installation_access(
        user, installation_id, http_client=http_client, assertion=assertion
    )
    if isinstance(access, AccessDenied):
        return access
    return approve_pairing(code, access, repository_ids)


@router.get("/dashboard")
def dashboard_route(request: Request) -> HTMLResponse:
    assertion = read_live_sign_in(request.cookies.get(LIVE_SIGN_IN_COOKIE_NAME, ""))
    signed_in = assertion is not None
    identity = html.escape(str(assertion.github_user_id)) if assertion is not None else ""
    status = (
        f"<p>Signed in as GitHub user {identity}. Pick the repositories this runner may review, "
        "then approve the waiting pairing.</p>"
        if signed_in
        else (
            "<p>Sign in with GitHub to pick repositories and approve a waiting pairing. "
            "The local runner sent you here because GitHub cannot redirect to 127.0.0.1.</p>"
        )
    )
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>PR Reviewer dashboard</title></head>
<body>
  <h1>Approve pairing</h1>
  {status}
  <p>Repository selection happens on this hosted origin after GitHub sign-in.</p>
  <form id="approve">
    <label for="code">Pairing code</label>
    <input id="code" name="code" required>
    <label for="installation_id">Installation</label>
    <input id="installation_id" name="installation_id" required>
    <label for="repository_ids">Repository ids</label>
    <input id="repository_ids" name="repository_ids"
           placeholder="GitHub repository ids, comma separated">
    <button type="submit">Approve pairing</button>
  </form>
  <script>
    document.getElementById("approve").addEventListener("submit", async (event) => {{
      event.preventDefault();
      const form = event.target;
      const ids = form.repository_ids.value.split(",")
        .map((s) => Number(s.trim())).filter((n) => n);
      const response = await fetch("/api/pairing/approve", {{
        method: "POST",
        credentials: "same-origin",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          code: form.code.value,
          installation_id: Number(form.installation_id.value),
          repository_ids: ids,
        }}),
      }});
      const body = await response.text();
      document.getElementById("result").textContent = body;
    }});
  </script>
  <pre id="result"></pre>
</body>
</html>
"""
    )


@router.post("/api/pairing/approve")
def approve_pairing_route(body: ApprovePairingBody, request: Request) -> JSONResponse:
    assertion = read_live_sign_in(request.cookies.get(LIVE_SIGN_IN_COOKIE_NAME, ""))
    if assertion is None:
        return JSONResponse({"error": "missing_sign_in"}, status_code=401)

    result = submit_pairing_approval(
        code=body.code,
        assertion=assertion,
        installation_id=body.installation_id,
        repository_ids=body.repository_ids,
    )
    if isinstance(result, AccessDenied):
        response = JSONResponse({"error": result.reason}, status_code=403)
    elif isinstance(result, PairingDenied):
        response = JSONResponse({"reason": result.reason}, status_code=400)
    else:
        response = JSONResponse(
            {
                "approved": True,
                "installation_id": result.installation_id,
                "repository_ids": [str(item) for item in result.repository_ids],
            }
        )
    response.delete_cookie(LIVE_SIGN_IN_COOKIE_NAME, path="/")
    return response
