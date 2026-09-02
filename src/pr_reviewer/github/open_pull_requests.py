"""Read the open, reviewable pull requests for an installation repository."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


class InstallationTokenProvider(Protocol):
    def __call__(self, installation_id: int) -> str: ...


class HttpClient(Protocol):
    def get(
        self, url: str, *, headers: dict[str, str], params: dict[str, str], timeout: float
    ) -> httpx.Response: ...


@dataclass(frozen=True)
class OpenPullRequest:
    number: int
    title: str
    author: str
    head_sha: str
    updated_at: str


def list_open_pull_requests(
    repository_id: int,
    *,
    installation_id: int,
    token_provider: InstallationTokenProvider,
    client: HttpClient | None = None,
    api_base_url: str = "https://api.github.com",
    timeout_seconds: float = 10.0,
) -> list[OpenPullRequest]:
    """Return only open non-draft pull requests in GitHub's newest-first order."""
    http_client = client or httpx.Client()
    response = http_client.get(
        f"{api_base_url}/repositories/{repository_id}/pulls",
        headers={
            "accept": "application/vnd.github+json",
            "authorization": f"Bearer {token_provider(installation_id)}",
            "x-github-api-version": "2022-11-28",
        },
        params={"state": "open", "sort": "updated", "direction": "desc"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, list):
        raise ValueError("GitHub pull request response must be a list")
    pull_requests: list[OpenPullRequest] = []
    for raw in body:
        if not isinstance(raw, dict) or raw.get("draft") is True:
            continue
        user = raw.get("user")
        head = raw.get("head")
        number = raw.get("number")
        title = raw.get("title")
        updated_at = raw.get("updated_at")
        if not isinstance(user, dict) or not isinstance(head, dict):
            raise ValueError("GitHub pull request entry is invalid")
        author, head_sha = user.get("login"), head.get("sha")
        if (
            not isinstance(number, int)
            or not isinstance(title, str)
            or not isinstance(updated_at, str)
        ):
            raise ValueError("GitHub pull request entry is invalid")
        if not isinstance(author, str) or not isinstance(head_sha, str):
            raise ValueError("GitHub pull request entry is invalid")
        pull_requests.append(
            OpenPullRequest(
                number=number,
                title=title,
                author=author,
                head_sha=head_sha,
                updated_at=updated_at,
            )
        )
    return pull_requests
