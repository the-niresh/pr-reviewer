from __future__ import annotations

from typing import cast

from pr_reviewer.db.client import fetch_all
from pr_reviewer.events.record_event import AgentEvent, JsonObject


def list_events_for_job(review_job_id: str) -> list[AgentEvent]:
    rows = fetch_all(
        """
        select
          id,
          sequence,
          review_job_id,
          event_type,
          payload,
          created_at
        from agent_events
        where review_job_id = %s
        order by sequence asc
        """,
        (review_job_id,),
    )
    return [
        AgentEvent(
            id=str(row["id"]),
            sequence=int(row["sequence"]),
            review_job_id=str(row["review_job_id"]) if row["review_job_id"] is not None else None,
            event_type=str(row["event_type"]),
            payload=cast(JsonObject, row["payload"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]
