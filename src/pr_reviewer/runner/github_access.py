"""Runner-side GitHub fetch (Runtime Task 4).

fetch_job_snapshot takes a JobEnvelope and a GitHubJobToken already minted by the control plane's
token broker, and calls GitHub directly from the runner's own machine. This module has no path to
the GitHub App private key at all: it never imports the hosted control plane or database packages
(test_runner_and_local_store_boundary in tests/test_package_boundaries.py enforces this at the
import-graph level), and it never constructs the App-level settings type or calls the
installation-token-minting method -- only the control plane can mint a token, this module only
spends one it was already handed.
"""

from __future__ import annotations

from pr_reviewer.contracts.runner import GitHubJobToken, JobEnvelope
from pr_reviewer.github.pull_request import (
    HttpClient,
    PullRequestSnapshot,
    fetch_pull_request_by_repository_id,
)


def fetch_job_snapshot(
    job: JobEnvelope,
    token: GitHubJobToken,
    *,
    client: HttpClient | None = None,
    api_base_url: str = "https://api.github.com",
    timeout_seconds: float = 10.0,
) -> PullRequestSnapshot:
    if token.github_repository_id != job.repository_id:
        raise ValueError(
            "token repository does not match job repository: "
            f"token is scoped to {token.github_repository_id}, job names {job.repository_id}"
        )

    return fetch_pull_request_by_repository_id(
        job.repository_id,
        job.pull_request_number,
        token=token.token,
        client=client,
        api_base_url=api_base_url,
        timeout_seconds=timeout_seconds,
    )
