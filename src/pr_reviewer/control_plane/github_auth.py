"""Contracts for hosted GitHub sign-in (Runtime Task 2A).

These live in control_plane/, not contracts/. Phase 1 section 4 makes contracts/ shared
vocabulary that everything, including the runner, is allowed to import; SignInChallenge and
VerifiedGitHubUser carry values that must never reach a runner (a binding secret, and the user's
own live GitHub OAuth token), so they belong on the hosted-internal side of that line instead.
RunnerCredential stays in contracts/ even though it also holds a plaintext secret, because hosted
mints it and the runner is meant to receive it; crossing the boundary is its whole purpose. The
other three types here carry no secret and have no boundary meaning either, but moved with the
rest of the file rather than being split out on their own.

See control_plane/github_oauth.py for the functions that produce and consume these.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

# A caller presenting a state and a binding_secret is not authorised to learn whether the state
# never existed, already expired, was already consumed, or was issued to a different binding
# secret: telling those apart would let a login-CSRF attacker confirm a state is "real" before
# also holding the one value (the binding_secret cookie) that never travels through the browser.
# So all four collapse into one reason. Same rule as PairingDenialReason in contracts/runner.py.
SignInDenialReason = Literal["invalid_or_expired_state"]

# "No such installation" and "installation exists but you do not control it" are the same
# reason for the same tenancy-leak reason authorize_repository and approve_pairing already
# follow: telling them apart requires a query scoped only by installation_id, with no regard to
# who is asking, which is itself a cross-tenant read.
AccessDenialReason = Literal["installation_not_controlled"]

ReturnToDenialReason = Literal["return_to_not_allowed"]


class SignInChallenge(BaseModel):
    """Returned by begin_sign_in. state goes in the GitHub authorize URL query string, where an
    attacker can see and replay it. binding_secret goes in an HttpOnly cookie, which never
    appears in a URL and is not sent on the cross-site navigation an attacker would use to plant
    their own state in a victim's browser. Losing either one on its own is not enough to
    complete the sign-in; only the pair, matched atomically, is.
    """

    model_config = ConfigDict(frozen=True)

    state: str = Field(min_length=1)
    binding_secret: str = Field(min_length=1)
    expires_at: datetime


class ReturnToRejected(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: ReturnToDenialReason


class VerifiedGitHubUser(BaseModel):
    """The result of a completed GitHub sign-in.

    access_token is the user's own OAuth token, live only long enough to call
    capture_live_assertion once (one /user/installations round-trip). It is never written to the
    database, never logged, never sealed into a cookie, and never sent to a runner: see
    docs/phases/phase-2-security-design-gate.md section 7, where it is deliberately absent from
    the secret lifecycle table because it must never live long enough to have one. SecretStr
    keeps it out of reprs and str() by accident; callers still have to ask for it explicitly
    with get_secret_value().
    """

    model_config = ConfigDict(frozen=True)

    github_user_id: int
    login: str = Field(min_length=1)
    access_token: SecretStr
    return_to: str


class LiveInstallationAssertion(BaseModel):
    """Verified GitHub installations captured at sign-in, sealed into the live-sign-in cookie.

    This is the outcome of one /user/installations call, not the OAuth token used to make it.
    github_user_id and the installation/repository map are data the user already sees on the
    dashboard. expires_at is the assertion's own expiry: HMAC authenticity is not a substitute
    for freshness. login is the GitHub username from the same sign-in response; it is optional
    (defaults to None) purely so a cookie issued before this field existed still decodes -- a
    fresh sign-in always sets it.
    """

    model_config = ConfigDict(frozen=True)

    github_user_id: int
    login: str | None = None
    installations: dict[int, dict[int, str]]
    expires_at: int


class SignInDenied(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: SignInDenialReason


class AccessDenied(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: AccessDenialReason
