"""Tests for the loopback onboarding app (Runtime Task 8).

This is the local HTTP surface that receives the user's model API key. It binds 127.0.0.1 only,
signs its own session, and writes the key into the Task 5 SecretStore. It must never import the
hosted control plane: pairing reuse is forwarded over HTTPS through an injectable client, so the
same indistinguishable denial Task 2 already proved (invalid_or_expired_code) is the denial this
app returns, without this module gaining a Neon handle.

Imports of runner.web.local_auth stay inside test bodies so a missing module fails the test
instead of interrupting collection.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pr_reviewer.containers.runtime import ContainerProbe
from pr_reviewer.contracts.runner import PairingDenied, RunnerCredential
from pr_reviewer.runner.modes import select_runtime_mode
from pr_reviewer.runner.secrets import FileSecretStore

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "pr_reviewer"
LOCAL_AUTH = SRC_ROOT / "runner" / "web" / "local_auth.py"
MODEL_KEY_MARKER_PREFIX = "sk-onboarding-must-not-echo-"


def _probe(*, ready: bool, failures: tuple[str, ...] = ()) -> ContainerProbe:
    return ContainerProbe(
        docker_cli_found=ready,
        daemon_running=ready,
        socket_accessible=ready,
        image_pull_succeeded=ready,
        runs_as_non_root=ready,
        network_isolated=ready,
        resource_limits_enforced=ready,
        platform_supported=ready,
        failures=failures,
    )


class _OneUsePairingClient:
    """Stand-in for the hosted exchange over HTTPS. First use succeeds; replay returns Task 2's
    denial. local_auth must not import control_plane.pairing to get this behaviour.
    """

    def __init__(self) -> None:
        self._used = False
        self.calls: list[tuple[str, str]] = []

    def exchange(self, code: str, proof: str) -> RunnerCredential | PairingDenied:
        self.calls.append((code, proof))
        if self._used:
            return PairingDenied(reason="invalid_or_expired_code")
        self._used = True
        return RunnerCredential(runner_id=uuid.uuid4(), credential="runner-cred-test")


def _app(
    tmp_path: Path,
    *,
    host: str = "127.0.0.1",
    session_secret: str = "session-secret-for-tests-not-a-model-key",
    pairing: _OneUsePairingClient | None = None,
    probe: ContainerProbe | None = None,
):
    from pr_reviewer.runner.web.local_auth import create_local_onboarding_app

    return create_local_onboarding_app(
        host=host,
        session_secret=session_secret,
        secrets=FileSecretStore(tmp_path / "secrets"),
        pairing_client=pairing if pairing is not None else _OneUsePairingClient(),
        probe=probe if probe is not None else _probe(ready=True),
        requested_mode="full",
    )


def _csrf_token(client: TestClient) -> str:
    response = client.get("/onboarding/session")
    assert response.status_code == 200
    token = response.json()["csrf_token"]
    assert isinstance(token, str) and token
    return token


def test_non_loopback_bind_is_rejected(tmp_path: Path) -> None:
    from pr_reviewer.runner.web.local_auth import LocalAuthError

    for host in ("0.0.0.0", "192.168.1.10", "::", "[::]"):
        with pytest.raises(LocalAuthError):
            _app(tmp_path, host=host)


def test_missing_session_secret_is_rejected(tmp_path: Path) -> None:
    from pr_reviewer.runner.web.local_auth import LocalAuthError

    with pytest.raises(LocalAuthError):
        _app(tmp_path, session_secret="")


def test_post_without_csrf_token_is_rejected(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path))
    key = MODEL_KEY_MARKER_PREFIX + uuid.uuid4().hex
    response = client.post(
        "/onboarding/model-key",
        json={"provider": "openai", "key": key},
    )
    assert response.status_code in {400, 403}
    assert key not in response.text


def test_post_with_a_wrong_csrf_token_is_rejected(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path))
    _csrf_token(client)
    key = MODEL_KEY_MARKER_PREFIX + uuid.uuid4().hex
    response = client.post(
        "/onboarding/model-key",
        json={"provider": "openai", "key": key},
        headers={"x-csrf-token": "not-the-session-token"},
    )
    assert response.status_code in {400, 403}
    assert key not in response.text


def test_reused_pairing_code_is_rejected_with_the_same_denial_as_task_2(
    tmp_path: Path,
) -> None:
    pairing = _OneUsePairingClient()
    client = TestClient(_app(tmp_path, pairing=pairing))
    token = _csrf_token(client)
    body = {"code": "PAIR-USED-ONCE", "proof": "pkce-verifier"}

    first = client.post(
        "/onboarding/pairing/exchange",
        json=body,
        headers={"x-csrf-token": token},
    )
    assert first.status_code == 200

    replay = client.post(
        "/onboarding/pairing/exchange",
        json=body,
        headers={"x-csrf-token": token},
    )
    assert replay.status_code == 400
    assert replay.json()["reason"] == "invalid_or_expired_code"
    assert pairing.calls == [
        ("PAIR-USED-ONCE", "pkce-verifier"),
        ("PAIR-USED-ONCE", "pkce-verifier"),
    ]


def test_model_key_is_stored_in_the_secret_store_and_never_echoed(tmp_path: Path) -> None:
    from pr_reviewer.runner.web.local_auth import (
        LOCAL_MODEL_KEY_SECRET_NAME,
        create_local_onboarding_app,
    )

    secrets = FileSecretStore(tmp_path / "secrets")
    app = create_local_onboarding_app(
        host="127.0.0.1",
        session_secret="session-secret-for-tests-not-a-model-key",
        secrets=secrets,
        pairing_client=_OneUsePairingClient(),
        probe=_probe(ready=True),
        requested_mode="full",
    )
    client = TestClient(app)
    token = _csrf_token(client)
    key = MODEL_KEY_MARKER_PREFIX + uuid.uuid4().hex

    response = client.post(
        "/onboarding/model-key",
        json={"provider": "openai", "key": key},
        headers={"x-csrf-token": token},
    )
    assert response.status_code == 200
    assert key not in response.text
    assert key not in str(response.headers)
    assert key not in repr(response.json())
    assert secrets.get(LOCAL_MODEL_KEY_SECRET_NAME) == key


def test_model_key_never_appears_in_os_environ_or_a_spawned_childs_environment(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.web.local_auth import (
        LOCAL_MODEL_KEY_SECRET_NAME,
        create_local_onboarding_app,
    )

    secrets = FileSecretStore(tmp_path / "secrets")
    app = create_local_onboarding_app(
        host="127.0.0.1",
        session_secret="session-secret-for-tests-not-a-model-key",
        secrets=secrets,
        pairing_client=_OneUsePairingClient(),
        probe=_probe(ready=True),
        requested_mode="full",
    )
    client = TestClient(app)
    token = _csrf_token(client)
    key = MODEL_KEY_MARKER_PREFIX + uuid.uuid4().hex

    before = dict(os.environ)
    response = client.post(
        "/onboarding/model-key",
        json={"provider": "openai", "key": key},
        headers={"x-csrf-token": token},
    )
    assert response.status_code == 200
    assert secrets.get(LOCAL_MODEL_KEY_SECRET_NAME) == key
    assert dict(os.environ) == before, "storing a model key must never mutate os.environ"

    child = subprocess.run(
        [sys.executable, "-c", "import os, sys; sys.stdout.write(repr(dict(os.environ)))"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert key not in child.stdout, "model key leaked into a spawned child's environment"


def test_mode_preview_uses_select_runtime_mode_not_a_second_decision(tmp_path: Path) -> None:
    probe = _probe(ready=False, failures=("docker CLI not found on PATH",))
    expected = select_runtime_mode(probe, "full")
    client = TestClient(_app(tmp_path, probe=probe))

    response = client.get("/onboarding/mode")
    assert response.status_code == 200
    body = response.json()
    assert body["granted_mode"] == expected.granted_mode
    assert body["downgraded"] is True
    assert tuple(body["disabled_features"]) == expected.disabled_features
    assert expected.disabled_features != ()


def test_hosted_packages_cannot_import_the_module_that_holds_the_model_key() -> None:
    needles = ("pr_reviewer.runner.web.local_auth", "pr_reviewer.runner.web")
    for package_name in ("control_plane", "web", "cli", "db"):
        for path in (SRC_ROOT / package_name).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for needle in needles:
                assert needle not in source, f"{path} imports {needle}"


def test_local_auth_never_imports_the_hosted_database_or_control_plane() -> None:
    source = LOCAL_AUTH.read_text(encoding="utf-8")
    assert "pr_reviewer.db" not in source
    assert "pr_reviewer.control_plane" not in source
    assert "pr_reviewer.cli" not in source
    assert "select_runtime_mode" in source
