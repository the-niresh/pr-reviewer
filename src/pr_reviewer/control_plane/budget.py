"""Hosted aggregate repository budget. One UPDATE, unset means deny.

Local per-job reservation lives in local_store.budget. This module owns Neon.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg import Connection

from pr_reviewer.reliability.budget import BudgetDenied

RowConn = Connection[dict[str, Any]]


def upsert_repository_budget(
    conn: RowConn,
    *,
    installation_id: int,
    github_repository_id: int,
    max_tokens: int | None,
    max_cost_usd: Decimal | None,
) -> None:
    conn.execute(
        """
        insert into repository_budgets (
          installation_id, github_repository_id, max_tokens, max_cost_usd
        )
        values (%s, %s, %s, %s)
        on conflict (installation_id, github_repository_id)
        do update set max_tokens = excluded.max_tokens, max_cost_usd = excluded.max_cost_usd
        """,
        (installation_id, github_repository_id, max_tokens, max_cost_usd),
    )


def reserve_repository_budget(
    conn: RowConn,
    *,
    installation_id: int,
    github_repository_id: int,
    job_id: str,
    tokens: int,
    cost_usd: Decimal,
) -> None:
    existing = conn.execute(
        """
        select 1 from repository_budget_reservations
        where job_id = %s and status = 'held'
        """,
        (job_id,),
    ).fetchone()
    if existing is not None:
        return
    cursor = conn.execute(
        """
        update repository_budgets
        set reserved_tokens = reserved_tokens + %s,
            reserved_cost_usd = reserved_cost_usd + %s
        where installation_id = %s
          and github_repository_id = %s
          and max_tokens is not null and max_tokens > 0
          and max_cost_usd is not null and max_cost_usd > 0
          and reserved_tokens + spent_tokens + %s <= max_tokens
          and reserved_cost_usd + spent_cost_usd + %s <= max_cost_usd
        returning 1
        """,
        (tokens, cost_usd, installation_id, github_repository_id, tokens, cost_usd),
    )
    if cursor.fetchone() is None:
        configured = conn.execute(
            """
            select 1 from repository_budgets
            where installation_id = %s
              and github_repository_id = %s
              and max_tokens is not null and max_tokens > 0
              and max_cost_usd is not null and max_cost_usd > 0
            """,
            (installation_id, github_repository_id),
        ).fetchone()
        raise BudgetDenied("unset" if configured is None else "insufficient")
    conn.execute(
        """
        insert into repository_budget_reservations (
          job_id, installation_id, github_repository_id, tokens, cost_usd, status
        ) values (%s, %s, %s, %s, %s, 'held')
        """,
        (job_id, installation_id, github_repository_id, tokens, cost_usd),
    )


def release_repository_reservation(conn: RowConn, job_id: str) -> None:
    row = conn.execute(
        """
        update repository_budget_reservations
        set status = 'released'
        where job_id = %s and status = 'held'
        returning installation_id, github_repository_id, tokens, cost_usd
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        return
    conn.execute(
        """
        update repository_budgets
        set reserved_tokens = reserved_tokens - %s,
            reserved_cost_usd = reserved_cost_usd - %s
        where installation_id = %s and github_repository_id = %s
        """,
        (
            int(row["tokens"]),
            row["cost_usd"],
            int(row["installation_id"]),
            int(row["github_repository_id"]),
        ),
    )
