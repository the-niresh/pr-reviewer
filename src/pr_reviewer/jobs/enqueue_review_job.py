from __future__ import annotations

from typing import Literal

from pr_reviewer.db.client import connection

EnqueueReviewJobResult = Literal["enqueued", "duplicate", "ignored"]


def enqueue_review_job(
    delivery_id: str,
    event_name: str,
    payload: object,
) -> EnqueueReviewJobResult:
    del payload
    if event_name != "pull_request":
        return "ignored"

    with connection() as conn, conn.transaction():
        delivery_cursor = conn.execute(
            """
            insert into github_deliveries (id, event_name)
            values (%s, %s)
            on conflict (id) do nothing
            returning id
            """,
            (delivery_id, event_name),
        )

        if delivery_cursor.rowcount == 0:
            return "duplicate"

        conn.execute(
            """
            insert into review_jobs (delivery_id, status)
            values (%s, 'pending')
            """,
            (delivery_id,),
        )
    return "enqueued"
