"""Writer for review_jobs.status = cancelled.

The check constraint has included cancelled since 202608302200_pr_lifecycle.sql.
A draft PR produces no row. This writer only marks pending or running jobs.
"""

from __future__ import annotations

from typing import Literal

from pr_reviewer.contracts.github import GitHubDelivery
from pr_reviewer.db.client import connection

CancelReviewJobResult = Literal["cancelled", "duplicate"]


def cancel_review_job(delivery: GitHubDelivery) -> CancelReviewJobResult:
    identity = delivery.repository_identity
    with connection() as conn, conn.transaction():
        delivery_cursor = conn.execute(
            """
            insert into github_deliveries (id, event_name)
            values (%s, %s)
            on conflict (id) do nothing
            returning id
            """,
            (delivery.delivery_id, delivery.event),
        )
        if delivery_cursor.rowcount == 0:
            return "duplicate"
        conn.execute(
            """
            update review_jobs
            set status = 'cancelled',
                updated_at = now()
            where installation_id = %s
              and github_repository_id = %s
              and pull_request_number = %s
              and status in ('pending', 'running')
            """,
            (
                identity.installation_id,
                identity.repository_id,
                delivery.pull_request.number,
            ),
        )
    return "cancelled"
