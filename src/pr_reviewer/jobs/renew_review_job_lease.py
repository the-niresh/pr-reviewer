from __future__ import annotations

from typing import Any

from psycopg import Connection

from pr_reviewer.db.client import connection
from pr_reviewer.jobs.claim_review_job import REVIEW_JOB_LEASE_INTERVAL


def renew_review_job_lease(
    job_id: str,
    worker_id: str,
    conn: Connection[dict[str, Any]] | None = None,
) -> None:
    def run(active_conn: Connection[dict[str, Any]]) -> None:
        cursor = active_conn.execute(
            """
            update review_jobs
            set locked_until = now() + %s::interval,
                updated_at = now()
            where id = %s
              and status = 'running'
              and locked_by = %s
              and locked_until > now()
            returning id
            """,
            (REVIEW_JOB_LEASE_INTERVAL, job_id, worker_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Review job lease is not owned by worker: {job_id}")

    if conn is not None:
        run(conn)
        return

    with connection() as pooled_conn:
        run(pooled_conn)
