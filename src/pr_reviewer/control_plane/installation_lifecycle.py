"""Keeps installations/repositories in sync with GitHub's own installation webhooks.

Nothing populated these tables before this module existed: approve_pairing_by_hash's
"unknown_installation" denial (control_plane/pairing.py) was correct on its own terms, but had
no source of truth ever writing to installations/repositories in production -- register_installation
and register_repository (control_plane/repository_policy.py) had only ever been called from
tests. GitHub sends "installation" for the App itself (install, uninstall, suspend, unsuspend,
permission changes) and "installation_repositories" for repository access changes on an
already-installed App; this module is the one place both land.
"""

from __future__ import annotations

import httpx

from pr_reviewer.config import get_settings
from pr_reviewer.control_plane.repository_policy import (
    register_installation,
    register_repository,
    revoke_installation,
)
from pr_reviewer.github.app_client import GITHUB_API_BASE_URL, GitHubAppClient
from pr_reviewer.github.installation_repositories import list_installation_repositories
from pr_reviewer.github.tokens import GitHubAppSettings

# new_permissions_accepted re-registers rather than mutating permissions: this table tracks
# whether we know about the installation at all, not what it is permitted to read.
_REGISTER_ACTIONS = {"created", "unsuspend", "new_permissions_accepted"}
_REVOKE_ACTIONS = {"deleted", "suspend"}


def _app_settings() -> GitHubAppSettings:
    settings = get_settings()
    return GitHubAppSettings(
        app_id=settings.github_app_id, private_key=settings.github_app_private_key
    )


def _sync_repositories(
    installation_id: int,
    *,
    http_client: httpx.Client | None = None,
    api_base_url: str = GITHUB_API_BASE_URL,
) -> None:
    # metadata:read is the minimum GitHub accepts for listing an installation's repositories --
    # this token is used for nothing else and is never persisted past this function. One concrete
    # httpx.Client, not two differently-typed Protocol handles, so a test's single mock transport
    # backs both the token mint (POST) and the repository listing (GET).
    app_client = GitHubAppClient(
        settings=_app_settings(), client=http_client, api_base_url=api_base_url
    )
    token = app_client.create_installation_token(
        installation_id, permissions={"metadata": "read"}
    ).token
    repositories = list_installation_repositories(
        installation_id,
        token_provider=lambda _: token,
        client=http_client,
        api_base_url=api_base_url,
    )
    for repository in repositories:
        register_repository(installation_id, repository.id, repository.full_name)


def handle_installation_event(
    payload: object,
    *,
    http_client: httpx.Client | None = None,
    api_base_url: str = GITHUB_API_BASE_URL,
) -> None:
    if not isinstance(payload, dict):
        return
    action = payload.get("action")
    installation = payload.get("installation")
    if not isinstance(action, str) or not isinstance(installation, dict):
        return
    installation_id = installation.get("id")
    account = installation.get("account")
    if not isinstance(installation_id, int) or not isinstance(account, dict):
        return
    account_login = account.get("login")
    if not isinstance(account_login, str):
        return

    if action in _REGISTER_ACTIONS:
        register_installation(installation_id, account_login)
        _sync_repositories(installation_id, http_client=http_client, api_base_url=api_base_url)
    elif action in _REVOKE_ACTIONS:
        revoke_installation(installation_id)


def handle_installation_repositories_event(payload: object) -> None:
    # Only "added" needs handling here: GitHub already gave us the full repository objects for
    # those, no extra API call needed. "removed" repositories are left registered on purpose --
    # nothing here deletes review history for a repository, and repository_policy has no delete
    # function; a future access check against a re-added-elsewhere repository is exactly the
    # transfer scenario test_repository_transfer_does_not_carry_data_to_the_new_installation
    # already covers.
    if not isinstance(payload, dict):
        return
    installation = payload.get("installation")
    added = payload.get("repositories_added")
    if not isinstance(installation, dict) or not isinstance(added, list):
        return
    installation_id = installation.get("id")
    if not isinstance(installation_id, int):
        return
    for repository in added:
        if not isinstance(repository, dict):
            continue
        repository_id = repository.get("id")
        full_name = repository.get("full_name")
        if isinstance(repository_id, int) and isinstance(full_name, str):
            register_repository(installation_id, repository_id, full_name)
