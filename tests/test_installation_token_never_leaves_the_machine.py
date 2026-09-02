"""Guards the two-plane boundary for the GitHub installation token the TUI mints.

CLAUDE.md's hard rule: source, diff hunks, agent reasoning, sandbox logs and model/GitHub keys
must never cross to the hosted plane. The installation token is a GitHub key: it is minted by
the hosted control plane (in exchange for the runner's own credential) but must then be used
only to talk to GitHub, and must never be written to disk anywhere on the runner's machine.

This test wires together the two real production pieces exactly as
tui/github_reads.py._try_installation_token_provider and the real readers do: mint the token
through the hosted /api/runner/installations/{id}/token endpoint, then hand it to
list_installation_repositories and list_open_pull_requests as their token_provider. Every
network call either function could make is intercepted (httpx.post for the mint call, an
injected client for the GitHub calls), so nothing here touches a real network -- and every call
that was made is inspected afterwards for exactly two properties: the token appears in no file
under the runner's home directory, and it appears in no outbound call whose host is not
api.github.com.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest

from pr_reviewer.github.installation_repositories import list_installation_repositories
from pr_reviewer.github.open_pull_requests import list_open_pull_requests
from pr_reviewer.runner.secrets import FileSecretStore
from pr_reviewer.tui import github_reads
from pr_reviewer.tui.auth_state import RUNNER_CREDENTIAL_SECRET

HOSTED_ORIGIN = "https://hosted.example.com"
RUNNER_CREDENTIAL = "runner-credential-abc"
INSTALLATION_TOKEN = "ghs_do_not_leak_this_token"
INSTALLATION_ID = 42


class RecordingHttpClient:
    """Stands in for the real httpx.Client the GitHub read functions would otherwise build.

    No real network call is ever made through this: every GET is answered locally, and its url
    and headers are kept so the test can inspect, after the fact, exactly which outbound calls
    carried the installation token and to which host each one went.
    """

    def __init__(self, response_json: object) -> None:
        self.calls: list[dict[str, object]] = []
        self._response_json = response_json

    def get(
        self, url: str, *, headers: dict[str, str], timeout: float, **kwargs: object
    ) -> httpx.Response:
        self.calls.append({"url": url, "headers": dict(headers)})
        return httpx.Response(200, request=httpx.Request("GET", url), json=self._response_json)


def _install_runner_credential(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PR_REVIEWER_HOSTED_ORIGIN", HOSTED_ORIGIN)
    store = FileSecretStore(tmp_path / "secrets")
    store.set(RUNNER_CREDENTIAL_SECRET, RUNNER_CREDENTIAL)
    # The real _try_installation_token_provider always builds its own secret store from
    # Path.home(); swapping in this tmp_path-backed one is the injection seam, not a shortcut
    # around the code under test.
    monkeypatch.setattr(github_reads, "get_secret_store", lambda **kwargs: store)


def _install_mint_endpoint(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, object]]) -> None:
    def fake_post(url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response:
        calls.append({"url": url, "headers": dict(headers)})
        return httpx.Response(
            200, request=httpx.Request("POST", url), json={"token": INSTALLATION_TOKEN}
        )

    monkeypatch.setattr(httpx, "post", fake_post)


def _run_reads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[
    list[dict[str, object]], RecordingHttpClient, RecordingHttpClient
]:
    mint_calls: list[dict[str, object]] = []
    _install_runner_credential(monkeypatch, tmp_path)
    _install_mint_endpoint(monkeypatch, mint_calls)

    token_provider = github_reads._try_installation_token_provider()
    assert token_provider is not None

    repos_client = RecordingHttpClient({"repositories": []})
    list_installation_repositories(
        INSTALLATION_ID, token_provider=token_provider, client=repos_client
    )

    pulls_client = RecordingHttpClient([])
    list_open_pull_requests(
        7,
        installation_id=INSTALLATION_ID,
        token_provider=token_provider,
        client=pulls_client,
    )

    return mint_calls, repos_client, pulls_client


def test_installation_token_is_never_written_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_reads(monkeypatch, tmp_path)

    for path in tmp_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert INSTALLATION_TOKEN.encode() not in content, f"token leaked into {path}"


def test_installation_token_is_only_ever_sent_to_github(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mint_calls, repos_client, pulls_client = _run_reads(monkeypatch, tmp_path)

    # The token_provider mints fresh on every call (no caching, see github_reads.py), so both
    # reads produce their own mint call. Each one authenticates with the runner's own credential,
    # not the installation token it does not have yet, and must go to the hosted plane, never to
    # GitHub directly.
    assert len(mint_calls) == 2
    for mint_call in mint_calls:
        assert urlparse(str(mint_call["url"])).hostname == "hosted.example.com"
        mint_headers = mint_call["headers"]
        assert isinstance(mint_headers, dict)
        assert mint_headers["authorization"] == f"Bearer {RUNNER_CREDENTIAL}"

    github_calls = repos_client.calls + pulls_client.calls
    assert github_calls, "expected the reads to actually call out to GitHub"

    saw_token = False
    for call in github_calls:
        headers = call["headers"]
        assert isinstance(headers, dict)
        authorization = headers.get("authorization", "")
        if INSTALLATION_TOKEN in authorization:
            saw_token = True
            host = urlparse(str(call["url"])).hostname
            assert host == "api.github.com", (
                f"installation token sent to {host}, not api.github.com: {call['url']}"
            )
    assert saw_token, "expected at least one GitHub call to actually carry the installation token"
