from __future__ import annotations

from dataclasses import dataclass
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
    ) -> httpx.Response: ...


@dataclass(frozen=True)
class GitHubAppClient:
    settings: GitHubAppSettings
    api_base_url: str = GITHUB_API_BASE_URL
    timeout_seconds: float = 10.0
    client: HttpClient | None = None

    def create_installation_token(self, installation_id: int) -> str:
        http_client = self.client or httpx.Client()
        response = http_client.post(
            f"{self.api_base_url}/app/installations/{installation_id}/access_tokens",
            headers={
                "accept": "application/vnd.github+json",
                "authorization": f"Bearer {build_app_jwt(self.settings)}",
                "x-github-api-version": "2022-11-28",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("GitHub installation token response did not include token")
        return token
