"""Failing tests for Task 18 fault matrix, ops endpoints, retry, circuits, and queue benchmark.

Imports of new modules stay inside test bodies. Waits use an injected clock and a hard deadline.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import httpx
import pytest

from pr_reviewer.contracts.errors import ReviewJobErrorClass
from pr_reviewer.db.client import connection
from pr_reviewer.jobs import claim_review_job, enqueue_review_job, fail_review_job
from pr_reviewer.web.app import app

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"
EXPECTED_WORKER_COUNT = 4


def test_github_timeout_retries_until_deadline_then_raises_loudly() -> None:
    from pr_reviewer.reliability.retry import RetryDeadlineExceeded, run_with_retry

    attempts = {"n": 0}
    sleeps: list[float] = []

    def operation() -> str:
        attempts["n"] += 1
        raise httpx.TimeoutException("github timed out")

    with pytest.raises(RetryDeadlineExceeded, match="deadline"):
        run_with_retry(
            operation,
            is_retryable=lambda error: isinstance(error, httpx.TimeoutException),
            deadline_monotonic=0.1,
            clock=lambda: 0.0,
            sleep=sleeps.append,
            max_attempts=5,
            base_seconds=0.5,
            cap_seconds=8.0,
        )
    assert attempts["n"] >= 1
    assert sleeps == []


def test_provider_timeout_is_retryable_until_success() -> None:
    from pr_reviewer.models.provider import ModelTimeout
    from pr_reviewer.reliability.retry import run_with_retry

    attempts = {"n": 0}

    def operation() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ModelTimeout()
        return "ok"

    result = run_with_retry(
        operation,
        is_retryable=lambda error: isinstance(error, ModelTimeout),
        deadline_monotonic=10.0,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
        max_attempts=3,
        base_seconds=0.1,
        cap_seconds=1.0,
        rng=lambda: 0.0,
    )
    assert result == "ok"
    assert attempts["n"] == 2


def test_rate_limit_uses_retry_after_header_not_exponential() -> None:
    from pr_reviewer.reliability.retry import next_backoff, retry_after_seconds

    assert retry_after_seconds({"Retry-After": "12"}) == 12.0
    delay = next_backoff(
        0,
        base_seconds=0.5,
        cap_seconds=30.0,
        retry_after=12.0,
        rng=lambda: 0.0,
    )
    assert delay == 12.0


def test_retry_sleep_never_exceeds_the_deadline() -> None:
    from pr_reviewer.reliability.retry import RetryDeadlineExceeded, run_with_retry

    def operation() -> str:
        raise TimeoutError("neon interrupted")

    with pytest.raises(RetryDeadlineExceeded, match="deadline"):
        run_with_retry(
            operation,
            is_retryable=lambda error: isinstance(error, TimeoutError),
            deadline_monotonic=0.4,
            clock=lambda: 0.0,
            sleep=lambda _seconds: None,
            max_attempts=8,
            base_seconds=1.0,
            cap_seconds=30.0,
            rng=lambda: 0.0,
        )


def test_neon_interruption_is_retryable() -> None:
    from pr_reviewer.reliability.retry import is_neon_interruption, run_with_retry

    class OperationalError(Exception):
        pass

    attempts = {"n": 0}

    def operation() -> int:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OperationalError("server closed the connection unexpectedly")
        return 7

    result = run_with_retry(
        operation,
        is_retryable=is_neon_interruption,
        deadline_monotonic=5.0,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
        max_attempts=3,
        rng=lambda: 0.0,
    )
    assert result == 7


def _fail_until_available(job_id: str, worker_id: str) -> None:
    fail_review_job(job_id, worker_id, ReviewJobErrorClass.WORKER_CRASHED)
    with connection() as conn, conn.transaction():
        conn.execute(
            "update review_jobs set available_at = now() where id = %s and status = 'pending'",
            (job_id,),
        )


def test_worker_crash_schedules_retry_then_dead_job() -> None:
    enqueue_review_job("delivery-fault-crash", "pull_request", {})
    job = None
    for _ in range(3):
        job = claim_review_job("worker-crash")
        assert job is not None
        _fail_until_available(job.id, "worker-crash")
    assert job is not None
    with connection() as conn:
        row = conn.execute(
            "select status, last_error from review_jobs where id = %s",
            (job.id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "failed"
    from pr_reviewer.jobs.requeue_review_job import dead_job_status

    assert dead_job_status(str(row["status"])) == "dead"


def test_manual_requeue_moves_a_dead_job_to_pending() -> None:
    from pr_reviewer.jobs.requeue_review_job import requeue_review_job

    enqueue_review_job("delivery-fault-requeue", "pull_request", {})
    job = None
    for _ in range(3):
        job = claim_review_job("worker-requeue")
        assert job is not None
        _fail_until_available(job.id, "worker-requeue")
    assert job is not None
    with connection() as conn:
        row = conn.execute(
            "select status from review_jobs where id = %s", (job.id,)
        ).fetchone()
    assert row is not None
    assert row["status"] == "failed"
    requeue_review_job(job.id)
    with connection() as conn:
        row = conn.execute(
            "select status, attempts, last_error from review_jobs where id = %s",
            (job.id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "pending"
    assert int(row["attempts"]) == 0
    assert row["last_error"] is None


def test_lease_expiry_makes_the_job_claimable_again() -> None:
    enqueue_review_job("delivery-fault-lease", "pull_request", {})
    held = claim_review_job("worker-lease-a")
    assert held is not None
    with connection() as conn, conn.transaction():
        conn.execute(
            "update review_jobs set locked_until = now() - interval '1 second' where id = %s",
            (held.id,),
        )
    again = claim_review_job("worker-lease-b")
    assert again is not None
    assert again.id == held.id
    assert again.locked_by == "worker-lease-b"


def test_duplicate_delivery_does_not_enqueue_a_second_job() -> None:
    assert enqueue_review_job("delivery-fault-dup", "pull_request", {}) == "enqueued"
    assert enqueue_review_job("delivery-fault-dup", "pull_request", {}) == "duplicate"
    with connection() as conn:
        row = conn.execute("select count(*) as n from review_jobs").fetchone()
    assert row is not None
    assert int(row["n"]) == 1


def test_duplicate_post_is_idempotent_for_the_same_key() -> None:
    from pr_reviewer.contracts.github import PullRequestRef
    from pr_reviewer.github.post_review import posting_idempotency_key

    ref = PullRequestRef(owner="acme", repository="widgets", number=18)
    first = posting_idempotency_key(ref, "a" * 40, "policy-v1")
    second = posting_idempotency_key(ref, "a" * 40, "policy-v1")
    assert first == second


def test_unreadable_circuit_is_open_not_closed() -> None:
    from pr_reviewer.reliability.circuit import (
        UNKNOWN_CIRCUIT_STATE,
        CircuitStateUnreadable,
        allow_call,
        decide_unreadable_circuit,
        load_or_unknown,
    )

    assert UNKNOWN_CIRCUIT_STATE == "open"
    assert decide_unreadable_circuit() == "open"

    def boom() -> Any:
        raise CircuitStateUnreadable("circuit row unreadable")

    snapshot = load_or_unknown("github", load=boom)
    assert snapshot is not None
    assert snapshot.state == "open"
    assert allow_call(snapshot, now=0.0) is False


def test_missing_circuit_row_is_closed_and_allows_the_first_call() -> None:
    from pr_reviewer.reliability.circuit import allow_call, load_or_unknown

    snapshot = load_or_unknown("github", load=lambda: None)
    assert snapshot is None or snapshot.state == "closed"
    assert allow_call(snapshot, now=0.0) is True


def test_half_open_probe_uses_probe_after_not_a_poll_loop() -> None:
    from pr_reviewer.reliability.circuit import CircuitSnapshot, allow_call, seconds_until_probe

    opened = CircuitSnapshot(
        connector="github",
        state="open",
        consecutive_failures=5,
        probe_after_monotonic=10.0,
    )
    assert allow_call(opened, now=9.0) is False
    assert seconds_until_probe(opened, now=9.0) == 1.0
    assert allow_call(opened, now=10.0) is True
    source = (SRC_ROOT / "reliability" / "circuit.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            raise AssertionError("circuit.py must not poll; compare now to probe_after")


def test_ops_health_readiness_queue_cost_rejection_and_circuit_endpoints() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app)
    health = client.get("/health")
    ready = client.get("/ready")
    queue = client.get("/ops/queue")
    cost = client.get("/ops/cost")
    rejection = client.get("/ops/rejection-rate")
    circuits = client.get("/ops/circuits")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ok"
    assert queue.status_code == 200
    body = queue.json()
    assert "depth" in body
    assert "claim_latency_ms" in body
    assert "worker_capacity" in body
    assert cost.status_code == 200
    assert "spent_usd" in cost.json()
    assert rejection.status_code == 200
    assert "rejection_rate" in rejection.json()
    assert circuits.status_code == 200
    assert "circuits" in circuits.json()


def test_queue_metrics_include_depth_claim_latency_and_worker_capacity() -> None:
    from pr_reviewer.control_plane.ops import queue_metrics

    enqueue_review_job("delivery-fault-metrics-a", "pull_request", {})
    enqueue_review_job("delivery-fault-metrics-b", "pull_request", {})
    claimed = claim_review_job("worker-metrics")
    assert claimed is not None
    metrics = queue_metrics()
    assert metrics.depth >= 1
    assert metrics.worker_capacity >= 1
    assert metrics.claim_latency_ms >= 0


def test_postgres_queue_benchmark_at_expected_worker_count_stays_under_two_seconds() -> None:
    from pr_reviewer.reliability.queue_benchmark import (
        EXPECTED_WORKER_COUNT as worker_count,
    )
    from pr_reviewer.reliability.queue_benchmark import (
        run_queue_benchmark,
    )

    assert worker_count == EXPECTED_WORKER_COUNT
    result = run_queue_benchmark(worker_count=EXPECTED_WORKER_COUNT, jobs=40)
    assert result.p99_claim_ms < 2000
    doc = Path(__file__).resolve().parent.parent / "docs" / "QUEUE_BENCHMARK.md"
    text = doc.read_text(encoding="utf-8")
    assert str(EXPECTED_WORKER_COUNT) in text
    assert "not adding redis" in text.lower()
    assert "p99" in text.lower()


def test_reliability_package_is_shared_and_does_not_import_stores() -> None:
    package = SRC_ROOT / "reliability"
    assert package.is_dir()
    forbidden = (
        "pr_reviewer.db",
        "pr_reviewer.control_plane",
        "pr_reviewer.runner",
        "pr_reviewer.local_store",
    )
    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path.name} imported {token}"
