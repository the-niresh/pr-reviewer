"""Mint GitHub installation tokens for repositories assigned to one runner."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pr_reviewer.config import get_settings
from pr_reviewer.db.client import connection
from pr_reviewer.github.app_client import GitHubAppClient
from pr_reviewer.github.tokens import GitHubAppSettings

RunnerInstallationTokenDenialReason = Literal["installation_not_assigned"]

# GitHub App installation tokens have a GitHub-controlled one-hour maximum lifetime. GitHub does
# not accept a requested shorter expiry, so this service never caches or extends the token and
# returns GitHub's expiry exactly as issued.
INSTALLATION_TOKEN_PERMISSIONS: dict[str, str] = {"contents": "read", "pull_requests": "read"}


class RunnerInstallationTokenDenied(Exception):
    def __init__(self, reason: RunnerInstallationTokenDenialReason) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class RunnerInstallationToken:
    token: str
    expires_at: datetime


def _app_settings() -> GitHubAppSettings:
    settings = get_settings()
    return GitHubAppSettings(
        app_id=settings.github_app_id,
        private_key=settings.github_app_private_key,
    )


def issue_runner_installation_token(
    runner_id: uuid.UUID,
    installation_id: int,
    *,
    app_client: GitHubAppClient | None = None,
) -> RunnerInstallationToken:
    """Mint a token for only the requested installation's assigned repositories.

    A runner holding a credential is not entitled to learn whether a different installation
    exists or which runner owns it. Every no-assignment result therefore has the same denial.
    """
    with connection() as conn:
        rows = conn.execute(
            """
            select r.github_repository_id
            from repositories r
            join repository_assignments a on a.repository_id = r.id
            join installations i on i.id = r.installation_id
            where a.runner_id = %s
              and r.installation_id = %s
              and i.revoked_at is null
            order by r.github_repository_id
            """,
            (str(runner_id), installation_id),
        ).fetchall()

    repository_ids = [int(row["github_repository_id"]) for row in rows]
    if not repository_ids:
        raise RunnerInstallationTokenDenied(reason="installation_not_assigned")

    client = app_client or GitHubAppClient(settings=_app_settings())
    minted = client.create_installation_token(
        installation_id,
        repository_ids=repository_ids,
        permissions=INSTALLATION_TOKEN_PERMISSIONS,
    )
    return RunnerInstallationToken(token=minted.token, expires_at=minted.expires_at)
