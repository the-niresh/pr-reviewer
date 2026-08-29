"""Outbound job claim, heartbeat, and acknowledgement (Runtime Task 3).

claim_job takes an AuthenticatedRunner and returns JobEnvelope or NoJob. Jobs for repositories
this runner is not assigned to, jobs for other tenants, and an empty queue are one answer.
Revoked runners also get NoJob here; the HTTP layer has already distinguished revoked_runner
from unknown_credential via authenticate_runner.
"""

from __future__ import annotations

import secrets
import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from pr_reviewer.contracts.runner import (
    AuthenticatedRunner,
    GitHubJobToken,
    JobAcknowledgement,
    JobBudget,
    JobEnvelope,
    JobProtocolDenied,
    LeaseState,
    NoJob,
    RunnerAuthDenied,
)
from pr_reviewer.control_plane.repository_policy import hash_runner_credential
from pr_reviewer.control_plane.runner_auth import authenticate_runner
from pr_reviewer.control_plane.token_broker import issue_job_token
from pr_reviewer.db.client import connection
from pr_reviewer.events.record_event import JsonObject, serialize_json_object
from pr_reviewer.jobs.claim_review_job import REVIEW_JOB_LEASE_INTERVAL
from pr_reviewer.observability.trace import HostedTrace, HostedTraceEvent

router = APIRouter(prefix="/api/runner", tags=["runner-jobs"])

INVALID_OR_EXPIRED: Literal["invalid_or_expired"] = "invalid_or_expired"


class _LeaseTokenBody(BaseModel):
    lease_token: str


class _AckBody(BaseModel):
    lease_token: str
    result: JobAcknowledgement


def _authenticate_bearer(authorization: str | None) -> AuthenticatedRunner:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer credential")
    credential = authorization.removeprefix("Bearer ")
    authenticated = authenticate_runner(credential)
    if isinstance(authenticated, RunnerAuthDenied):
        raise HTTPException(status_code=401, detail=authenticated.reason)
    return authenticated


@router.post("/jobs/claim")
def claim_jobs_route(
    authorization: str | None = Header(default=None),
) -> JobEnvelope | dict[str, str]:
    runner = _authenticate_bearer(authorization)
    result = claim_job(runner)
    if isinstance(result, NoJob):
        return {"status": "no_job"}
    return result


@router.post("/jobs/{job_id}/heartbeat")
def heartbeat_jobs_route(
    job_id: uuid.UUID,
    body: _LeaseTokenBody,
    authorization: str | None = Header(default=None),
) -> LeaseState:
    runner = _authenticate_bearer(authorization)
    return heartbeat_job(runner.runner_id, job_id, body.lease_token)


@router.post("/jobs/{job_id}/ack")
def acknowledge_jobs_route(
    job_id: uuid.UUID,
    body: _AckBody,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    runner = _authenticate_bearer(authorization)
    try:
        acknowledge_job(runner.runner_id, job_id, body.lease_token, body.result)
    except JobProtocolDenied as denied:
        raise HTTPException(status_code=409, detail=denied.reason) from denied
    return {"status": "ok"}


@router.post("/jobs/{job_id}/token")
def issue_job_token_route(
    job_id: uuid.UUID,
    body: _LeaseTokenBody,
    authorization: str | None = Header(default=None),
) -> GitHubJobToken:
    runner = _authenticate_bearer(authorization)
    try:
        return issue_job_token(runner.runner_id, job_id, body.lease_token)
    except JobProtocolDenied as denied:
        raise HTTPException(status_code=409, detail=denied.reason) from denied


def claim_job(runner: AuthenticatedRunner) -> JobEnvelope | NoJob:
    lease_token = secrets.token_urlsafe(32)
    lease_token_hash = hash_runner_credential(lease_token)

    with connection() as conn, conn.transaction():
        runner_row = conn.execute(
            "select revoked_at from runners where id = %s for update",
            (str(runner.runner_id),),
        ).fetchone()
        if runner_row is None or runner_row["revoked_at"] is not None:
            return NoJob()

        cursor = conn.execute(
            """
            with next_job as (
              select id
              from review_jobs
              where status = 'pending'
                and available_at <= now()
                and installation_id is not null
                and github_repository_id is not null
                and pull_request_number is not null
                and exists (
                  select 1
                  from repositories r
                  join repository_assignments a on a.repository_id = r.id
                  where r.installation_id = review_jobs.installation_id
                    and r.github_repository_id = review_jobs.github_repository_id
                    and a.runner_id = %s
                )
              order by available_at asc, created_at asc
              for update skip locked
              limit 1
            )
            update review_jobs
            set status = 'running',
                locked_by = %s,
                lease_token_hash = %s,
                locked_until = now() + %s::interval,
                attempts = attempts + 1,
                updated_at = now()
            where id = (select id from next_job)
            returning
              id,
              installation_id,
              github_repository_id,
              pull_request_number,
              base_sha,
              head_sha,
              policy_version,
              budget_max_tokens,
              budget_max_cost_usd,
              trace_id
            """,
            (
                str(runner.runner_id),
                str(runner.runner_id),
                lease_token_hash,
                REVIEW_JOB_LEASE_INTERVAL,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            return NoJob()

        return JobEnvelope(
            job_id=uuid.UUID(str(row["id"])),
            installation_id=int(row["installation_id"]),
            repository_id=int(row["github_repository_id"]),
            pull_request_number=int(row["pull_request_number"]),
            base_sha=str(row["base_sha"]),
            head_sha=str(row["head_sha"]),
            policy_version=str(row["policy_version"]),
            budget=JobBudget(
                max_tokens=int(row["budget_max_tokens"]),
                max_cost_usd=Decimal(str(row["budget_max_cost_usd"])),
            ),
            trace_id=uuid.UUID(str(row["trace_id"])),
            lease_token=lease_token,
        )


def heartbeat_job(runner_id: uuid.UUID, job_id: uuid.UUID, lease_token: str) -> LeaseState:
    token_hash = hash_runner_credential(lease_token)
    with connection() as conn, conn.transaction():
        cursor = conn.execute(
            """
            update review_jobs
            set locked_until = now() + %s::interval,
                updated_at = now()
            where id = %s
              and status = 'running'
              and locked_by = %s
              and lease_token_hash = %s
              and locked_until > now()
            returning id
            """,
            (REVIEW_JOB_LEASE_INTERVAL, str(job_id), str(runner_id), token_hash),
        )
        if cursor.rowcount == 1:
            return LeaseState(status="active")
        return LeaseState(status=INVALID_OR_EXPIRED)


def acknowledge_job(
    runner_id: uuid.UUID,
    job_id: uuid.UUID,
    lease_token: str,
    result: object,
) -> None:
    ack = (
        result
        if isinstance(result, JobAcknowledgement)
        else JobAcknowledgement.model_validate(result)
    )
    token_hash = hash_runner_credential(lease_token)
    with connection() as conn, conn.transaction():
        row = conn.execute(
            """
            select status, locked_by, lease_token_hash, locked_until
            from review_jobs
            where id = %s
            for update
            """,
            (str(job_id),),
        ).fetchone()
        if row is None:
            raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)
        if str(row["locked_by"]) != str(runner_id) or str(row["lease_token_hash"]) != token_hash:
            raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)
        if row["status"] in {"succeeded", "failed"}:
            return
        if row["status"] != "running" or row["locked_until"] is None:
            raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)
        now_row = conn.execute("select now() as now").fetchone()
        assert now_row is not None
        if row["locked_until"] <= now_row["now"]:
            raise JobProtocolDenied(reason=INVALID_OR_EXPIRED)

        next_status = "succeeded" if ack.terminal_state == "succeeded" else "failed"
        conn.execute(
            """
            update review_jobs
            set status = %s,
                last_error = %s,
                locked_until = null,
                updated_at = now()
            where id = %s
            """,
            (next_status, ack.error_class, str(job_id)),
        )
        payload: JsonObject = {
            "terminal_state": ack.terminal_state,
            "input_tokens": ack.input_tokens,
            "output_tokens": ack.output_tokens,
            "cost_usd": str(ack.cost_usd),
            "latency_ms": ack.latency_ms,
            "local_result_hash": ack.local_result_hash,
        }
        if ack.error_class is not None:
            payload["error_class"] = ack.error_class
        conn.execute(
            """
            insert into agent_events (review_job_id, event_type, payload)
            values (%s, %s, %s::jsonb)
            """,
            (
                str(job_id),
                "review_job_acknowledged",
                serialize_json_object(payload),
            ),
        )


def fetch_hosted_trace(job_id: str) -> HostedTrace | None:
    """The hosted half of Runtime Task 5A's trace join.

    review_jobs.id (the job_id every hosted and local row this job touches is scoped by) and
    review_jobs.trace_id are 1:1 -- enqueue_review_job mints a fresh row and a fresh trace_id
    every time, including when it supersedes an older one -- so agent_events needs no trace_id
    column of its own; review_job_id = job_id already scopes it correctly, and trace_id is read
    once from review_jobs for display and for TraceIntegrityError's cross-store check.

    None means review_jobs has no row for job_id, or that row has never been given a trace_id (the
    minimal insert path for a webhook with no identifiable pull request). It is distinct from a
    HostedTrace with zero events, which means the job exists but nothing has been recorded for it
    yet. A connectivity or query failure is never converted to None here -- only genuine absence
    of the job is; reconstruct_trace's "which side is missing" report must not be able to mean
    "the database was briefly unreachable" by accident.
    """
    with connection() as conn:
        job_row = conn.execute(
            "select trace_id from review_jobs where id = %s", (job_id,)
        ).fetchone()
        if job_row is None or job_row["trace_id"] is None:
            return None
        trace_id = str(job_row["trace_id"])

        rows = conn.execute(
            """
            select sequence, event_type, payload, created_at
            from agent_events
            where review_job_id = %s
            order by sequence asc
            """,
            (job_id,),
        ).fetchall()

    events = tuple(
        HostedTraceEvent(
            sequence=int(row["sequence"]),
            kind=str(row["event_type"]),
            payload=row["payload"],
            created_at=row["created_at"],
        )
        for row in rows
    )
    return HostedTrace(trace_id=trace_id, events=events)
