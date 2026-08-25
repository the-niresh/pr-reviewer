from __future__ import annotations

from typing import Any

from psycopg import Connection

from pr_reviewer.db.client import connection
from pr_reviewer.events.record_event import serialize_json_object

MAX_REVIEW_JOB_ATTEMPTS = 3
REVIEW_JOB_RETRY_INTERVAL = "1 minute"


def fail_review_job(
    job_id: str,
    worker_id: str,
    error: str,
    conn: Connection[dict[str, Any]] | None = None,
) -> None:
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
                    error,
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
                    serialize_json_object({"error": error, "status": status}),
                ),
            )

    if conn is not None:
        run(conn)
        return

    with connection() as pooled_conn:
        run(pooled_conn)
