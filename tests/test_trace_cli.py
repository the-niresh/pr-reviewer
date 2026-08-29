"""Integration tests for Runtime Task 5A: fetch_hosted_trace, LocalStore.fetch_trace, and the
`reviewer trace` CLI wired to real Postgres and a real local SQLite file.

tests/test_trace_join.py already covers the pure merge/redaction rules with fabricated inputs;
this file exists to prove the adapters that turn real storage into those inputs are correct, and
that the whole path together satisfies the Phase 6 proof gate: reconstructing one review from its
job ID needs no manual database work.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from pr_reviewer.cli.trace import run
from pr_reviewer.contracts.runner import JobBudget, JobEnvelope
from pr_reviewer.control_plane.runner_jobs import fetch_hosted_trace
from pr_reviewer.db.client import connection
from pr_reviewer.events.record_event import record_event
from pr_reviewer.jobs import enqueue_review_job
from pr_reviewer.local_store.sqlite import open_local_store

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
NEWER_HEAD_SHA = "c" * 40


def insert_installation(installation_id: int) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s) "
            "on conflict (id) do nothing",
            (installation_id, "acme"),
        )


def enqueue_full_job(
    delivery_id: str,
    installation_id: int,
    github_repository_id: int,
    *,
    pull_request_number: int = 12,
    base_sha: str = BASE_SHA,
    head_sha: str = HEAD_SHA,
    repo_name: str = "widgets",
) -> str:
    """Enqueues a fully-identified job (unlike test_hosted_event_rescope.py's create_review_job,
    which inserts a bare row with no identity) so review_jobs actually assigns a trace_id -- the
    minimal insert path leaves trace_id null on purpose, matching enqueue_review_job.py.
    """
    insert_installation(installation_id)
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
    with connection() as conn:
        row = conn.execute(
            "select id from review_jobs where delivery_id = %s", (delivery_id,)
        ).fetchone()
    assert row is not None
    return str(row["id"])


def get_trace_id(job_id: str) -> str:
    with connection() as conn:
        row = conn.execute(
            "select trace_id from review_jobs where id = %s", (job_id,)
        ).fetchone()
    assert row is not None
    return str(row["trace_id"])


def job_envelope(job_id: str, trace_id: str) -> JobEnvelope:
    return JobEnvelope(
        job_id=uuid.UUID(job_id),
        installation_id=1,
        repository_id=1,
        pull_request_number=1,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        policy_version="v1",
        budget=JobBudget(max_tokens=1000, max_cost_usd=Decimal("1.000000")),
        trace_id=uuid.UUID(trace_id),
        lease_token="lease-token-value",
    )


def test_fetch_hosted_trace_returns_none_for_an_unknown_job() -> None:
    assert fetch_hosted_trace(str(uuid.uuid4())) is None


def test_fetch_hosted_trace_returns_none_for_a_job_row_with_no_trace_id() -> None:
    # enqueue_review_job's minimal insert path (no identifiable pull_request payload) leaves
    # trace_id null; fetch_hosted_trace must treat that the same as "no such job", not crash on it.
    assert enqueue_review_job("delivery-no-identity", "pull_request", {}) == "enqueued"
    with connection() as conn:
        row = conn.execute(
            "select id from review_jobs where delivery_id = %s", ("delivery-no-identity",)
        ).fetchone()
    assert row is not None

    assert fetch_hosted_trace(str(row["id"])) is None


def test_fetch_hosted_trace_joins_agent_events_by_review_job_id_and_reports_trace_id() -> None:
    job_id = enqueue_full_job("delivery-hosted-trace", 9001, 90001)
    trace_id = get_trace_id(job_id)
    record_event(job_id, "webhook.accepted", {"deliveryId": "delivery-hosted-trace"})
    record_event(job_id, "model_call.recorded", {"inputTokens": 10})

    hosted = fetch_hosted_trace(job_id)

    assert hosted is not None
    assert hosted.trace_id == trace_id
    assert [event.kind for event in hosted.events] == ["webhook.accepted", "model_call.recorded"]
    assert hosted.events[0].sequence < hosted.events[1].sequence


def test_local_store_fetch_trace_returns_none_for_an_unknown_job(tmp_path: Path) -> None:
    store = open_local_store(tmp_path / "local.sqlite3")
    assert store.fetch_trace(str(uuid.uuid4())) is None


def test_local_store_fetch_trace_joins_local_events_by_trace_id(tmp_path: Path) -> None:
    store = open_local_store(tmp_path / "local.sqlite3")
    job_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    store.jobs.record_claimed(job_envelope(job_id, trace_id))
    store.events.record(job_id=job_id, trace_id=trace_id, event_type="job_claimed", payload={})
    store.events.record(
        job_id=job_id, trace_id=trace_id, event_type="snapshot_fetched", payload={"files": 1}
    )

    local = store.fetch_trace(job_id)

    assert local is not None
    assert local.trace_id == trace_id
    assert [event.kind for event in local.events] == ["job_claimed", "snapshot_fetched"]


def test_reconstructing_a_trace_from_real_storage_needs_no_manual_database_work(
    tmp_path: Path,
) -> None:
    # The Phase 6 proof gate itself: given only a job id and a local store path, the full trace
    # comes back through fetch_hosted_trace + LocalStore.fetch_trace + reconstruct_trace, with no
    # hand-written SQL, no psql session, and no sqlite3 CLI invocation anywhere in this test.
    job_id = enqueue_full_job("delivery-e2e-trace", 9002, 90002)
    trace_id = get_trace_id(job_id)
    record_event(job_id, "model_call.recorded", {"provider": "openai", "inputTokens": 10})

    store = open_local_store(tmp_path / "local.sqlite3")
    store.jobs.record_claimed(job_envelope(job_id, trace_id))
    store.events.record(job_id=job_id, trace_id=trace_id, event_type="job_claimed", payload={})

    hosted = fetch_hosted_trace(job_id)
    local = store.fetch_trace(job_id)

    from pr_reviewer.observability.trace import reconstruct_trace

    result = reconstruct_trace(job_id, hosted, local)

    assert result.is_complete is True
    assert [segment.kind for segment in result.segments] == ["model_call.recorded", "job_claimed"]


def test_superseded_job_keeps_its_own_trace_and_does_not_pull_in_the_superseding_jobs_events() -> (
    None
):
    installation_id = 9003
    github_repository_id = 90003
    old_job_id = enqueue_full_job(
        "delivery-superseded-old", installation_id, github_repository_id, head_sha=HEAD_SHA
    )
    record_event(old_job_id, "webhook.accepted", {"deliveryId": "delivery-superseded-old"})

    new_job_id = enqueue_full_job(
        "delivery-superseded-new", installation_id, github_repository_id, head_sha=NEWER_HEAD_SHA
    )
    record_event(new_job_id, "webhook.accepted", {"deliveryId": "delivery-superseded-new"})

    with connection() as conn:
        status_row = conn.execute(
            "select status from review_jobs where id = %s", (old_job_id,)
        ).fetchone()
    assert status_row is not None
    assert status_row["status"] == "superseded"

    old_trace = fetch_hosted_trace(old_job_id)
    new_trace = fetch_hosted_trace(new_job_id)

    assert old_trace is not None
    assert new_trace is not None
    assert old_trace.trace_id != new_trace.trace_id
    assert len(old_trace.events) == 1
    assert len(new_trace.events) == 1
    assert old_trace.events[0].payload["deliveryId"] == "delivery-superseded-old"
    assert new_trace.events[0].payload["deliveryId"] == "delivery-superseded-new"


def test_cli_reports_incomplete_and_names_hosted_as_missing_when_only_local_has_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    store = open_local_store(tmp_path / "local.sqlite3")
    store.jobs.record_claimed(job_envelope(job_id, trace_id))
    store.events.record(job_id=job_id, trace_id=trace_id, event_type="job_claimed", payload={})

    exit_code = run([job_id, "--local-store", str(tmp_path / "local.sqlite3")])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "INCOMPLETE: missing data from: hosted" in output
    assert "job_claimed" in output


def test_cli_returns_nonzero_when_job_is_unknown_to_both_stores(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run([str(uuid.uuid4()), "--local-store", str(tmp_path / "local.sqlite3")])

    assert exit_code == 1
    assert "No trace found" in capsys.readouterr().err


def test_cli_json_export_redacts_secret_like_keys_and_shapes_segments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job_id = enqueue_full_job("delivery-cli-json", 9004, 90004)
    trace_id = get_trace_id(job_id)
    record_event(job_id, "model_call.recorded", {"provider": "openai"})

    store = open_local_store(tmp_path / "local.sqlite3")
    store.jobs.record_claimed(job_envelope(job_id, trace_id))
    store.events.record(
        job_id=job_id,
        trace_id=trace_id,
        event_type="github_call",
        payload={"githubToken": "ghs_leaked_token_value"},
    )

    exit_code = run(
        [job_id, "--local-store", str(tmp_path / "local.sqlite3"), "--json"]
    )

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["jobId"] == job_id
    assert parsed["traceId"] == trace_id
    assert parsed["complete"] is True
    assert parsed["missingOrigins"] == []
    kinds = [segment["kind"] for segment in parsed["segments"]]
    assert kinds == ["model_call.recorded", "github_call"]
    assert "ghs_leaked_token_value" not in json.dumps(parsed)
    placements = {segment["kind"]: segment["placement"] for segment in parsed["segments"]}
    assert placements == {"model_call.recorded": "unordered", "github_call": "proven"}


def test_cli_human_view_flags_an_unordered_hosted_segment_but_not_a_proven_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job_id = enqueue_full_job("delivery-cli-unordered", 9005, 90005)
    trace_id = get_trace_id(job_id)
    record_event(job_id, "model_call.recorded", {"provider": "openai"})

    store = open_local_store(tmp_path / "local.sqlite3")
    store.jobs.record_claimed(job_envelope(job_id, trace_id))
    store.events.record(job_id=job_id, trace_id=trace_id, event_type="job_claimed", payload={})

    exit_code = run([job_id, "--local-store", str(tmp_path / "local.sqlite3")])

    assert exit_code == 0
    output = capsys.readouterr().out
    lines = output.splitlines()
    model_call_line = next(line for line in lines if "model_call.recorded" in line)
    job_claimed_line = next(line for line in lines if "job_claimed" in line)
    assert "UNORDERED" in model_call_line
    assert "UNORDERED" not in job_claimed_line
