from __future__ import annotations

from pr_reviewer.db.client import connection
from pr_reviewer.jobs import (
    claim_review_job,
    complete_review_job,
    enqueue_review_job,
    fail_review_job,
    renew_review_job_lease,
)


def test_enqueue_ignores_non_pull_request_event() -> None:
    assert enqueue_review_job("delivery-1", "push", {}) == "ignored"


def test_enqueue_deduplicates_delivery_id() -> None:
    assert enqueue_review_job("delivery-1", "pull_request", {}) == "enqueued"
    assert enqueue_review_job("delivery-1", "pull_request", {}) == "duplicate"

    with connection() as conn:
        job_count = conn.execute("select count(*) as count from review_jobs").fetchone()

    assert job_count is not None
    assert job_count["count"] == 1


def test_claim_complete_and_renew_job() -> None:
    enqueue_review_job("delivery-2", "pull_request", {})

    job = claim_review_job("worker-1")

    assert job is not None
    assert job.status == "running"
    assert job.locked_by == "worker-1"
    renew_review_job_lease(job.id, "worker-1")
    complete_review_job(job.id, "worker-1")

    with connection() as conn:
        row = conn.execute(
            "select status, locked_by from review_jobs where id = %s",
            (job.id,),
        ).fetchone()

    assert row is not None
    assert row["status"] == "succeeded"
    assert row["locked_by"] is None


def test_fail_job_schedules_retry_and_records_event() -> None:
    enqueue_review_job("delivery-3", "pull_request", {})
    job = claim_review_job("worker-1")

    assert job is not None
    fail_review_job(job.id, "worker-1", "boom")

    with connection() as conn:
        row = conn.execute(
            "select status, last_error from review_jobs where id = %s",
            (job.id,),
        ).fetchone()
        event = conn.execute(
            "select event_type, payload from agent_events where review_job_id = %s",
            (job.id,),
        ).fetchone()

    assert row is not None
    assert row["status"] == "pending"
    assert row["last_error"] == "boom"
    assert event is not None
    assert event["event_type"] == "review_job_retry_scheduled"
