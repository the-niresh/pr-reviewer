"""Read exactly the repositories granted to a GitHub App installation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


class InstallationTokenProvider(Protocol):
    def __call__(self, installation_id: int) -> str: ...


class HttpClient(Protocol):
    def get(
        self, url: str, *, headers: dict[str, str], timeout: float
    ) -> httpx.Response: ...


@dataclass(frozen=True)
class InstallationRepository:
    id: int
    full_name: str
    private: bool


def list_installation_repositories(
    installation_id: int,
    *,
    token_provider: InstallationTokenProvider,
    client: HttpClient | None = None,
    api_base_url: str = "https://api.github.com",
    timeout_seconds: float = 10.0,
) -> list[InstallationRepository]:
    """Return every repository currently visible to the installation token."""
    http_client = client or httpx.Client()
    token = token_provider(installation_id)
    headers = {
        "accept": "application/vnd.github+json",
        "authorization": f"Bearer {token}",
        "x-github-api-version": "2022-11-28",
    }
    next_url: str | None = f"{api_base_url}/installation/repositories?per_page=100"
    repositories: list[InstallationRepository] = []

    while next_url is not None:
        response = http_client.get(next_url, headers=headers, timeout=timeout_seconds)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("GitHub installation repository response must be an object")
        raw_repositories = body.get("repositories")
        if not isinstance(raw_repositories, list):
            raise ValueError("GitHub installation repository response lacks repositories")
        for raw_repository in raw_repositories:
            if not isinstance(raw_repository, dict):
                raise ValueError("GitHub installation repository entry must be an object")
            repository_id = raw_repository.get("id")
            full_name = raw_repository.get("full_name")
            private = raw_repository.get("private")
            if not isinstance(repository_id, int) or not isinstance(full_name, str):
                raise ValueError("GitHub installation repository entry is invalid")
            if not isinstance(private, bool):
                raise ValueError("GitHub installation repository privacy is invalid")
            repositories.append(
                InstallationRepository(
                    id=repository_id,
                    full_name=full_name,
                    private=private,
                )
            )
        link = response.links.get("next")
        candidate = link.get("url") if link is not None else None
        next_url = candidate if isinstance(candidate, str) and candidate else None

    return repositories
