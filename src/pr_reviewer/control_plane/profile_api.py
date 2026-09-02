"""Task 33.C8: the signed-in viewer's own GitHub identity, for /dashboard/profile.

Carries nothing GitHub does not already show the user on every page of the installation
itself: their numeric id and login. No email, no access token -- that never survives past
capture_live_assertion in the first place (see github_auth.VerifiedGitHubUser).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from pr_reviewer.control_plane.github_oauth import LIVE_SIGN_IN_COOKIE_NAME, read_live_sign_in

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    github_user_id: int
    login: str | None


@router.get("", response_model=ProfileResponse)
def get_profile_route(request: Request) -> ProfileResponse:
    """login is None only for a session sealed before that field existed (see
    LiveInstallationAssertion.login) -- signing in again fills it in.
    """
    cookie = request.cookies.get(LIVE_SIGN_IN_COOKIE_NAME, "")
    assertion = read_live_sign_in(cookie)
    if assertion is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return ProfileResponse(github_user_id=assertion.github_user_id, login=assertion.login)
