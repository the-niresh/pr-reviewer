"""Tests for hosted GitHub sign-in (Runtime Task 2A).

State is CSRF protection, and CSRF protection is exactly the property that makes "replayed",
"expired", "wrong browser session", "missing", and "forged" all the SAME failure from the
caller's point of view: none of them are things a caller presenting a code and a state is
authorised to tell apart. See control_plane/github_auth.py's SignInDenialReason for why they all
collapse into invalid_or_expired_state, and docs/phases/phase-2-security-design-gate.md section 6
for the rule in general.

Every denial test below passes an ExplodingHttpClient, so a passing test also proves the denial
happened before any GitHub network call was attempted, not just that the final return value
happened to look right.
"""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from pr_reviewer.control_plane.github_auth import SignInChallenge, VerifiedGitHubUser
from pr_reviewer.control_plane.repository_policy import hash_runner_credential
from pr_reviewer.db.client import connection
from pr_reviewer.web.app import app

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_INSTALLATIONS_URL = "https://api.github.com/user/installations"


class ExplodingHttpClient:
    """Fails any test that reaches a network call it should not reach.

    Used for every denial path: state validation must reject a replayed, expired, mismatched, or
    forged attempt before ever spending a GitHub API call on it.
    """

    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response:
        del headers, timeout
        raise AssertionError(f"unexpected GET {url}, denial should happen before any GitHub call")

    def post(
        self, url: str, *, headers: dict[str, str], data: dict[str, str], timeout: float
    ) -> httpx.Response:
        del headers, data, timeout
        raise AssertionError(
            f"unexpected POST {url}, denial should happen before any GitHub call"
        )


class FakeGitHubClient:
    """A GitHub that always issues the same access token and identifies the same user, and
    reports a fixed set of installations and repositories per installation. Good enough to
    exercise complete_sign_in and verify_installation_access without a real network call.
    """

    def __init__(
        self,
        access_token: str = "gho_fake_token",
        github_user_id: int = 4242,
        login: str = "octocat",
        installation_ids: tuple[int, ...] = (),
        repositories_by_installation: dict[int, dict[int, str]] | None = None,
    ) -> None:
        self.access_token = access_token
        self.github_user_id = github_user_id
        self.login = login
        self.installation_ids = installation_ids
        self.repositories_by_installation = repositories_by_installation or {}
        self.calls: list[tuple[str, str]] = []

    def post(
        self, url: str, *, headers: dict[str, str], data: dict[str, str], timeout: float
    ) -> httpx.Response:
        del headers, timeout
        self.calls.append(("POST", url))
        assert url == GITHUB_TOKEN_URL
        assert "code" in data
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"access_token": self.access_token, "token_type": "bearer"},
        )

    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response:
        del timeout
        self.calls.append(("GET", url))
        assert headers["authorization"] == f"Bearer {self.access_token}"

        if url == GITHUB_USER_URL:
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={"id": self.github_user_id, "login": self.login},
            )
        if url == GITHUB_INSTALLATIONS_URL:
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={"installations": [{"id": iid} for iid in self.installation_ids]},
            )
        for installation_id, repos in self.repositories_by_installation.items():
            if url == f"{GITHUB_INSTALLATIONS_URL}/{installation_id}/repositories":
                return httpx.Response(
                    200,
                    request=httpx.Request("GET", url),
                    json={
                        "repositories": [
                            {"id": repo_id, "name": name} for repo_id, name in repos.items()
                        ]
                    },
                )
        raise AssertionError(f"unexpected GET {url}")


def backdate_oauth_state(state: str, minutes_ago: int) -> None:
    # oauth_states stores state hashed, the same way runners.credential_hash and
    # pairing_codes.code_hash do (hash_runner_credential is the one opaque-secret hash this
    # codebase uses), so backdating by the raw state means recomputing that hash to find the row.
    with connection() as conn, conn.transaction():
        conn.execute(
            "update oauth_states set created_at = now() - %s::interval where state_hash = %s",
            (f"{minutes_ago} minutes", hash_runner_credential(state)),
        )


def make_verified_github_user(github_user_id: int = 42) -> VerifiedGitHubUser:
    return VerifiedGitHubUser(
        github_user_id=github_user_id,
        login="octocat",
        access_token=SecretStr("gho_fake_token"),
        return_to="/dashboard",
    )


def start_a_sign_in(return_to: str = "/dashboard") -> SignInChallenge:
    from pr_reviewer.control_plane.github_oauth import begin_sign_in

    challenge = begin_sign_in(return_to)
    assert isinstance(challenge, SignInChallenge)
    return challenge


def test_verified_installation_access_construction_site_is_exactly_github_oauth() -> None:
    # Runtime Task 2 gave this exactly one construction site and it was pairing.py, because
    # pairing.py held the only (test-only, unverified) builder. Task 2A adds the real one, in
    # github_oauth.py, and pairing.py must stop constructing it: approve_pairing only ever
    # receives a VerifiedInstallationAccess as an argument now, it never makes one.
    #
    # AST-based, not text pattern matching (see test_package_boundaries.py's collect_imports for
    # the precedent): "VerifiedInstallationAccess(" also appears at the class's own definition
    # (a ClassDef, not a Call), so only real ast.Call nodes count.
    sites: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if called_name == "VerifiedInstallationAccess":
                sites.append(str(path.relative_to(SRC_ROOT.parent.parent)))
                break

    assert sites == ["src/pr_reviewer/control_plane/github_oauth.py"], (
        "VerifiedInstallationAccess must be constructed in exactly "
        f"src/pr_reviewer/control_plane/github_oauth.py, found: {sites}"
    )


# --- sign-in: state validation (all denials must happen before any GitHub call) -----------------


def test_replayed_state_is_denied() -> None:
    from pr_reviewer.control_plane.github_auth import SignInDenied
    from pr_reviewer.control_plane.github_oauth import complete_sign_in

    challenge = start_a_sign_in()
    fake_client = FakeGitHubClient()

    first = complete_sign_in(
        "some-code", challenge.state, challenge.binding_secret, http_client=fake_client
    )
    assert isinstance(first, VerifiedGitHubUser)

    replay = complete_sign_in(
        "some-code",
        challenge.state,
        challenge.binding_secret,
        http_client=ExplodingHttpClient(),
    )
    assert isinstance(replay, SignInDenied)
    assert replay.reason == "invalid_or_expired_state"


def test_expired_state_is_denied() -> None:
    from pr_reviewer.control_plane.github_auth import SignInDenied
    from pr_reviewer.control_plane.github_oauth import complete_sign_in

    challenge = start_a_sign_in()
    backdate_oauth_state(challenge.state, minutes_ago=11)

    result = complete_sign_in(
        "some-code",
        challenge.state,
        challenge.binding_secret,
        http_client=ExplodingHttpClient(),
    )
    assert isinstance(result, SignInDenied)
    assert result.reason == "invalid_or_expired_state"


def test_state_from_a_different_browser_session_is_denied() -> None:
    # The attack this protects against: an attacker gets their own valid (state, binding_secret)
    # pair from begin_sign_in, then tricks a victim's browser into completing the callback with
    # the attacker's state but the VICTIM's cookies. Since the victim's browser never received the
    # attacker's binding_secret cookie, the pair the callback actually presents does not match,
    # and this must be denied even though the state itself is genuine and unexpired.
    from pr_reviewer.control_plane.github_auth import SignInDenied
    from pr_reviewer.control_plane.github_oauth import complete_sign_in

    challenge = start_a_sign_in()

    result = complete_sign_in(
        "some-code",
        challenge.state,
        "a-binding-secret-from-a-different-browser",
        http_client=ExplodingHttpClient(),
    )
    assert isinstance(result, SignInDenied)
    assert result.reason == "invalid_or_expired_state"


def test_missing_state_is_denied() -> None:
    from pr_reviewer.control_plane.github_auth import SignInDenied
    from pr_reviewer.control_plane.github_oauth import complete_sign_in

    result = complete_sign_in(
        "some-code", "", "some-binding-secret", http_client=ExplodingHttpClient()
    )
    assert isinstance(result, SignInDenied)
    assert result.reason == "invalid_or_expired_state"


def test_forged_callback_with_no_prior_begin_sign_in_is_denied() -> None:
    from pr_reviewer.control_plane.github_auth import SignInDenied
    from pr_reviewer.control_plane.github_oauth import complete_sign_in

    result = complete_sign_in(
        "some-code",
        "state-nobody-ever-issued",
        "binding-secret-nobody-ever-issued",
        http_client=ExplodingHttpClient(),
    )
    assert isinstance(result, SignInDenied)
    assert result.reason == "invalid_or_expired_state"


def test_successful_sign_in_returns_verified_github_user() -> None:
    from pr_reviewer.control_plane.github_oauth import complete_sign_in

    challenge = start_a_sign_in()
    fake_client = FakeGitHubClient(github_user_id=555, login="paired-user")

    result = complete_sign_in(
        "some-code", challenge.state, challenge.binding_secret, http_client=fake_client
    )

    assert isinstance(result, VerifiedGitHubUser)
    assert result.github_user_id == 555
    assert result.login == "paired-user"
    assert result.access_token.get_secret_value() == "gho_fake_token"
    assert result.return_to == "/dashboard"


def test_begin_sign_in_rejects_return_to_outside_allowlist() -> None:
    from pr_reviewer.control_plane.github_auth import ReturnToRejected
    from pr_reviewer.control_plane.github_oauth import begin_sign_in

    result = begin_sign_in("https://evil.example.com/steal-the-code")

    assert isinstance(result, ReturnToRejected)
    assert result.reason == "return_to_not_allowed"


# --- verify_installation_access -------------------------------------------------------------


def test_verify_installation_access_grants_and_populates_repositories_from_github() -> None:
    from pr_reviewer.contracts.runner import VerifiedInstallationAccess
    from pr_reviewer.control_plane.github_oauth import verify_installation_access

    user = make_verified_github_user()
    fake_client = FakeGitHubClient(
        installation_ids=(9001,),
        repositories_by_installation={9001: {111: "widgets", 222: "gadgets"}},
    )

    result = verify_installation_access(user, 9001, http_client=fake_client)

    assert isinstance(result, VerifiedInstallationAccess)
    assert result.github_user_id == 42
    assert result.installation_id == 9001
    assert result.repositories == {111: "widgets", 222: "gadgets"}


def test_verify_installation_access_denies_unknown_and_uncontrolled_the_same_way() -> None:
    from pr_reviewer.control_plane.github_auth import AccessDenied
    from pr_reviewer.control_plane.github_oauth import verify_installation_access

    user = make_verified_github_user()

    # This user's GitHub /user/installations lists only 9001. 9999999 is an installation that
    # simply does not exist anywhere; 9002 is a real installation somebody else controls. Neither
    # is something this user's own verified session can distinguish, and this test asserts the
    # code does not try.
    fake_client = FakeGitHubClient(installation_ids=(9001,))

    unknown = verify_installation_access(user, 9999999, http_client=fake_client)
    not_controlled = verify_installation_access(user, 9002, http_client=fake_client)

    assert isinstance(unknown, AccessDenied)
    assert isinstance(not_controlled, AccessDenied)
    assert unknown.reason == not_controlled.reason == "installation_not_controlled"


# --- HTTP layer: cookie attributes on the sign-in redirect -----------------------------------


def test_begin_sign_in_route_sets_httponly_cookie() -> None:
    client = TestClient(app)
    response = client.get(
        "/api/auth/github/sign-in", params={"return_to": "/dashboard"}, follow_redirects=False
    )

    set_cookie = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()


def test_begin_sign_in_route_sets_secure_cookie() -> None:
    client = TestClient(app)
    response = client.get(
        "/api/auth/github/sign-in", params={"return_to": "/dashboard"}, follow_redirects=False
    )

    set_cookie = response.headers.get("set-cookie", "")
    assert "secure" in set_cookie.lower()


def test_begin_sign_in_route_sets_samesite_lax_cookie() -> None:
    # Not Strict: Strict sounds stronger but silently breaks this exact flow, because a Strict
    # cookie is not sent on the top-level navigation back from github.com to our callback. Lax is
    # sent on top-level GET navigations, which is exactly what the callback redirect is.
    client = TestClient(app)
    response = client.get(
        "/api/auth/github/sign-in", params={"return_to": "/dashboard"}, follow_redirects=False
    )

    set_cookie = response.headers.get("set-cookie", "")
    assert "samesite=lax" in set_cookie.lower()


def test_begin_sign_in_route_scopes_cookie_path_to_callback() -> None:
    client = TestClient(app)
    response = client.get(
        "/api/auth/github/sign-in", params={"return_to": "/dashboard"}, follow_redirects=False
    )

    set_cookie = response.headers.get("set-cookie", "")
    assert "path=/api/auth/github/callback" in set_cookie.lower()


def test_begin_sign_in_route_sets_max_age_matching_state_expiry() -> None:
    from pr_reviewer.control_plane.github_oauth import STATE_TTL_SECONDS

    client = TestClient(app)
    response = client.get(
        "/api/auth/github/sign-in", params={"return_to": "/dashboard"}, follow_redirects=False
    )

    set_cookie = response.headers.get("set-cookie", "")
    assert f"max-age={STATE_TTL_SECONDS}" in set_cookie.lower()


def test_begin_sign_in_route_rejects_return_to_outside_allowlist() -> None:
    client = TestClient(app)
    response = client.get(
        "/api/auth/github/sign-in",
        params={"return_to": "https://evil.example.com/steal-the-code"},
        follow_redirects=False,
    )

    assert response.status_code == 400


_GITHUB_TOKEN_PREFIXES = ("gho_", "ghu_", "ghs_", "github_pat_")


def _decode_live_sign_in_payload(cookie: str) -> dict[str, object]:
    import base64
    import json

    raw, _digest = cookie.rsplit(".", 1)
    pad = "=" * ((-len(raw)) % 4)
    payload: dict[str, object] = json.loads(base64.urlsafe_b64decode(raw + pad))
    return payload


def _assert_no_github_token_pattern(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _assert_no_github_token_pattern(key)
            _assert_no_github_token_pattern(nested)
        return
    if isinstance(value, list):
        for nested in value:
            _assert_no_github_token_pattern(nested)
        return
    text = str(value).lower()
    for prefix in _GITHUB_TOKEN_PREFIXES:
        assert prefix not in text, f"cookie field carried a GitHub token pattern {prefix}"


def test_live_sign_in_cookie_does_not_carry_a_github_token() -> None:
    from pr_reviewer.control_plane.github_oauth import (
        capture_live_assertion,
        issue_live_sign_in,
    )

    user = VerifiedGitHubUser(
        github_user_id=42,
        login="octocat",
        access_token=SecretStr("gho_must_never_appear_in_the_cookie"),
        return_to="/dashboard",
    )
    fake_client = FakeGitHubClient(
        access_token="gho_must_never_appear_in_the_cookie",
        installation_ids=(9001,),
        repositories_by_installation={9001: {111: "widgets"}},
    )
    cookie = issue_live_sign_in(capture_live_assertion(user, http_client=fake_client))
    payload = _decode_live_sign_in_payload(cookie)
    assert "access_token" not in payload
    _assert_no_github_token_pattern(payload)


def test_live_sign_in_assertion_expires_even_when_the_hmac_is_still_valid() -> None:
    import time

    from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
    from pr_reviewer.control_plane.github_oauth import issue_live_sign_in, read_live_sign_in

    assertion = LiveInstallationAssertion(
        github_user_id=42,
        installations={9001: {111: "widgets"}},
        expires_at=int(time.time()) - 1,
    )
    cookie = issue_live_sign_in(assertion)
    assert read_live_sign_in(cookie) is None


def test_capture_live_assertion_calls_user_installations_once() -> None:
    from pr_reviewer.control_plane.github_oauth import (
        GITHUB_INSTALLATIONS_URL,
        capture_live_assertion,
    )

    user = make_verified_github_user()
    fake_client = FakeGitHubClient(
        installation_ids=(9001, 9002),
        repositories_by_installation={
            9001: {111: "widgets"},
            9002: {222: "gadgets"},
        },
    )
    assertion = capture_live_assertion(user, http_client=fake_client)
    installation_list_calls = [
        method_url
        for method_url in fake_client.calls
        if method_url == ("GET", GITHUB_INSTALLATIONS_URL)
    ]
    assert len(installation_list_calls) == 1
    assert assertion.github_user_id == 42
    assert assertion.installations == {9001: {111: "widgets"}, 9002: {222: "gadgets"}}
    assert assertion.expires_at > 0


def test_read_live_sign_in_returns_the_sealed_installation_map() -> None:
    import time

    from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
    from pr_reviewer.control_plane.github_oauth import issue_live_sign_in, read_live_sign_in

    assertion = LiveInstallationAssertion(
        github_user_id=42,
        installations={9001: {111: "widgets"}},
        expires_at=int(time.time()) + 600,
    )
    restored = read_live_sign_in(issue_live_sign_in(assertion))
    assert restored == assertion


def test_verify_installation_access_from_assertion_does_not_call_github() -> None:
    import time

    from pr_reviewer.contracts.runner import VerifiedInstallationAccess
    from pr_reviewer.control_plane.github_auth import AccessDenied, LiveInstallationAssertion
    from pr_reviewer.control_plane.github_oauth import verify_installation_access

    assertion = LiveInstallationAssertion(
        github_user_id=42,
        installations={9001: {111: "widgets"}},
        expires_at=int(time.time()) + 600,
    )
    exploding = ExplodingHttpClient()
    granted = verify_installation_access(
        None, 9001, http_client=exploding, assertion=assertion
    )
    denied = verify_installation_access(
        None, 9002, http_client=exploding, assertion=assertion
    )
    assert isinstance(granted, VerifiedInstallationAccess)
    assert granted.repositories == {111: "widgets"}
    assert isinstance(denied, AccessDenied)
    assert denied.reason == "installation_not_controlled"
