from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

from pr_reviewer.contracts import PullRequestRef

GitHubFileStatus = Literal["added", "modified", "removed", "renamed"]


class GitHubBranchRef(TypedDict):
    sha: str


class GitHubPullRequestBody(TypedDict):
    base: GitHubBranchRef
    head: GitHubBranchRef
    title: str
    body: str | None


class GitHubPullRequestFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str = Field(min_length=1)
    status: str = Field(min_length=1)
    patch: str | None = None
    previous_filename: str | None = None


@dataclass(frozen=True)
class GitHubPullRequestResponse:
    pull_request: GitHubPullRequestBody
    files: list[GitHubPullRequestFile]


class PullRequestFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1)
    status: GitHubFileStatus
    patch: str
    previous_path: str | None = None


class PullRequestSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_owner: str = Field(min_length=1)
    repo_name: str = Field(min_length=1)
    number: int = Field(gt=0)
    base_sha: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)
    title: str
    body: str
    files: list[PullRequestFile]


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response: ...


class InstallationTokenProvider(Protocol):
    def create_installation_token(self, installation_id: int) -> str: ...


def normalize_github_pull_request(
    ref: PullRequestRef,
    response: GitHubPullRequestResponse,
) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        repo_owner=ref.owner,
        repo_name=ref.repository,
        number=ref.number,
        base_sha=response.pull_request["base"]["sha"],
        head_sha=response.pull_request["head"]["sha"],
        title=response.pull_request["title"],
        body=response.pull_request["body"] or "",
        files=[
            PullRequestFile(
                path=file.filename,
                status=normalize_file_status(file.status),
                patch=file.patch or "",
                previous_path=file.previous_filename,
            )
            for file in response.files
        ],
    )


def normalize_file_status(status: str) -> GitHubFileStatus:
    if status in {"added", "modified", "removed", "renamed"}:
        return cast(GitHubFileStatus, status)
    raise ValueError(f"Unsupported GitHub file status: {status}")


def fetch_pull_request(
    ref: PullRequestRef,
    *,
    installation_id: int,
    token_provider: InstallationTokenProvider,
    client: HttpClient | None = None,
    api_base_url: str = "https://api.github.com",
    timeout_seconds: float = 10.0,
) -> PullRequestSnapshot:
    http_client = client or httpx.Client()
    token = token_provider.create_installation_token(installation_id)
    headers = {
        "accept": "application/vnd.github+json",
        "authorization": f"Bearer {token}",
        "x-github-api-version": "2022-11-28",
    }
    pull_request_response = http_client.get(
        f"{api_base_url}/repos/{ref.owner}/{ref.repository}/pulls/{ref.number}",
        headers=headers,
        timeout=timeout_seconds,
    )
    pull_request_response.raise_for_status()
    files = fetch_all_pull_request_files(
        http_client=http_client,
        url=f"{api_base_url}/repos/{ref.owner}/{ref.repository}/pulls/{ref.number}/files",
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    return normalize_github_pull_request(
        ref,
        GitHubPullRequestResponse(
            pull_request=cast(GitHubPullRequestBody, pull_request_response.json()),
            files=files,
        ),
    )


def fetch_all_pull_request_files(
    *,
    http_client: HttpClient,
    url: str,
    headers: dict[str, str],
    timeout_seconds: float,
) -> list[GitHubPullRequestFile]:
    files: list[GitHubPullRequestFile] = []
    next_url: str | None = url

    while next_url is not None:
        response = http_client.get(next_url, headers=headers, timeout=timeout_seconds)
        response.raise_for_status()
        files.extend(GitHubPullRequestFile.model_validate(file) for file in response.json())
        next_url = get_next_link(response)

    return files


def get_next_link(response: httpx.Response) -> str | None:
    next_link = response.links.get("next")
    if next_link is None:
        return None
    url = next_link.get("url")
    return url if isinstance(url, str) and url else None
