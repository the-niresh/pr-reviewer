"""Short-lived GitHub token broker (Runtime Task 4).

issue_job_token exchanges a valid job lease for an installation token scoped to that job's
repository and to read-only permissions. There is no second denial type here: a caller presenting
a lease that is wrong, expired, superseded, already finished, or for a repository they are no
longer assigned to reuses JobProtocolDenied("invalid_or_expired"), the same reason heartbeat_job
and acknowledge_job already use, for the same reason (see control_plane/runner_jobs.py's
docstring). Telling those apart would let a caller probe job or repository state it should not
see.

Two checks gate every mint:
1. The same lease-validity check acknowledge_job performs: this job exists, is locked by this
   runner with this lease_token_hash, is still 'running', and locked_until has not passed. This
   alone covers wrong runner, wrong lease, expired lease, a job already superseded by a newer head
   SHA, and replay after the job already finished.
2. A live re-check of authorize_repository (Task 1, unchanged) -- not a trust of whatever check
   passed when the job was originally claimed. A repository can be reassigned, or an installation
   revoked, after the runner already holds a valid, unexpired lease; issuing a token at that point
   would hand out GitHub access the runner is no longer supposed to have.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pr_reviewer.config import get_settings
from pr_reviewer.contracts.runner import AuthorizationDenied, GitHubJobToken, JobProtocolDenied
from pr_reviewer.control_plane.repository_policy import authorize_repository, hash_runner_credential
from pr_reviewer.db.client import connection
from pr_reviewer.github.app_client import GitHubAppClient
from pr_reviewer.github.tokens import GitHubAppSettings

INVALID_OR_EXPIRED: Literal["invalid_or_expired"] = "invalid_or_expired"

# pull_requests:read for PR metadata and files, contents:read for repository file content beyond
# a diff hunk. No write, no admin: this is the full read set fetch_job_snapshot uses.
TOKEN_PERMISSIONS: dict[str, str] = {"contents": "read", "pull_requests": "read"}


def _app_settings() -> GitHubAppSettings:
    settings = get_settings()
    return GitHubAppSettings(
        app_id=settings.github_app_id,
        private_key=settings.github_app_private_key,
    )


def issue_job_token(
    runner_id: uuid.UUID,
    job_id: uuid.UUID,
    lease_token: str,
    *,
    app_client: GitHubAppClient | None = None,
) -> GitHubJobToken:
    token_hash = hash_runner_credential(lease_token)

    with connection() as conn:
        row = conn.execute(
            """
            select status, locked_by, lease_token_hash, locked_until, installation_id,
                   github_repository_id, now() as now
            from review_jobs
            where id = %s
            """,
            (str(job_id),),
        ).fetchone()
        if row is None:
            raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)
        if str(row["locked_by"]) != str(runner_id) or str(row["lease_token_hash"]) != token_hash:
            raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)
        if row["status"] != "running" or row["locked_until"] is None:
            raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)
        if row["locked_until"] <= row["now"]:
            raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)
        installation_id = row["installation_id"]
        github_repository_id = row["github_repository_id"]

    if installation_id is None or github_repository_id is None:
        raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)

    authorization = authorize_repository(int(installation_id), int(github_repository_id), runner_id)
    if isinstance(authorization, AuthorizationDenied):
        raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)

    client = app_client or GitHubAppClient(settings=_app_settings())
    minted = client.create_installation_token(
        int(installation_id),
        repository_ids=[int(github_repository_id)],
        permissions=TOKEN_PERMISSIONS,
    )
    return GitHubJobToken(
        token=minted.token,
        github_repository_id=int(github_repository_id),
        expires_at=minted.expires_at,
    )
