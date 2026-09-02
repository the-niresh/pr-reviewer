"""Per-job budget reservation on the runner's SQLite. Unset means deny."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pr_reviewer.local_store.sqlite import LocalStore
from pr_reviewer.reliability.budget import BudgetDenied, BudgetLimit, is_configured


@dataclass(frozen=True)
class BudgetStatus:
    spent_tokens: int
    spent_cost_usd: Decimal
    max_tokens: int
    max_cost_usd: Decimal

    @property
    def remaining_tokens(self) -> int:
        return max(self.max_tokens - self.spent_tokens, 0)

    @property
    def remaining_cost_usd(self) -> Decimal:
        return max(self.max_cost_usd - self.spent_cost_usd, Decimal("0"))


def get_budget_status(store: LocalStore, job_id: str) -> BudgetStatus | None:
    """None means there is nothing to show: no job, or the budget was never configured (unset
    still means deny, not an unlimited meter).
    """
    job = store.jobs.get(job_id)
    if job is None:
        return None
    limit = BudgetLimit(max_tokens=job.budget.max_tokens, max_cost_usd=job.budget.max_cost_usd)
    if not is_configured(limit):
        return None
    assert limit.max_tokens is not None
    assert limit.max_cost_usd is not None
    row = store.connection.execute(
        "select reserved_tokens, reserved_cost_usd from local_job_budgets where job_id = ?",
        (job_id,),
    ).fetchone()
    spent_tokens = int(row["reserved_tokens"]) if row is not None else 0
    spent_cost_usd = Decimal(row["reserved_cost_usd"]) if row is not None else Decimal("0")
    return BudgetStatus(
        spent_tokens=spent_tokens,
        spent_cost_usd=spent_cost_usd,
        max_tokens=limit.max_tokens,
        max_cost_usd=limit.max_cost_usd,
    )


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
