from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from pr_reviewer.github.tokens import GitHubAppSettings, build_app_jwt

GITHUB_API_BASE_URL = "https://api.github.com"


class HttpClient(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        json: dict[str, object] | None = None,
    ) -> httpx.Response: ...


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class GitHubAppClient:
    settings: GitHubAppSettings
    api_base_url: str = GITHUB_API_BASE_URL
    timeout_seconds: float = 10.0
    client: HttpClient | None = None

    def create_installation_token(
        self,
        installation_id: int,
        *,
        repository_ids: list[int] | None = None,
        permissions: dict[str, str] | None = None,
    ) -> InstallationToken:
        """Mint an installation token.

        repository_ids and permissions are sent as the request body whenever a caller supplies
        them, exactly as given: this method does not widen or drop scope on its own. Omitting
        both mints an unscoped token with the installation's full permissions across every
        repository it covers, which is why every caller that mints a token for one job must pass
        both (see control_plane.token_broker.issue_job_token).
        """
        http_client = self.client or httpx.Client()
        body: dict[str, object] = {}
        if repository_ids is not None:
            body["repository_ids"] = repository_ids
        if permissions is not None:
            body["permissions"] = permissions
        response = http_client.post(
            f"{self.api_base_url}/app/installations/{installation_id}/access_tokens",
            headers={
                "accept": "application/vnd.github+json",
                "authorization": f"Bearer {build_app_jwt(self.settings)}",
                "x-github-api-version": "2022-11-28",
            },
            timeout=self.timeout_seconds,
            json=body or None,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("GitHub installation token response did not include token")
        expires_at_raw = data.get("expires_at")
        if not isinstance(expires_at_raw, str) or not expires_at_raw:
            raise RuntimeError("GitHub installation token response did not include expires_at")
        expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
        return InstallationToken(token=token, expires_at=expires_at)
