"""Injectable GitHub read clients for the TUI until Track A modules land."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from pr_reviewer.runner.secrets import get_secret_store
from pr_reviewer.tui.auth_state import RUNNER_CREDENTIAL_SECRET
from pr_reviewer.tui.github_connect import HostedOriginError, resolved_hosted_origin

# The reader never keeps its own copy of a runner credential or a minted token: both are read
# fresh on every call (secret store) or minted fresh on every call (hosted endpoint), matching
# runner/secrets.py's own "no cache" rule for the credential this token is minted from.
InstallationTokenProvider = Callable[[int], str]


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


def _default_runner_credential() -> str | None:
    config_dir = Path.home() / ".config" / "pr-reviewer"
    return get_secret_store(file_fallback_directory=config_dir).get(RUNNER_CREDENTIAL_SECRET)


def _mint_installation_token(hosted_origin: str, credential: str, installation_id: int) -> str:
    response = httpx.post(
        f"{hosted_origin}/api/runner/installations/{installation_id}/token",
        headers={"authorization": f"Bearer {credential}"},
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        # No placeholder, no default: a hosted response with no usable token is a hosted bug or
        # an outage, and the caller must see that immediately, never a silent empty string that
        # would turn into an unauthenticated (and therefore rate-limited or refused) GitHub call.
        raise RuntimeError("installation token response did not include a token")
    return token


def _try_installation_token_provider() -> InstallationTokenProvider | None:
    """None only means "not configured to reach the hosted plane yet" (no hosted origin, or no
    paired runner credential) -- the same graceful degradation _resolve_installation_snapshot
    already applies in tui/app.py. Once both are present, a failure to mint a real token always
    raises out of the returned callable; it never falls back to an empty or placeholder token.
    """
    try:
        hosted_origin = resolved_hosted_origin()
    except HostedOriginError:
        return None
    credential = _default_runner_credential()
    if not credential or not credential.strip():
        return None
    return lambda installation_id: _mint_installation_token(
        hosted_origin, credential, installation_id
    )


@dataclass(frozen=True)
class ReaderUnavailable:
    """Returned instead of a reader when the hosted plane cannot be reached yet.

    Carries the reason in plain words so a caller can show it on screen. Never returned once
    a reader has been minted successfully: from that point on, an empty result is either a
    genuinely empty answer from GitHub or an exception the caller must handle on its own.
    """

    reason: str


def _reader_unavailable_reason() -> str:
    try:
        resolved_hosted_origin()
    except HostedOriginError:
        return (
            "Not connected to the hosted plane, so repositories cannot be listed yet."
        )
    credential = _default_runner_credential()
    if not credential or not credential.strip():
        return "This runner is not paired yet: connect GitHub before repositories can be listed."
    return "Could not reach the hosted plane to list repositories."


def resolve_installation_repositories_reader() -> (
    InstallationRepositoriesReader | ReaderUnavailable
):
    reader = try_real_installation_repositories_reader()
    if reader is not None:
        return reader
    return ReaderUnavailable(_reader_unavailable_reason())


def resolve_open_pull_requests_reader() -> OpenPullRequestsReader | ReaderUnavailable:
    reader = try_real_open_pull_requests_reader()
    if reader is not None:
        return reader
    return ReaderUnavailable(_reader_unavailable_reason())


def try_real_installation_repositories_reader() -> InstallationRepositoriesReader | None:
    try:
        module = importlib.import_module("pr_reviewer.github.installation_repositories")
    except ImportError:
        return None
    token_provider = _try_installation_token_provider()
    if token_provider is None:
        return None
    return _RealInstallationRepositoriesReader(module, token_provider)


def try_real_open_pull_requests_reader() -> OpenPullRequestsReader | None:
    try:
        module = importlib.import_module("pr_reviewer.github.open_pull_requests")
    except ImportError:
        return None
    token_provider = _try_installation_token_provider()
    if token_provider is None:
        return None
    return _RealOpenPullRequestsReader(module, token_provider)


class _RealInstallationRepositoriesReader:
    def __init__(self, module: Any, token_provider: InstallationTokenProvider) -> None:
        self._module = module
        self._token_provider = token_provider

    def list_repositories(self, installation_id: int) -> tuple[PermittedRepository, ...]:
        rows = self._module.list_installation_repositories(
            installation_id, token_provider=self._token_provider
        )
        return tuple(
            PermittedRepository(id=row.id, full_name=row.full_name, private=row.private)
            for row in rows
        )


class _RealOpenPullRequestsReader:
    def __init__(self, module: Any, token_provider: InstallationTokenProvider) -> None:
        self._module = module
        self._token_provider = token_provider

    def list_open_pull_requests(
        self,
        owner: str,
        repository: str,
    ) -> tuple[OpenPullRequest, ...]:
        rows = self._module.list_open_pull_requests(
            owner, repository, token_provider=self._token_provider
        )
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
