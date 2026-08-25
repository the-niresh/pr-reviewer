from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest

from pr_reviewer.jobs import ReviewJob
from pr_reviewer.worker.main import JobStore, run_worker


def make_job(job_id: str = "job-1") -> ReviewJob:
    now = datetime.now(UTC)
    return ReviewJob(
        id=job_id,
        delivery_id="delivery-1",
        pull_request_id=None,
        status="pending",
        attempts=0,
        available_at=now,
        locked_by=None,
        locked_until=None,
        last_error=None,
        created_at=now,
        updated_at=now,
    )


def test_worker_completes_claimed_job() -> None:
    job = make_job()
    completed: list[str] = []

    store = JobStore(
        claim=lambda worker_id: job if not completed else None,
        complete=lambda job_id, worker_id: completed.append(job_id),
        fail=lambda job_id, worker_id, error: pytest.fail(error),
        renew=lambda job_id, worker_id: None,
    )

    run_worker(job_store=store, max_iterations=1, poll_interval_seconds=0, worker_id="worker-1")

    assert completed == ["job-1"]


def test_worker_fails_job_when_run_job_raises() -> None:
    job = make_job()
    failures: list[str] = []

    store = JobStore(
        claim=lambda worker_id: job,
        complete=lambda job_id, worker_id: pytest.fail("job should not complete"),
        fail=lambda job_id, worker_id, error: failures.append(error),
        renew=lambda job_id, worker_id: None,
    )

    def run_job(_job: ReviewJob, _stop_event: threading.Event) -> None:
        raise RuntimeError("boom")

    run_worker(
        job_store=store,
        max_iterations=1,
        poll_interval_seconds=0,
        run_job=run_job,
        worker_id="worker-1",
    )

    assert failures == ["boom"]
