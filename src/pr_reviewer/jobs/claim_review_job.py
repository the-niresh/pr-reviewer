from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import Connection

from pr_reviewer.db.client import Row, connection

ReviewJobStatus = str
REVIEW_JOB_LEASE_INTERVAL = "5 minutes"


@dataclass(frozen=True)
class ReviewJob:
    id: str
    delivery_id: str
    pull_request_id: str | None
    status: ReviewJobStatus
    attempts: int
    available_at: datetime
    locked_by: str | None
    locked_until: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


def row_to_review_job(row: Row) -> ReviewJob:
    return ReviewJob(
        id=str(row["id"]),
        delivery_id=str(row["delivery_id"]),
        pull_request_id=str(row["pull_request_id"]) if row["pull_request_id"] is not None else None,
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        available_at=row["available_at"],
        locked_by=str(row["locked_by"]) if row["locked_by"] is not None else None,
        locked_until=row["locked_until"],
        last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def claim_review_job(
    worker_id: str,
    conn: Connection[dict[str, Any]] | None = None,
) -> ReviewJob | None:
    def run(active_conn: Connection[dict[str, Any]]) -> ReviewJob | None:
        cursor = active_conn.execute(
            """
            with next_job as (
              select id
              from review_jobs
              where (status = 'pending' and available_at <= now())
                 or (status = 'running' and locked_until <= now())
              order by available_at asc, created_at asc
              for update skip locked
              limit 1
            )
            update review_jobs
            set status = 'running',
                locked_by = %s,
                locked_until = now() + %s::interval,
                attempts = attempts + 1,
                updated_at = now()
            where id = (select id from next_job)
            returning
              id,
              delivery_id,
              pull_request_id,
              status,
              attempts,
              available_at,
              locked_by,
              locked_until,
              last_error,
              created_at,
              updated_at
            """,
            (worker_id, REVIEW_JOB_LEASE_INTERVAL),
        )
        row = cursor.fetchone()
        return row_to_review_job(dict(row)) if row is not None else None

    if conn is not None:
        return run(conn)

    with connection() as pooled_conn:
        return run(pooled_conn)
