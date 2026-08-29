"""Runtime Task 1B: review_jobs.last_error takes a closed-set ReviewJobErrorClass, not a caller-
supplied string, so it cannot hold a diff, a stack trace, or file content. See
contracts/errors.py's module docstring for why.
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from pr_reviewer.contracts.errors import ReviewJobErrorClass
from pr_reviewer.db.client import connection
from pr_reviewer.events.record_event import serialize_json_object

MAX_REVIEW_JOB_ATTEMPTS = 3
REVIEW_JOB_RETRY_INTERVAL = "1 minute"


def fail_review_job(
    job_id: str,
    worker_id: str,
    error: ReviewJobErrorClass,
    conn: Connection[dict[str, Any]] | None = None,
) -> None:
    if not isinstance(error, ReviewJobErrorClass):
        # A type hint alone does not stop a caller that ignores it; the closed set has to be a
        # runtime fact, the same way assert_no_private_columns and COST_USD_PATTERN are.
        raise TypeError(
            f"error must be a ReviewJobErrorClass, not {type(error).__name__}; "
            "review_jobs.last_error is a hosted column and cannot hold free-form prose"
        )

    def run(active_conn: Connection[dict[str, Any]]) -> None:
        with active_conn.transaction():
            cursor = active_conn.execute(
                """
                update review_jobs
                set status = case when attempts >= %s then 'failed' else 'pending' end,
                    available_at = case
                      when attempts >= %s then available_at
                      else now() + %s::interval
                    end,
                    locked_by = null,
                    locked_until = null,
                    last_error = %s,
                    updated_at = now()
                where id = %s and status = 'running' and locked_by = %s
                returning id, status
                """,
                (
                    MAX_REVIEW_JOB_ATTEMPTS,
                    MAX_REVIEW_JOB_ATTEMPTS,
                    REVIEW_JOB_RETRY_INTERVAL,
                    error.value,
                    job_id,
                    worker_id,
                ),
            )

            row = cursor.fetchone()
            if row is None:
                raise RuntimeError(f"Review job is not owned by worker: {job_id}")

            status = str(row["status"])
            active_conn.execute(
                """
                insert into agent_events (review_job_id, event_type, payload)
                values (%s, %s, %s::jsonb)
                """,
                (
                    job_id,
                    "review_job_failed" if status == "failed" else "review_job_retry_scheduled",
                    serialize_json_object({"error": error.value, "status": status}),
                ),
            )

    if conn is not None:
        run(conn)
        return

    with connection() as pooled_conn:
        run(pooled_conn)
