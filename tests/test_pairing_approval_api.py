"""Tests for hosted pairing approval and exchangeability status (Runtime Task 2B).

approve_pairing already exists and is correct. It has no HTTP route, so no runner can be paired
in production. These tests pin the hosted surface that Task 8's local poll already expects:

- PairingStatus is pending | exchangeable | invalid_or_expired, never a different vocabulary.
- Status takes the pairing code AND the PKCE challenge. A code-only status call is the
  pending-versus-approved oracle Task 2's single denial reason exists to prevent.
- Status returns only whether an exchange may be attempted. It is idempotent and consumes nothing.
- The approve route consumes a live GitHub sign-in. It never takes github_user_id as a parameter
  and never constructs VerifiedInstallationAccess: verify_installation_access stays the only
  construction site in src/.
- The runner polls. The control plane never calls in.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from test_github_oauth import FakeGitHubClient, make_verified_github_user
from test_runner_pairing import insert_installation, sha256_hex

from pr_reviewer.contracts.runner import VerifiedInstallationAccess
from pr_reviewer.web.app import app

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"
APPROVAL_API = SRC_ROOT / "control_plane" / "approval_api.py"
PAIRING = SRC_ROOT / "control_plane" / "pairing.py"

STATUS_PATH = "/api/runner/pairing-codes/status"
APPROVE_PATH = "/api/pairing/approve"
PAIRING_STATUS_STATES = frozenset({"pending", "exchangeable", "invalid_or_expired"})
STATUS_FORBIDDEN_KEYS = frozenset(
    {
        "installation_id",
        "installation",
        "repository_ids",
        "repositories",
        "device_name",
        "created_at",
        "approved_at",
        "exchanged_at",
        "expires_at",
        "github_user_id",
        "access_token",
    }
)


def _create_pairing(device_name: str = "laptop") -> tuple[str, str, str]:
    from pr_reviewer.control_plane.pairing import create_pairing_code

    verifier = "pkce-verifier-for-status-tests"
    challenge = sha256_hex(verifier)
    created = create_pairing_code(device_name, challenge)
    return created.code, challenge, verifier


def test_approve_route_consumes_a_signed_assertion_not_a_token() -> None:
    import time

    from test_github_oauth import _decode_live_sign_in_payload

    from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
    from pr_reviewer.control_plane.github_oauth import (
        LIVE_SIGN_IN_COOKIE_NAME,
        issue_live_sign_in,
    )

    insert_installation(7010)
    code, _challenge, _verifier = _create_pairing()
    assertion = LiveInstallationAssertion(
        github_user_id=42,
        installations={7010: {11: "in-scope"}},
        expires_at=int(time.time()) + 600,
    )
    cookie = issue_live_sign_in(assertion)
    payload = _decode_live_sign_in_payload(cookie)
    assert "access_token" not in payload
    blob = str(payload).lower()
    for prefix in ("gho_", "ghu_", "ghs_", "github_pat_"):
        assert prefix not in blob

    client = TestClient(app)
    client.cookies.set(LIVE_SIGN_IN_COOKIE_NAME, cookie)
    response = client.post(
        APPROVE_PATH,
        json={"code": code, "installation_id": 7010, "repository_ids": [11]},
    )
    assert response.status_code == 200
    assert response.json()["approved"] is True
    assert "gho_" not in response.text.lower()
    client = TestClient(app)
    code, _challenge, _verifier = _create_pairing()
    response = client.post(
        APPROVE_PATH,
        json={"code": code, "installation_id": 7001, "repository_ids": [11]},
    )
    assert response.status_code == 401
    blob = response.text.lower()
    assert "github_user_id" not in blob
    assert "gho_" not in blob
    assert "verifiedinstallationaccess" not in blob


def test_approve_route_does_not_accept_github_user_id_as_a_parameter() -> None:
    from pr_reviewer.control_plane.approval_api import ApprovePairingBody

    fields = set(ApprovePairingBody.model_fields)
    assert "github_user_id" not in fields
    assert "installation_id" in fields
    assert "code" in fields
    assert "repository_ids" in fields


def test_approval_denied_when_the_signed_in_user_does_not_control_the_installation() -> None:
    from pr_reviewer.control_plane.approval_api import submit_pairing_approval
    from pr_reviewer.control_plane.github_auth import AccessDenied

    insert_installation(7002)
    code, _challenge, _verifier = _create_pairing()
    user = make_verified_github_user(github_user_id=42)
    fake = FakeGitHubClient(installation_ids=(), repositories_by_installation={})

    result = submit_pairing_approval(
        code=code,
        user=user,
        installation_id=7002,
        repository_ids=[],
        http_client=fake,
    )
    assert isinstance(result, AccessDenied)
    assert result.reason == "installation_not_controlled"


def test_approval_denied_for_a_repository_outside_the_verified_set() -> None:
    from pr_reviewer.contracts.runner import PairingDenied
    from pr_reviewer.control_plane.approval_api import submit_pairing_approval

    insert_installation(7003)
    code, _challenge, _verifier = _create_pairing()
    user = make_verified_github_user(github_user_id=42)
    fake = FakeGitHubClient(
        installation_ids=(7003,),
        repositories_by_installation={7003: {11: "in-scope"}},
    )

    result = submit_pairing_approval(
        code=code,
        user=user,
        installation_id=7003,
        repository_ids=[999],
        http_client=fake,
    )
    assert isinstance(result, PairingDenied)
    assert result.reason == "repository_not_in_installation"


def test_replayed_approval_is_denied() -> None:
    from pr_reviewer.contracts.runner import PairingApproved, PairingDenied
    from pr_reviewer.control_plane.approval_api import submit_pairing_approval

    insert_installation(7004)
    code, _challenge, _verifier = _create_pairing()
    user = make_verified_github_user(github_user_id=42)
    fake = FakeGitHubClient(
        installation_ids=(7004,),
        repositories_by_installation={7004: {11: "in-scope"}},
    )

    first = submit_pairing_approval(
        code=code,
        user=user,
        installation_id=7004,
        repository_ids=[11],
        http_client=fake,
    )
    assert isinstance(first, PairingApproved)

    replay = submit_pairing_approval(
        code=code,
        user=user,
        installation_id=7004,
        repository_ids=[11],
        http_client=fake,
    )
    assert isinstance(replay, PairingDenied)
    assert replay.reason == "invalid_or_expired_code"


def test_approval_api_never_constructs_verified_installation_access() -> None:
    source = APPROVAL_API.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(APPROVAL_API))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        assert called_name != "VerifiedInstallationAccess"
    assert "verify_installation_access" in source


def test_status_without_the_challenge_is_rejected() -> None:
    client = TestClient(app)
    code, _challenge, _verifier = _create_pairing()
    response = client.get(STATUS_PATH, params={"code": code})
    assert response.status_code in {400, 422}
    blob = response.text.lower()
    for key in STATUS_FORBIDDEN_KEYS:
        assert key not in blob


def test_status_with_the_wrong_challenge_matches_an_unknown_code() -> None:
    from pr_reviewer.control_plane.pairing import pairing_status

    code, challenge, _verifier = _create_pairing()
    wrong = pairing_status(code, "not-the-challenge")
    missing = pairing_status("not-a-real-code", challenge)
    assert wrong == missing == "invalid_or_expired"


def test_status_stays_pending_until_approved_then_becomes_exchangeable() -> None:
    from pr_reviewer.control_plane.pairing import approve_pairing, pairing_status

    insert_installation(7005)
    code, challenge, _verifier = _create_pairing()
    assert pairing_status(code, challenge) == "pending"

    approve_pairing(code, _access(7005, {11: "in-scope"}), [11])
    assert pairing_status(code, challenge) == "exchangeable"


def test_status_returns_only_whether_an_exchange_may_be_attempted() -> None:
    client = TestClient(app)
    code, challenge, _verifier = _create_pairing()
    response = client.get(STATUS_PATH, params={"code": code, "challenge": challenge})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"state"}
    assert body["state"] in PAIRING_STATUS_STATES
    blob = str(body).lower()
    for key in STATUS_FORBIDDEN_KEYS:
        assert key not in blob


def test_status_is_idempotent_and_never_consumes_the_code() -> None:
    from pr_reviewer.contracts.runner import RunnerCredential
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        exchange_pairing_code,
        pairing_status,
    )

    insert_installation(7006)
    code, challenge, verifier = _create_pairing()
    approve_pairing(code, _access(7006, {11: "in-scope"}), [11])

    first = pairing_status(code, challenge)
    second = pairing_status(code, challenge)
    assert first == second == "exchangeable"

    exchanged = exchange_pairing_code(code, verifier)
    assert isinstance(exchanged, RunnerCredential)
    assert pairing_status(code, challenge) == "invalid_or_expired"


def test_dashboard_route_exists_so_oauth_return_to_is_not_a_404() -> None:
    client = TestClient(app)
    response = client.get("/dashboard")
    assert response.status_code != 404


def test_production_status_client_polls_the_hosted_route_with_code_and_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pr_reviewer.runner.web.local_auth import PendingPairingClient

    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        request = httpx.Request("GET", url)
        return httpx.Response(200, request=request, json={"state": "exchangeable"})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = PendingPairingClient("https://control.example.test")
    assert client.status("PAIR-CODE", "pkce-challenge") == "exchangeable"
    assert captured["url"] == "https://control.example.test/api/runner/pairing-codes/status"
    assert captured["params"] == {"code": "PAIR-CODE", "challenge": "pkce-challenge"}


def test_pending_pairing_client_no_longer_claims_a_task_2b_deferral() -> None:
    source = inspect.getsource(
        __import__(
            "pr_reviewer.runner.web.local_auth", fromlist=["PendingPairingClient"]
        ).PendingPairingClient
    )
    lowered = source.lower()
    assert "until task 2b" not in lowered
    assert "status stays pending" not in lowered
    assert 'return "pending"' not in source


def test_the_control_plane_does_not_call_into_the_runner() -> None:
    approval = APPROVAL_API.read_text(encoding="utf-8")
    pairing = PAIRING.read_text(encoding="utf-8")
    for source in (approval, pairing):
        assert "bind(" not in source
        assert "listen(" not in source
        assert "uvicorn" not in source.lower()


def test_approve_route_never_takes_github_user_id_from_the_http_body() -> None:
    client = TestClient(app)
    code, _challenge, _verifier = _create_pairing()
    response = client.post(
        APPROVE_PATH,
        json={
            "code": code,
            "github_user_id": 42,
            "installation_id": 7007,
            "repository_ids": [11],
        },
    )
    assert response.status_code in {401, 422}
    assert "gho_" not in response.text.lower()


def _access(installation_id: int, repositories: dict[int, str]) -> VerifiedInstallationAccess:
    return VerifiedInstallationAccess(
        github_user_id=42,
        installation_id=installation_id,
        repositories=repositories,
    )
