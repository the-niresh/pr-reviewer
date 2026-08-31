"""Hosted health, readiness, queue, cost, rejection-rate, and circuit endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fastapi import APIRouter

from pr_reviewer.db.client import connection

router = APIRouter()


@dataclass(frozen=True)
class QueueMetrics:
    depth: int
    claim_latency_ms: int
    worker_capacity: int


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict[str, str]:
    with connection() as conn:
        conn.execute("select 1")
    return {"status": "ok"}


@router.get("/ops/queue")
def ops_queue() -> dict[str, int]:
    metrics = queue_metrics()
    return {
        "depth": metrics.depth,
        "claim_latency_ms": metrics.claim_latency_ms,
        "worker_capacity": metrics.worker_capacity,
    }


@router.get("/ops/cost")
def ops_cost() -> dict[str, str]:
    with connection() as conn:
        row = conn.execute(
            "select coalesce(sum(spent_cost_usd), 0) as spent from repository_budgets"
        ).fetchone()
    spent = Decimal("0") if row is None else Decimal(str(row["spent"]))
    return {"spent_usd": format(spent, "f")}


@router.get("/ops/rejection-rate")
def ops_rejection_rate() -> dict[str, float]:
    with connection() as conn:
        row = conn.execute(
            """
            select
              count(*) filter (where status = 'failed')::float
                / nullif(count(*) filter (where status in ('failed', 'succeeded')), 0)
              as rate
            from review_jobs
            """
        ).fetchone()
    rate = 0.0 if row is None or row["rate"] is None else float(row["rate"])
    return {"rejection_rate": rate}


@router.get("/ops/circuits")
def ops_circuits() -> dict[str, list[dict[str, str | int]]]:
    with connection() as conn:
        rows = conn.execute(
            "select connector, state, consecutive_failures from connector_circuits"
        ).fetchall()
    return {
        "circuits": [
            {
                "connector": str(row["connector"]),
                "state": str(row["state"]),
                "consecutive_failures": int(row["consecutive_failures"]),
            }
            for row in rows
        ]
    }


def queue_metrics() -> QueueMetrics:
    with connection() as conn:
        depth_row = conn.execute(
            """
            select count(*) as n from review_jobs
            where status = 'pending' and available_at <= now()
            """
        ).fetchone()
        latency_row = conn.execute(
            """
            select coalesce(
              extract(epoch from (updated_at - available_at)) * 1000, 0
            )::int as ms
            from review_jobs
            where status = 'running'
            order by updated_at desc
            limit 1
            """
        ).fetchone()
        capacity_row = conn.execute(
            "select count(*) as n from review_jobs where status = 'running'"
        ).fetchone()
    return QueueMetrics(
        depth=0 if depth_row is None else int(depth_row["n"]),
        claim_latency_ms=0 if latency_row is None else int(latency_row["ms"]),
        worker_capacity=0 if capacity_row is None else int(capacity_row["n"]),
    )
