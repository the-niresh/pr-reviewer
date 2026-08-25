from __future__ import annotations

from typing import Any

from psycopg import Connection

from pr_reviewer.db.client import connection


def complete_review_job(
    job_id: str,
    worker_id: str,
    conn: Connection[dict[str, Any]] | None = None,
) -> None:
    def run(active_conn: Connection[dict[str, Any]]) -> None:
        cursor = active_conn.execute(
            """
            update review_jobs
            set status = 'succeeded',
                locked_by = null,
                locked_until = null,
                updated_at = now()
            where id = %s and status = 'running' and locked_by = %s
            returning id
            """,
            (job_id, worker_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Review job is not owned by worker: {job_id}")

    if conn is not None:
        run(conn)
        return

    with connection() as pooled_conn:
        run(pooled_conn)
