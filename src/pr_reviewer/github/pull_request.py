from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

from pr_reviewer.contracts.github import OmissionReason, PullRequestRef, RepositoryIdentity

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
    patch: str | None = None
    previous_path: str | None = None
    truncated: bool = False
    binary: bool = False
    omission_reason: OmissionReason | None = None


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
    identity: RepositoryIdentity | None = None
    draft: bool = False


class RepositoryFetcher(Protocol):
    def recover_patch(
        self,
        identity: RepositoryIdentity,
        path: str,
        *,
        base_sha: str,
        head_sha: str,
    ) -> str | None: ...


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
                patch=file.patch,
                previous_path=file.previous_filename,
            )
            for file in response.files
        ],
    )


def normalize_file_status(status: str) -> GitHubFileStatus:
    if status in {"added", "modified", "removed", "renamed"}:
        return cast(GitHubFileStatus, status)
    raise ValueError(f"Unsupported GitHub file status: {status}")


def ensure_complete_diff(
    snapshot: PullRequestSnapshot,
    fetcher: RepositoryFetcher,
) -> PullRequestSnapshot:
    """Fill omitted patches via fetcher, or record a closed-set OmissionReason.

    A missing GitHub patch is never an unchanged file. A clone bound (timeout or
    size) is recorded as an omission so the rest of the review can continue.
    """
    completed: list[PullRequestFile] = []
    for file in snapshot.files:
        completed.append(_complete_file(snapshot, file, fetcher))
    return snapshot.model_copy(update={"files": completed})


def _complete_file(
    snapshot: PullRequestSnapshot,
    file: PullRequestFile,
    fetcher: RepositoryFetcher,
) -> PullRequestFile:
    if file.binary:
        return file.model_copy(update={"omission_reason": OmissionReason.BINARY, "patch": None})
    if file.truncated:
        return file.model_copy(update={"omission_reason": OmissionReason.PATCH_TRUNCATED_BY_GITHUB})
    if file.patch:
        return file
    recovered = _recover_or_omit(snapshot, file, fetcher)
    if recovered is None:
        return file.model_copy(
            update={"patch": None, "omission_reason": OmissionReason.PATCH_OMITTED_BY_GITHUB}
        )
    if isinstance(recovered, OmissionReason):
        return file.model_copy(update={"patch": None, "omission_reason": recovered})
    return file.model_copy(update={"patch": recovered, "omission_reason": None})


def _recover_or_omit(
    snapshot: PullRequestSnapshot,
    file: PullRequestFile,
    fetcher: RepositoryFetcher,
) -> str | OmissionReason | None:
    if snapshot.identity is None:
        return None
    try:
        return fetcher.recover_patch(
            snapshot.identity,
            file.path,
            base_sha=snapshot.base_sha,
            head_sha=snapshot.head_sha,
        )
    except Exception as error:
        reason = _omission_for_fetcher_error(error)
        if reason is not None:
            return reason
        raise


def _omission_for_fetcher_error(error: BaseException) -> OmissionReason | None:
    name = type(error).__name__
    if name == "CloneTimeout":
        return OmissionReason.CLONE_TIMEOUT
    if name == "CloneSizeLimit":
        return OmissionReason.FILE_SIZE_LIMIT
    return None


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


def fetch_pull_request_by_repository_id(
    repository_id: int,
    pull_request_number: int,
    *,
    token: str,
    client: HttpClient | None = None,
    api_base_url: str = "https://api.github.com",
    timeout_seconds: float = 10.0,
) -> PullRequestSnapshot:
    """Fetch a pull request using GitHub's numeric-repository-id route.

    JobEnvelope only carries a numeric github_repository_id, never an owner/name string, and the
    runner has no database to resolve one. /repositories/{id}/pulls/{number} takes the same
    numeric id GitHub already issued at webhook delivery, so no extra lookup exists to get wrong.
    owner and name come back out of the response body itself (base.repo), not from a caller-
    supplied ref, because there is no ref to trust here.
    """
    http_client = client or httpx.Client()
    headers = {
        "accept": "application/vnd.github+json",
        "authorization": f"Bearer {token}",
        "x-github-api-version": "2022-11-28",
    }
    pull_request_response = http_client.get(
        f"{api_base_url}/repositories/{repository_id}/pulls/{pull_request_number}",
        headers=headers,
        timeout=timeout_seconds,
    )
    pull_request_response.raise_for_status()
    body = cast(dict[str, Any], pull_request_response.json())
    files = fetch_all_pull_request_files(
        http_client=http_client,
        url=f"{api_base_url}/repositories/{repository_id}/pulls/{pull_request_number}/files",
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    return normalize_github_pull_request_by_repository_id(pull_request_number, body, files)


def normalize_github_pull_request_by_repository_id(
    pull_request_number: int,
    body: dict[str, Any],
    files: list[GitHubPullRequestFile],
) -> PullRequestSnapshot:
    repo = body["base"]["repo"]
    return PullRequestSnapshot(
        repo_owner=str(repo["owner"]["login"]),
        repo_name=str(repo["name"]),
        number=pull_request_number,
        base_sha=str(body["base"]["sha"]),
        head_sha=str(body["head"]["sha"]),
        title=str(body["title"]),
        body=str(body["body"] or ""),
        files=[
            PullRequestFile(
                path=file.filename,
                status=normalize_file_status(file.status),
                patch=file.patch,
                previous_path=file.previous_filename,
            )
            for file in files
        ],
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
