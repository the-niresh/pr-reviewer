"""Injectable GitHub read clients for the TUI until Track A modules land."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class PermittedRepository:
    id: int
    full_name: str
    private: bool = False


@dataclass(frozen=True)
class OpenPullRequest:
    number: int
    title: str
    author: str
    head_sha: str
    updated_at: str


class InstallationRepositoriesReader(Protocol):
    def list_repositories(self, installation_id: int) -> tuple[PermittedRepository, ...]: ...


class OpenPullRequestsReader(Protocol):
    def list_open_pull_requests(
        self,
        owner: str,
        repository: str,
    ) -> tuple[OpenPullRequest, ...]: ...


@dataclass
class FakeInstallationRepositoriesReader:
    repositories: tuple[PermittedRepository, ...] = ()

    def list_repositories(self, installation_id: int) -> tuple[PermittedRepository, ...]:
        del installation_id
        return self.repositories


@dataclass
class FakeOpenPullRequestsReader:
    pull_requests: tuple[OpenPullRequest, ...] = ()

    def list_open_pull_requests(
        self,
        owner: str,
        repository: str,
    ) -> tuple[OpenPullRequest, ...]:
        del owner, repository
        return self.pull_requests


def try_real_installation_repositories_reader() -> InstallationRepositoriesReader | None:
    try:
        module = importlib.import_module("pr_reviewer.github.installation_repositories")
    except ImportError:
        return None
    return _RealInstallationRepositoriesReader(module)


def try_real_open_pull_requests_reader() -> OpenPullRequestsReader | None:
    try:
        module = importlib.import_module("pr_reviewer.github.open_pull_requests")
    except ImportError:
        return None
    return _RealOpenPullRequestsReader(module)


class _RealInstallationRepositoriesReader:
    def __init__(self, module: Any) -> None:
        self._module = module

    def list_repositories(self, installation_id: int) -> tuple[PermittedRepository, ...]:
        rows = self._module.list_installation_repositories(installation_id)
        return tuple(
            PermittedRepository(id=row.id, full_name=row.full_name, private=row.private)
            for row in rows
        )


class _RealOpenPullRequestsReader:
    def __init__(self, module: Any) -> None:
        self._module = module

    def list_open_pull_requests(
        self,
        owner: str,
        repository: str,
    ) -> tuple[OpenPullRequest, ...]:
        rows = self._module.list_open_pull_requests(owner, repository)
        return tuple(
            OpenPullRequest(
                number=row.number,
                title=row.title,
                author=row.author,
                head_sha=row.head_sha,
                updated_at=row.updated_at,
            )
            for row in rows
        )
