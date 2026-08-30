"""Hosted GitHub sign-in (Runtime Task 2A).

This is what supplies the one real constructor for VerifiedInstallationAccess; Task 2 built
approve_pairing to take that object as an argument, and shipped only a test-only builder for it.

Every state-validation denial below returns before any GitHub network call is made: state is CSRF
protection, and a caller presenting a state and a binding_secret is not authorised to learn
whether that state never existed, already expired, was already consumed, or was issued for a
different binding_secret. All of those collapse into invalid_or_expired_state (see
github_auth.SignInDenialReason). Consuming the row is one atomic UPDATE ... WHERE ... RETURNING,
not a lookup followed by a separate write, so a state cannot be read as valid and then lost to a
concurrent completion before it is marked consumed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from typing import Protocol

import httpx
from pydantic import SecretStr

from pr_reviewer.config import get_settings
from pr_reviewer.contracts.runner import VerifiedInstallationAccess
from pr_reviewer.control_plane.github_auth import (
    AccessDenied,
    LiveInstallationAssertion,
    ReturnToRejected,
    SignInChallenge,
    SignInDenied,
    VerifiedGitHubUser,
)
from pr_reviewer.control_plane.repository_policy import hash_runner_credential
from pr_reviewer.db.client import connection

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_INSTALLATIONS_URL = "https://api.github.com/user/installations"

# Matches pairing_codes' ten-minute window: long enough for a human to actually authorize on
# GitHub's consent screen, short enough that a leaked, unconsumed state is not useful for long.
STATE_TTL_SECONDS = 600

# return_to is attacker-influenceable input arriving on the sign-in request itself. Validating it
# against a fixed allowlist of our own known paths, before it is ever written to oauth_states,
# means the value the callback later redirects to was never taken on anyone's word: an
# unvalidated return_to on an OAuth callback is an open redirect, and an open redirect here is a
# code-leak path. This list is expected to grow as real post-sign-in destinations are built.
ALLOWED_RETURN_TO_PATHS = frozenset({"/dashboard"})
LIVE_SIGN_IN_COOKIE_NAME = "gh_live_sign_in"


class HttpClient(Protocol):
    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response: ...

    def post(
        self, url: str, *, headers: dict[str, str], data: dict[str, str], timeout: float
    ) -> httpx.Response: ...


def begin_sign_in(return_to: str) -> SignInChallenge | ReturnToRejected:
    if return_to not in ALLOWED_RETURN_TO_PATHS:
        return ReturnToRejected(reason="return_to_not_allowed")

    state = secrets.token_urlsafe(32)
    binding_secret = secrets.token_urlsafe(32)

    with connection() as conn:
        row = conn.execute(
            """
            insert into oauth_states (state_hash, binding_hash, return_to)
            values (%s, %s, %s)
            returning created_at
            """,
            (
                hash_runner_credential(state),
                hash_runner_credential(binding_secret),
                return_to,
            ),
        ).fetchone()
    assert row is not None

    expires_at = row["created_at"] + timedelta(seconds=STATE_TTL_SECONDS)
    return SignInChallenge(state=state, binding_secret=binding_secret, expires_at=expires_at)


def complete_sign_in(
    code: str,
    state: str,
    binding_secret: str,
    *,
    http_client: HttpClient | None = None,
) -> VerifiedGitHubUser | SignInDenied:
    with connection() as conn, conn.transaction():
        # One statement: an unconsumed, unexpired row matching BOTH hashes, marked consumed in
        # the same breath it is read. There is no window between "this looked valid" and "this is
        # now spent" for a concurrent request to slip through, and no way to learn a state was
        # real without also presenting the binding_secret that proves it is yours.
        row = conn.execute(
            """
            update oauth_states
            set consumed_at = now()
            where state_hash = %s
              and binding_hash = %s
              and consumed_at is null
              and created_at > now() - interval '10 minutes'
            returning return_to
            """,
            (hash_runner_credential(state), hash_runner_credential(binding_secret)),
        ).fetchone()
    if row is None:
        return SignInDenied(reason="invalid_or_expired_state")
    return_to = str(row["return_to"])

    client = http_client or httpx.Client()
    settings = get_settings()

    token_response = client.post(
        GITHUB_TOKEN_URL,
        headers={"accept": "application/json"},
        data={
            "client_id": settings.github_oauth_client_id,
            "client_secret": settings.github_oauth_client_secret,
            "code": code,
        },
        timeout=10.0,
    )
    token_response.raise_for_status()
    access_token = str(token_response.json()["access_token"])

    user_response = client.get(
        GITHUB_USER_URL,
        headers={
            "authorization": f"Bearer {access_token}",
            "accept": "application/vnd.github+json",
        },
        timeout=10.0,
    )
    user_response.raise_for_status()
    user_payload = user_response.json()

    return VerifiedGitHubUser(
        github_user_id=int(user_payload["id"]),
        login=str(user_payload["login"]),
        access_token=SecretStr(access_token),
        return_to=return_to,
    )


def capture_live_assertion(
    user: VerifiedGitHubUser,
    *,
    http_client: HttpClient | None = None,
) -> LiveInstallationAssertion:
    """Call /user/installations once, then drop the token. The returned assertion is the outcome."""

    client = http_client or httpx.Client()
    headers = {
        "authorization": f"Bearer {user.access_token.get_secret_value()}",
        "accept": "application/vnd.github+json",
    }
    installations_response = client.get(GITHUB_INSTALLATIONS_URL, headers=headers, timeout=10.0)
    installations_response.raise_for_status()
    installations: dict[int, dict[int, str]] = {}
    for installation in installations_response.json().get("installations", []):
        installation_id = int(installation["id"])
        repositories_response = client.get(
            f"{GITHUB_INSTALLATIONS_URL}/{installation_id}/repositories",
            headers=headers,
            timeout=10.0,
        )
        repositories_response.raise_for_status()
        installations[installation_id] = {
            int(repository["id"]): str(repository["name"])
            for repository in repositories_response.json().get("repositories", [])
        }
    return LiveInstallationAssertion(
        github_user_id=user.github_user_id,
        installations=installations,
        expires_at=int(time.time()) + STATE_TTL_SECONDS,
    )


def verify_installation_access(
    user: VerifiedGitHubUser | None,
    installation_id: int,
    *,
    http_client: HttpClient | None = None,
    assertion: LiveInstallationAssertion | None = None,
) -> VerifiedInstallationAccess | AccessDenied:
    """The one construction site for VerifiedInstallationAccess in src/.

    Control is proven either by a live GitHub /user/installations call with the user's own OAuth
    token, or by a LiveInstallationAssertion captured from that same call at sign-in. There is
    deliberately no installation-ownership table, because GitHub is the authoritative source and a
    local copy would go stale the moment an installation is transferred or removed there.
    """
    github_user_id: int
    repositories: dict[int, str]
    if assertion is not None:
        if assertion.expires_at <= int(time.time()):
            return AccessDenied(reason="installation_not_controlled")
        matched = assertion.installations.get(installation_id)
        if matched is None:
            return AccessDenied(reason="installation_not_controlled")
        github_user_id = assertion.github_user_id
        repositories = matched
    elif user is not None:
        client = http_client or httpx.Client()
        headers = {
            "authorization": f"Bearer {user.access_token.get_secret_value()}",
            "accept": "application/vnd.github+json",
        }

        installations_response = client.get(GITHUB_INSTALLATIONS_URL, headers=headers, timeout=10.0)
        installations_response.raise_for_status()
        controlled_installation_ids = {
            int(installation["id"])
            for installation in installations_response.json().get("installations", [])
        }
        if installation_id not in controlled_installation_ids:
            return AccessDenied(reason="installation_not_controlled")

        repositories_response = client.get(
            f"{GITHUB_INSTALLATIONS_URL}/{installation_id}/repositories",
            headers=headers,
            timeout=10.0,
        )
        repositories_response.raise_for_status()
        github_user_id = user.github_user_id
        repositories = {
            int(repository["id"]): str(repository["name"])
            for repository in repositories_response.json().get("repositories", [])
        }
    else:
        return AccessDenied(reason="installation_not_controlled")

    return VerifiedInstallationAccess(
        github_user_id=github_user_id,
        installation_id=installation_id,
        repositories=repositories,
    )


def issue_live_sign_in(assertion: LiveInstallationAssertion) -> str:
    """Seal the verified installation map into an HttpOnly cookie value.

    The OAuth token is not in this payload. HMAC proves the control plane signed it; expires_at
    is the assertion's own freshness, because an HMAC does not expire.
    """
    payload = {
        "github_user_id": assertion.github_user_id,
        "installations": {
            str(installation_id): {str(repo_id): name for repo_id, name in repos.items()}
            for installation_id, repos in assertion.installations.items()
        },
        "expires_at": assertion.expires_at,
    }
    raw = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    digest = hmac.new(_sign_key(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{raw}.{digest}"


def read_live_sign_in(cookie: str) -> LiveInstallationAssertion | None:
    if "." not in cookie:
        return None
    raw, digest = cookie.rsplit(".", 1)
    expected = hmac.new(_sign_key(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        return None
    try:
        payload = json.loads(_b64decode(raw).decode("utf-8"))
        expires_at = int(payload["expires_at"])
        github_user_id = int(payload["github_user_id"])
        installations = _installations_from_payload(payload["installations"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    if expires_at <= int(time.time()):
        return None
    return LiveInstallationAssertion(
        github_user_id=github_user_id,
        installations=installations,
        expires_at=expires_at,
    )


def _installations_from_payload(raw: object) -> dict[int, dict[int, str]]:
    if not isinstance(raw, dict):
        raise TypeError("installations must be an object")
    installations: dict[int, dict[int, str]] = {}
    for installation_key, repos in raw.items():
        if not isinstance(repos, dict):
            raise TypeError("installation repositories must be an object")
        installations[int(installation_key)] = {
            int(repo_id): str(name) for repo_id, name in repos.items()
        }
    return installations


def _sign_key() -> bytes:
    settings = get_settings()
    secret = settings.github_oauth_client_secret or settings.github_webhook_secret
    return secret.encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    pad = "=" * ((-len(text)) % 4)
    return base64.urlsafe_b64decode(text + pad)
