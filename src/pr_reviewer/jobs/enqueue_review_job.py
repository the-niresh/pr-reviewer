from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pr_reviewer.db.client import connection

EnqueueReviewJobResult = Literal["enqueued", "duplicate", "ignored"]

DEFAULT_POLICY_VERSION = "v1"
DEFAULT_BUDGET_MAX_TOKENS = 100_000
DEFAULT_BUDGET_MAX_COST_USD = Decimal("1.000000")


def enqueue_review_job(
    delivery_id: str,
    event_name: str,
    payload: object,
) -> EnqueueReviewJobResult:
    if event_name != "pull_request":
        return "ignored"

    identity = _pull_request_identity(payload)

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

        if identity is None:
            conn.execute(
                """
                insert into review_jobs (delivery_id, status)
                values (%s, 'pending')
                """,
                (delivery_id,),
            )
            return "enqueued"

        installation_id, github_repository_id, pull_request_number, base_sha, head_sha = identity
        installation = conn.execute(
            "select id from installations where id = %s",
            (installation_id,),
        ).fetchone()
        if installation is None:
            conn.execute(
                """
                insert into review_jobs (delivery_id, status)
                values (%s, 'pending')
                """,
                (delivery_id,),
            )
            return "enqueued"

        conn.execute(
            """
            update review_jobs
            set status = 'superseded',
                updated_at = now()
            where installation_id = %s
              and github_repository_id = %s
              and pull_request_number = %s
              and status in ('pending', 'running')
            """,
            (installation_id, github_repository_id, pull_request_number),
        )
        conn.execute(
            """
            insert into review_jobs (
              delivery_id,
              status,
              installation_id,
              github_repository_id,
              pull_request_number,
              base_sha,
              head_sha,
              policy_version,
              budget_max_tokens,
              budget_max_cost_usd,
              trace_id
            )
            values (%s, 'pending', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                delivery_id,
                installation_id,
                github_repository_id,
                pull_request_number,
                base_sha,
                head_sha,
                DEFAULT_POLICY_VERSION,
                DEFAULT_BUDGET_MAX_TOKENS,
                DEFAULT_BUDGET_MAX_COST_USD,
                uuid.uuid4(),
            ),
        )
    return "enqueued"


def _pull_request_identity(
    payload: object,
) -> tuple[int, int, int, str, str] | None:
    if not isinstance(payload, dict):
        return None
    installation = payload.get("installation")
    repository = payload.get("repository")
    pull_request = payload.get("pull_request")
    if not isinstance(installation, dict):
        return None
    if not isinstance(repository, dict):
        return None
    if not isinstance(pull_request, dict):
        return None
    base = pull_request.get("base")
    head = pull_request.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict):
        return None
    try:
        installation_id = int(installation["id"])
        github_repository_id = int(repository["id"])
        pull_request_number = int(pull_request["number"])
        base_sha = str(base["sha"])
        head_sha = str(head["sha"])
    except (KeyError, TypeError, ValueError):
        return None
    if pull_request_number <= 0 or not base_sha or not head_sha:
        return None
    return installation_id, github_repository_id, pull_request_number, base_sha, head_sha
