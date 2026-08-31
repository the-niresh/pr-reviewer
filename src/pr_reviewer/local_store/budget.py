"""Per-job budget reservation on the runner's SQLite. Unset means deny."""

from __future__ import annotations

from decimal import Decimal

from pr_reviewer.local_store.sqlite import LocalStore
from pr_reviewer.reliability.budget import BudgetDenied, BudgetLimit, is_configured


def reserve_job_budget(
    store: LocalStore, job_id: str, *, tokens: int, cost_usd: Decimal
) -> None:
    job = store.jobs.get(job_id)
    if job is None:
        raise BudgetDenied("unset")
    if not is_configured(
        BudgetLimit(max_tokens=job.budget.max_tokens, max_cost_usd=job.budget.max_cost_usd)
    ):
        raise BudgetDenied("unset")
    store.connection.execute(
        """
        insert or ignore into local_job_budgets (job_id, reserved_tokens, reserved_cost_usd)
        values (?, 0, '0')
        """,
        (job_id,),
    )
    cursor = store.connection.execute(
        """
        update local_job_budgets
        set reserved_tokens = reserved_tokens + ?,
            reserved_cost_usd = printf('%.6f', reserved_cost_usd + ?)
        where job_id = ?
          and reserved_tokens + ? <= (
            select budget_max_tokens from local_jobs where job_id = ?
          )
          and reserved_cost_usd + ? <= (
            select cast(budget_max_cost_usd as real) from local_jobs where job_id = ?
          )
        """,
        (tokens, float(cost_usd), job_id, tokens, job_id, float(cost_usd), job_id),
    )
    if cursor.rowcount != 1:
        raise BudgetDenied("insufficient")
    store.connection.commit()
