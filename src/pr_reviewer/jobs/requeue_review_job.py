"""Dead-job status and manual requeue. Failed after max attempts is dead."""

from __future__ import annotations

from pr_reviewer.db.client import connection


def dead_job_status(status: str) -> str:
    return "dead" if status == "failed" else status


def requeue_review_job(job_id: str) -> None:
    with connection() as conn:
        cursor = conn.execute(
            """
            update review_jobs
            set status = 'pending',
                attempts = 0,
                last_error = null,
                locked_by = null,
                locked_until = null,
                available_at = now(),
                updated_at = now()
            where id = %s and status = 'failed'
            returning id
            """,
            (job_id,),
        )
        if cursor.fetchone() is None:
            raise RuntimeError(f"review job is not dead: {job_id}")
