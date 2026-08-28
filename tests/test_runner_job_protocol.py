"""Tests for outbound job claim, heartbeat, and acknowledgement (Runtime Task 3).

A runner presenting a credential already possesses evidence of prior issuance, so unknown vs
revoked stay distinguishable at the HTTP auth layer, the same way Task 2's authenticate_runner
does. After that, claim_job takes an AuthenticatedRunner and may only return JobEnvelope or
NoJob. "No pending job", "a job exists for a repository you are not assigned to", and "a job
exists for another tenant" are not things that runner is authorised to tell apart, so they are
one answer: NoJob. Same rule as PairingDenialReason and SignInDenialReason
(docs/phases/phase-2-security-design-gate.md, section 6).

Heartbeat and acknowledge take a lease_token. Wrong token, expired lease, unknown job, and a job
held by a different runner collapse to one status: invalid_or_expired. Telling those apart would
let a caller probe job IDs they should not see.

This task is also the first time src/pr_reviewer/runner/ exists. Creating it will fail
test_guarded_package_inventory_matches_snapshot. That failure is intended. The snapshot is not
the boundary: test_runner_and_local_store_boundary is. Do not update EXPECTED_EXISTING_PACKAGES
without watching that test fail when runner/client.py imports pr_reviewer.db.client.
"""

from __future__ import annotations

import hashlib
import inspect
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pr_reviewer.contracts.runner import (
    AuthenticatedRunner,
    RunnerCredential,
    VerifiedInstallationAccess,
)
from pr_reviewer.control_plane.repository_policy import revoke_runner
from pr_reviewer.db.client import connection
from pr_reviewer.jobs import enqueue_review_job
from pr_reviewer.web.app import app

VerifiedAccessFactory = Callable[[int, int, dict[int, str] | None], VerifiedInstallationAccess]

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
NEWER_HEAD_SHA = "c" * 40


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def insert_installation(installation_id: int) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (installation_id, "acme"),
        )


def pair_runner_assigned_to_repo(
    installation_id: int,
    github_repository_id: int,
    make_verified_installation_access: VerifiedAccessFactory,
    device_name: str = "laptop",
    repo_name: str = "widgets",
) -> RunnerCredential:
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    verifier = f"verifier-for-{device_name}"
    challenge_result = create_pairing_code(device_name, sha256_hex(verifier))
    access = make_verified_installation_access(
        42, installation_id, {github_repository_id: repo_name}
    )
    approve_pairing(challenge_result.code, access, [github_repository_id])
    result = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(result, RunnerCredential)
    return result


def authenticate(credential: str) -> AuthenticatedRunner:
    from pr_reviewer.control_plane.runner_auth import authenticate_runner

    result = authenticate_runner(credential)
    assert isinstance(result, AuthenticatedRunner)
    return result


def enqueue_pull_request_job(
    delivery_id: str,
    installation_id: int,
    github_repository_id: int,
    pull_request_number: int = 12,
    base_sha: str = BASE_SHA,
    head_sha: str = HEAD_SHA,
    repo_name: str = "widgets",
) -> None:
    payload = {
        "action": "opened",
        "installation": {"id": installation_id},
        "repository": {"id": github_repository_id, "name": repo_name},
        "pull_request": {
            "number": pull_request_number,
            "base": {"sha": base_sha},
            "head": {"sha": head_sha},
        },
    }
    assert enqueue_review_job(delivery_id, "pull_request", payload) == "enqueued"


def acknowledgement(
    *,
    terminal_state: str = "succeeded",
    error_class: str | None = None,
    input_tokens: int = 10,
    output_tokens: int = 20,
    cost_usd: Decimal = Decimal("0.010000"),
    latency_ms: int = 1500,
    local_result_hash: str | None = None,
) -> object:
    from pr_reviewer.contracts.runner import JobAcknowledgement

    return JobAcknowledgement(
        terminal_state=terminal_state,
        error_class=error_class,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        local_result_hash=local_result_hash or ("d" * 64),
    )


def test_claim_route_rejects_missing_credential() -> None:
    client = TestClient(app)
    response = client.post("/api/runner/jobs/claim")
    assert response.status_code == 401


def test_claim_route_rejects_unknown_credential() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/runner/jobs/claim",
        headers={"authorization": "Bearer never-issued"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "unknown_credential"


def test_revoked_runner_cannot_claim_a_queued_job(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import NoJob, RunnerAuthDenied
    from pr_reviewer.control_plane.runner_auth import authenticate_runner
    from pr_reviewer.control_plane.runner_jobs import claim_job

    installation_id = 7001
    github_repository_id = 81001
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-revoked", installation_id, github_repository_id)
    revoke_runner(credential.runner_id)

    auth = authenticate_runner(credential.credential)
    assert isinstance(auth, RunnerAuthDenied)
    assert auth.reason == "revoked_runner"

    client = TestClient(app)
    denied = client.post(
        "/api/runner/jobs/claim",
        headers={"authorization": f"Bearer {credential.credential}"},
    )
    assert denied.status_code == 401
    assert denied.json()["detail"] == "revoked_runner"

    # An in-process AuthenticatedRunner must still not lease work after revocation.
    forged = AuthenticatedRunner(
        runner_id=credential.runner_id, device_name="laptop", mode="analysis_only"
    )
    assert isinstance(claim_job(forged), NoJob)


def test_unassigned_runner_sees_no_job_even_when_one_exists(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobEnvelope, NoJob
    from pr_reviewer.control_plane.runner_jobs import claim_job

    installation_id = 7002
    assigned_repo = 81002
    other_repo = 81003
    insert_installation(installation_id)
    assigned = pair_runner_assigned_to_repo(
        installation_id, assigned_repo, make_verified_installation_access, "assigned"
    )
    outsider = pair_runner_assigned_to_repo(
        installation_id, other_repo, make_verified_installation_access, "outsider"
    )
    enqueue_pull_request_job("delivery-assigned-only", installation_id, assigned_repo)

    outsider_result = claim_job(authenticate(outsider.credential))
    assigned_result = claim_job(authenticate(assigned.credential))

    assert isinstance(outsider_result, NoJob)
    assert isinstance(assigned_result, JobEnvelope)
    assert assigned_result.installation_id == installation_id
    assert assigned_result.repository_id == assigned_repo
    assert assigned_result.pull_request_number == 12
    assert assigned_result.base_sha == BASE_SHA
    assert assigned_result.head_sha == HEAD_SHA
    assert assigned_result.policy_version
    assert assigned_result.budget is not None
    assert assigned_result.trace_id
    assert assigned_result.lease_token
    assert assigned_result.lease_token != str(assigned.runner_id)


def test_empty_queue_is_indistinguishable_from_someone_elses_job(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import NoJob
    from pr_reviewer.control_plane.runner_jobs import claim_job

    idle_installation = 7003
    busy_installation = 7004
    insert_installation(idle_installation)
    insert_installation(busy_installation)
    idle = pair_runner_assigned_to_repo(
        idle_installation, 81004, make_verified_installation_access, "idle"
    )
    pair_runner_assigned_to_repo(
        busy_installation, 81005, make_verified_installation_access, "busy"
    )

    empty_queue = claim_job(authenticate(idle.credential))
    enqueue_pull_request_job("delivery-other-tenant", busy_installation, 81005)
    other_tenant = claim_job(authenticate(idle.credential))

    assert isinstance(empty_queue, NoJob)
    assert isinstance(other_tenant, NoJob)
    assert type(empty_queue) is type(other_tenant)


def test_jobs_queue_while_the_runner_is_offline_then_claim_on_reconnect(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobEnvelope
    from pr_reviewer.control_plane.runner_jobs import claim_job

    installation_id = 7005
    github_repository_id = 81006
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-offline", installation_id, github_repository_id)

    with connection() as conn:
        row = conn.execute(
            "select status from review_jobs where delivery_id = %s",
            ("delivery-offline",),
        ).fetchone()
    assert row is not None
    assert row["status"] == "pending"

    result = claim_job(authenticate(credential.credential))
    assert isinstance(result, JobEnvelope)
    assert result.head_sha == HEAD_SHA


def test_stale_head_sha_is_superseded_and_not_claimed(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobEnvelope, NoJob
    from pr_reviewer.control_plane.runner_jobs import claim_job

    installation_id = 7006
    github_repository_id = 81007
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job(
        "delivery-stale", installation_id, github_repository_id, head_sha=HEAD_SHA
    )
    enqueue_pull_request_job(
        "delivery-fresh", installation_id, github_repository_id, head_sha=NEWER_HEAD_SHA
    )

    runner = authenticate(credential.credential)
    first = claim_job(runner)
    second = claim_job(runner)
    assert isinstance(first, JobEnvelope)
    assert first.head_sha == NEWER_HEAD_SHA
    assert isinstance(second, NoJob)

    with connection() as conn:
        stale = conn.execute(
            "select status from review_jobs where delivery_id = %s",
            ("delivery-stale",),
        ).fetchone()
    assert stale is not None
    assert stale["status"] not in {"pending", "running"}


def test_duplicate_claim_does_not_mint_a_second_lease(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobEnvelope, NoJob
    from pr_reviewer.control_plane.runner_jobs import claim_job, heartbeat_job

    installation_id = 7007
    github_repository_id = 81008
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-dup-claim", installation_id, github_repository_id)

    runner = authenticate(credential.credential)
    first = claim_job(runner)
    second = claim_job(runner)
    assert isinstance(first, JobEnvelope)
    assert isinstance(second, NoJob)

    lease = heartbeat_job(runner.runner_id, first.job_id, first.lease_token)
    assert lease.status == "active"
    with connection() as conn:
        row = conn.execute(
            "select attempts from review_jobs where id = %s",
            (str(first.job_id),),
        ).fetchone()
    assert row is not None
    assert row["attempts"] == 1


def test_concurrent_claims_of_one_job_exactly_one_wins(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobEnvelope, NoJob
    from pr_reviewer.control_plane.runner_jobs import claim_job

    installation_id = 7008
    github_repository_id = 81009
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-concurrent", installation_id, github_repository_id)
    runner = authenticate(credential.credential)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim_job, runner) for _ in range(2)]
        results = [future.result() for future in futures]

    envelopes = [item for item in results if isinstance(item, JobEnvelope)]
    none = [item for item in results if isinstance(item, NoJob)]
    assert len(envelopes) == 1, f"expected exactly one winner, got: {results}"
    assert len(none) == 1
    assert envelopes[0].lease_token


def test_claim_job_uses_skip_locked_and_binds_the_lease_to_the_runner() -> None:
    from pr_reviewer.control_plane import runner_jobs

    source = Path(inspect.getfile(runner_jobs)).read_text(encoding="utf-8").lower()
    assert "for update skip locked" in source
    assert "lease_token" in source


def test_wrong_lease_and_expired_lease_are_the_same_heartbeat_state(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobEnvelope
    from pr_reviewer.control_plane.runner_jobs import claim_job, heartbeat_job

    installation_id = 7009
    github_repository_id = 81010
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-lease", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    wrong = heartbeat_job(runner.runner_id, envelope.job_id, "not-the-lease-token")
    with connection() as conn, conn.transaction():
        conn.execute(
            "update review_jobs set locked_until = now() - interval '1 second' where id = %s",
            (str(envelope.job_id),),
        )
    expired = heartbeat_job(runner.runner_id, envelope.job_id, envelope.lease_token)
    unknown_job = heartbeat_job(runner.runner_id, uuid.uuid4(), envelope.lease_token)

    assert wrong.status == expired.status == unknown_job.status
    assert wrong.status == "invalid_or_expired"


def test_acknowledge_rejects_wrong_and_expired_lease_the_same_way(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobEnvelope, JobProtocolDenied
    from pr_reviewer.control_plane.runner_jobs import acknowledge_job, claim_job

    installation_id = 7010
    github_repository_id = 81011
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-ack-lease", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)
    result = acknowledgement()

    with pytest.raises(JobProtocolDenied) as wrong:
        acknowledge_job(runner.runner_id, envelope.job_id, "not-the-lease-token", result)
    with connection() as conn, conn.transaction():
        conn.execute(
            "update review_jobs set locked_until = now() - interval '1 second' where id = %s",
            (str(envelope.job_id),),
        )
    with pytest.raises(JobProtocolDenied) as expired:
        acknowledge_job(runner.runner_id, envelope.job_id, envelope.lease_token, result)

    assert wrong.value.reason == expired.value.reason == "invalid_or_expired"
    with connection() as conn:
        row = conn.execute(
            "select status from review_jobs where id = %s",
            (str(envelope.job_id),),
        ).fetchone()
    assert row is not None
    assert row["status"] == "running"


def test_duplicate_acknowledgement_is_idempotent(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobEnvelope
    from pr_reviewer.control_plane.runner_jobs import acknowledge_job, claim_job

    installation_id = 7011
    github_repository_id = 81012
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-dup-ack", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)
    result = acknowledgement(input_tokens=11, output_tokens=22, cost_usd=Decimal("0.020000"))

    acknowledge_job(runner.runner_id, envelope.job_id, envelope.lease_token, result)
    acknowledge_job(runner.runner_id, envelope.job_id, envelope.lease_token, result)

    with connection() as conn:
        job = conn.execute(
            "select status from review_jobs where id = %s",
            (str(envelope.job_id),),
        ).fetchone()
        events = conn.execute(
            "select event_type, payload from agent_events where review_job_id = %s "
            "order by created_at",
            (str(envelope.job_id),),
        ).fetchall()
    assert job is not None
    assert job["status"] == "succeeded"
    terminal = [event for event in events if event["event_type"] == "review_job_acknowledged"]
    assert len(terminal) == 1
    payload = dict(terminal[0]["payload"])
    assert payload.get("input_tokens") == 11
    assert payload.get("output_tokens") == 22
    assert "diff" not in payload
    assert "rationale" not in payload
    assert "source" not in payload
    assert "error" not in payload


def test_acknowledgement_records_only_redacted_lifecycle_fields(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobAcknowledgement, JobEnvelope
    from pr_reviewer.control_plane.runner_jobs import acknowledge_job, claim_job

    installation_id = 7012
    github_repository_id = 81013
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-redacted", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)
    result = acknowledgement(terminal_state="failed", error_class="ModelProviderError")
    acknowledge_job(runner.runner_id, envelope.job_id, envelope.lease_token, result)

    allowed = {
        "terminal_state",
        "error_class",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "latency_ms",
        "local_result_hash",
    }
    with connection() as conn:
        event = conn.execute(
            "select payload from agent_events where review_job_id = %s and event_type = %s",
            (str(envelope.job_id), "review_job_acknowledged"),
        ).fetchone()
    assert event is not None
    payload = dict(event["payload"])
    assert set(payload) <= allowed
    assert payload["error_class"] == "ModelProviderError"
    assert "Traceback" not in str(payload)
    with pytest.raises(ValidationError):
        JobAcknowledgement(
            terminal_state="failed",
            error_class="ModelProviderError",
            input_tokens=1,
            output_tokens=1,
            cost_usd=Decimal("0.01"),
            latency_ms=1,
            local_result_hash="e" * 64,
            diff="@@ -1,1 +1,1 @@",
        )


def test_job_envelope_rejects_unknown_fields_and_command_strings() -> None:
    from pr_reviewer.contracts.runner import JobEnvelope

    assert JobEnvelope.model_config.get("extra") == "forbid"
    forbidden = {
        "command",
        "cmd",
        "argv",
        "args",
        "shell",
        "script",
        "executable",
        "payload",
    }
    assert not (set(JobEnvelope.model_fields) & forbidden)
    with pytest.raises(ValidationError):
        JobEnvelope(
            job_id=uuid.uuid4(),
            installation_id=1,
            repository_id=1,
            pull_request_number=1,
            base_sha=BASE_SHA,
            head_sha=HEAD_SHA,
            policy_version="v1",
            budget={"max_tokens": 1, "max_cost_usd": "0.01"},
            trace_id=uuid.uuid4(),
            lease_token="token",
            command="rm -rf /",
        )


def test_runner_client_polls_outbound_https_and_never_listens() -> None:
    from pr_reviewer.runner import client as runner_client

    source = inspect.getsource(runner_client)
    lowered = source.lower()
    assert "httpx" in lowered
    assert "bind(" not in source
    assert "listen(" not in source
    assert "uvicorn" not in lowered
    timeout = runner_client.RunnerClient.POLL_TIMEOUT_SECONDS
    assert 0 < timeout <= 30
    delay = runner_client.RunnerClient.poll_delay_seconds(attempt=1)
    assert delay > 0
