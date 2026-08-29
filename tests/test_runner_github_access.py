"""Tests for the runner-side GitHub fetch (Runtime Task 4).

fetch_job_snapshot takes a JobEnvelope and a GitHubJobToken and calls GitHub directly, on the
runner's own machine. It never mints a token itself: the GitHub App private key never leaves the
control plane, so this module must have no path to it at all, not even an unused import. That is
checked here directly (source-level, no "private_key" or "GitHubAppSettings" string anywhere in
this file) in addition to the generic import-graph check in test_package_boundaries.py.

A mismatched token (issued for a different repository than the job names) is rejected before any
network call, proven the same way runner/client.py's tests prove it: an exploding client whose
get() raises if it is ever reached.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from pr_reviewer.contracts.runner import JobBudget, JobEnvelope

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def _job_envelope(
    *,
    repository_id: int = 42101,
    pull_request_number: int = 7,
    installation_id: int = 4201,
) -> JobEnvelope:
    return JobEnvelope(
        job_id=uuid.uuid4(),
        installation_id=installation_id,
        repository_id=repository_id,
        pull_request_number=pull_request_number,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        policy_version="v1",
        budget=JobBudget(max_tokens=1000, max_cost_usd=Decimal("1.000000")),
        trace_id=uuid.uuid4(),
        lease_token="lease-token-value",
    )


class ExplodingHttpClient:
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        del headers, timeout
        raise AssertionError(f"unexpected GitHub call: GET {url}, denial should happen first")


class FakeGitHubClient:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.headers_seen: dict[str, str] = {}

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        del timeout
        self.urls.append(url)
        self.headers_seen = headers
        if url.endswith("/pulls/7"):
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={
                    "number": 7,
                    "title": "Numeric endpoint fetch",
                    "body": None,
                    "base": {
                        "sha": BASE_SHA,
                        "repo": {"name": "widgets", "owner": {"login": "foodspector"}},
                    },
                    "head": {"sha": HEAD_SHA},
                },
            )
        if url.endswith("/pulls/7/files"):
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json=[
                    {
                        "filename": "src/one.py",
                        "status": "modified",
                        "patch": "@@ one",
                    }
                ],
            )
        raise AssertionError(f"Unexpected URL: {url}")


def test_github_access_never_touches_the_github_app_private_key() -> None:
    from pr_reviewer.runner import github_access

    source = inspect.getsource(github_access)
    lowered = source.lower()
    assert "private_key" not in lowered
    assert "githubappsettings" not in lowered
    assert "create_installation_token" not in lowered
    assert "pr_reviewer.control_plane" not in source
    assert "pr_reviewer.db" not in source


def test_token_for_a_different_repository_is_rejected_before_any_network_call() -> None:
    from pr_reviewer.contracts.runner import GitHubJobToken
    from pr_reviewer.runner.github_access import fetch_job_snapshot

    job = _job_envelope(repository_id=42101)
    mismatched_token = GitHubJobToken(
        token="ghs_mismatched",
        github_repository_id=99999,
        expires_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="does not match"):
        fetch_job_snapshot(job, mismatched_token, client=ExplodingHttpClient())


def test_fetch_job_snapshot_uses_the_numeric_repository_endpoint_and_bearer_token() -> None:
    from pr_reviewer.contracts.runner import GitHubJobToken
    from pr_reviewer.runner.github_access import fetch_job_snapshot

    job = _job_envelope(repository_id=42102, pull_request_number=7)
    token = GitHubJobToken(
        token="ghs_scoped_token",
        github_repository_id=42102,
        expires_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    client = FakeGitHubClient()

    snapshot = fetch_job_snapshot(
        job, token, client=client, api_base_url="https://api.example.test"
    )

    assert client.urls == [
        "https://api.example.test/repositories/42102/pulls/7",
        "https://api.example.test/repositories/42102/pulls/7/files",
    ]
    assert client.headers_seen["authorization"] == "Bearer ghs_scoped_token"
    assert snapshot.repo_owner == "foodspector"
    assert snapshot.repo_name == "widgets"
    assert snapshot.number == 7
    assert snapshot.base_sha == BASE_SHA
    assert snapshot.head_sha == HEAD_SHA
    assert snapshot.files[0].path == "src/one.py"
    assert snapshot.files[0].patch == "@@ one"
