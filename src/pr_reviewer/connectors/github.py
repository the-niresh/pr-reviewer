"""Wrap existing GitHub token-mint and PR-fetch calls. Signatures of the originals stay put."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable

import httpx
from psycopg import Connection

from pr_reviewer.connectors.audit import ConnectorAudit
from pr_reviewer.connectors.base import ConnectorResult
from pr_reviewer.contracts import PullRequestRef
from pr_reviewer.db.client import Row, connection
from pr_reviewer.github.app_client import GitHubAppClient, InstallationToken
from pr_reviewer.github.post_review import PostedReview, ReviewSubmission
from pr_reviewer.github.pull_request import (
    HttpClient,
    InstallationTokenProvider,
    PullRequestSnapshot,
)
from pr_reviewer.github.pull_request import (
    fetch_pull_request as fetch_github_pull_request,
)

RecordConnectorRun = Callable[[Connection[Row], ConnectorAudit, str | None], str]


def _payload_hash(
    *,
    operation: str,
    status_code: int | None,
    request_bytes: int,
    response_bytes: int,
) -> str:
    material = f"{operation}:{status_code}:{request_bytes}:{response_bytes}".encode()
    return hashlib.sha256(material).hexdigest()


def _json_bytes(payload: object) -> int:
    return len(json.dumps(payload, separators=(",", ":"), default=str).encode())


def _maybe_record(
    record: RecordConnectorRun | None,
    audit: ConnectorAudit,
    review_job_id: str | None,
) -> None:
    if record is None:
        return
    with connection() as conn:
        record(conn, audit, review_job_id)


def create_installation_token(
    client: GitHubAppClient,
    installation_id: int,
    *,
    repository_ids: list[int] | None = None,
    permissions: dict[str, str] | None = None,
    trace_id: uuid.UUID,
    review_job_id: str | None = None,
    record: RecordConnectorRun | None = None,
) -> ConnectorResult[InstallationToken]:
    body: dict[str, object] = {}
    if repository_ids is not None:
        body["repository_ids"] = repository_ids
    if permissions is not None:
        body["permissions"] = permissions
    request_bytes = _json_bytes(body) if body else 0
    started = time.perf_counter()
    try:
        token = client.create_installation_token(
            installation_id,
            repository_ids=repository_ids,
            permissions=permissions,
        )
    except httpx.TimeoutException:
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        audit = ConnectorAudit(
            trace_id=trace_id,
            connector="github",
            operation="create_installation_token",
            request_bytes=request_bytes,
            response_bytes=0,
            payload_hash=_payload_hash(
                operation="create_installation_token",
                status_code=None,
                request_bytes=request_bytes,
                response_bytes=0,
            ),
        )
        _maybe_record(record, audit, review_job_id)
        return ConnectorResult(
            connector="github",
            operation="create_installation_token",
            outcome="error",
            value=None,
            error_kind="timeout",
            status_code=None,
            latency_ms=latency_ms,
            request_bytes=request_bytes,
            response_bytes=0,
        )
    except httpx.HTTPStatusError as error:
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        status_code = error.response.status_code
        response_bytes = len(error.response.content)
        audit = ConnectorAudit(
            trace_id=trace_id,
            connector="github",
            operation="create_installation_token",
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            payload_hash=_payload_hash(
                operation="create_installation_token",
                status_code=status_code,
                request_bytes=request_bytes,
                response_bytes=response_bytes,
            ),
        )
        _maybe_record(record, audit, review_job_id)
        return ConnectorResult(
            connector="github",
            operation="create_installation_token",
            outcome="error",
            value=None,
            error_kind="http_error",
            status_code=status_code,
            latency_ms=latency_ms,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
        )
    latency_ms = max(0, int((time.perf_counter() - started) * 1000))
    # Never hash or count the token. expires_at alone proves a response arrived.
    response_bytes = _json_bytes({"expires_at": token.expires_at.isoformat()})
    audit = ConnectorAudit(
        trace_id=trace_id,
        connector="github",
        operation="create_installation_token",
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        payload_hash=_payload_hash(
            operation="create_installation_token",
            status_code=201,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
        ),
    )
    _maybe_record(record, audit, review_job_id)
    return ConnectorResult(
        connector="github",
        operation="create_installation_token",
        outcome="success",
        value=token,
        error_kind=None,
        status_code=201,
        latency_ms=latency_ms,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
    )


def fetch_pull_request(
    ref: PullRequestRef,
    *,
    installation_id: int,
    token_provider: InstallationTokenProvider,
    client: HttpClient | None = None,
    api_base_url: str = "https://api.github.com",
    timeout_seconds: float = 10.0,
    trace_id: uuid.UUID | None = None,
    review_job_id: str | None = None,
    record: RecordConnectorRun | None = None,
) -> ConnectorResult[PullRequestSnapshot]:
    request_bytes = len(f"/repos/{ref.owner}/{ref.repository}/pulls/{ref.number}".encode())
    started = time.perf_counter()
    try:
        snapshot = fetch_github_pull_request(
            ref,
            installation_id=installation_id,
            token_provider=token_provider,
            client=client,
            api_base_url=api_base_url,
            timeout_seconds=timeout_seconds,
        )
    except httpx.TimeoutException:
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        _record_fetch(
            trace_id=trace_id,
            review_job_id=review_job_id,
            record=record,
            request_bytes=request_bytes,
            response_bytes=0,
            status_code=None,
        )
        return ConnectorResult(
            connector="github",
            operation="fetch_pull_request",
            outcome="error",
            value=None,
            error_kind="timeout",
            status_code=None,
            latency_ms=latency_ms,
            request_bytes=request_bytes,
            response_bytes=0,
        )
    except httpx.HTTPStatusError as error:
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        status_code = error.response.status_code
        response_bytes = len(error.response.content)
        _record_fetch(
            trace_id=trace_id,
            review_job_id=review_job_id,
            record=record,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            status_code=status_code,
        )
        return ConnectorResult(
            connector="github",
            operation="fetch_pull_request",
            outcome="error",
            value=None,
            error_kind="http_error",
            status_code=status_code,
            latency_ms=latency_ms,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
        )
    latency_ms = max(0, int((time.perf_counter() - started) * 1000))
    # Paths and SHAs only. Never title, body, or patch.
    response_bytes = _json_bytes(
        {
            "file_count": len(snapshot.files),
            "paths": [file.path for file in snapshot.files],
            "base_sha": snapshot.base_sha,
            "head_sha": snapshot.head_sha,
        }
    )
    _record_fetch(
        trace_id=trace_id,
        review_job_id=review_job_id,
        record=record,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        status_code=200,
    )
    return ConnectorResult(
        connector="github",
        operation="fetch_pull_request",
        outcome="success",
        value=snapshot,
        error_kind=None,
        status_code=200,
        latency_ms=latency_ms,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
    )


def create_pull_request_review(
    submission: ReviewSubmission,
    *,
    ref: PullRequestRef,
    token: str,
    client: httpx.Client | None = None,
    api_base_url: str = "https://api.github.com",
    timeout_seconds: float = 10.0,
    trace_id: uuid.UUID | None = None,
    review_job_id: str | None = None,
    record: RecordConnectorRun | None = None,
) -> ConnectorResult[PostedReview]:
    """Post a review that is already public-shaped. Finding objects are not accepted."""
    payload = {
        "commit_id": submission.commit_id,
        "event": "COMMENT",
        "body": submission.body,
        "comments": [
            {
                "path": comment.path,
                "line": comment.line,
                "side": comment.side,
                "body": comment.body,
            }
            for comment in submission.comments
        ],
    }
    request_bytes = _json_bytes(payload)
    started = time.perf_counter()
    http_client = client or httpx.Client()
    try:
        response = http_client.post(
            f"{api_base_url}/repos/{ref.owner}/{ref.repository}/pulls/{ref.number}/reviews",
            headers={
                "accept": "application/vnd.github+json",
                "authorization": f"Bearer {token}",
                "x-github-api-version": "2022-11-28",
            },
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except httpx.TimeoutException:
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        _record_post(
            trace_id=trace_id,
            review_job_id=review_job_id,
            record=record,
            request_bytes=request_bytes,
            response_bytes=0,
            status_code=None,
        )
        return ConnectorResult(
            connector="github",
            operation="create_pull_request_review",
            outcome="error",
            value=None,
            error_kind="timeout",
            status_code=None,
            latency_ms=latency_ms,
            request_bytes=request_bytes,
            response_bytes=0,
        )
    except httpx.HTTPStatusError as error:
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        status_code = error.response.status_code
        response_bytes = len(error.response.content)
        _record_post(
            trace_id=trace_id,
            review_job_id=review_job_id,
            record=record,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            status_code=status_code,
        )
        return ConnectorResult(
            connector="github",
            operation="create_pull_request_review",
            outcome="error",
            value=None,
            error_kind="http_error",
            status_code=status_code,
            latency_ms=latency_ms,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
        )
    latency_ms = max(0, int((time.perf_counter() - started) * 1000))
    body = response.json()
    review_id = str(body.get("id", ""))
    comment_ids = tuple(str(item.get("id", "")) for item in body.get("comments") or ())
    status_code = response.status_code
    response_bytes = _json_bytes({"id": review_id, "comment_count": len(comment_ids)})
    _record_post(
        trace_id=trace_id,
        review_job_id=review_job_id,
        record=record,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        status_code=status_code,
    )
    return ConnectorResult(
        connector="github",
        operation="create_pull_request_review",
        outcome="success",
        value=PostedReview(
            github_review_id=review_id,
            comment_ids=comment_ids,
            response_status=status_code,
            body=submission.body,
            comments=submission.comments,
        ),
        error_kind=None,
        status_code=status_code,
        latency_ms=latency_ms,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
    )


def _record_fetch(
    *,
    trace_id: uuid.UUID | None,
    review_job_id: str | None,
    record: RecordConnectorRun | None,
    request_bytes: int,
    response_bytes: int,
    status_code: int | None,
) -> None:
    if record is None or trace_id is None:
        return
    audit = ConnectorAudit(
        trace_id=trace_id,
        connector="github",
        operation="fetch_pull_request",
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        payload_hash=_payload_hash(
            operation="fetch_pull_request",
            status_code=status_code,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
        ),
    )
    _maybe_record(record, audit, review_job_id)


def _record_post(
    *,
    trace_id: uuid.UUID | None,
    review_job_id: str | None,
    record: RecordConnectorRun | None,
    request_bytes: int,
    response_bytes: int,
    status_code: int | None,
) -> None:
    if record is None or trace_id is None:
        return
    audit = ConnectorAudit(
        trace_id=trace_id,
        connector="github",
        operation="create_pull_request_review",
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        payload_hash=_payload_hash(
            operation="create_pull_request_review",
            status_code=status_code,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
        ),
    )
    _maybe_record(record, audit, review_job_id)
