"""Failing tests for Task 18 budgets.

Unset means deny, not unlimited. Hosted aggregate reservation is one UPDATE, tested with
two real connections overlapping. Per-job reservation is local. Imports of new modules stay
inside test bodies.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

from pr_reviewer.db.client import connection
from pr_reviewer.local_store.sqlite import open_local_store


def _install(installation_id: int, github_repository_id: int, name: str) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s) "
            "on conflict (id) do nothing",
            (installation_id, "acme"),
        )
        conn.execute(
            """
            insert into repositories (installation_id, github_repository_id, name)
            values (%s, %s, %s)
            on conflict (installation_id, github_repository_id) do nothing
            """,
            (installation_id, github_repository_id, name),
        )


def test_unset_repository_budget_denies_instead_of_spending_freely() -> None:
    from pr_reviewer.control_plane.budget import reserve_repository_budget
    from pr_reviewer.reliability.budget import BudgetDenied

    installation_id = 18001
    github_repository_id = 28001
    _install(installation_id, github_repository_id, "unset")
    with connection() as conn, conn.transaction():
        try:
            reserve_repository_budget(
                conn,
                installation_id=installation_id,
                github_repository_id=github_repository_id,
                job_id=str(uuid.uuid4()),
                tokens=1,
                cost_usd=Decimal("0.01"),
            )
        except BudgetDenied as denied:
            assert denied.reason == "unset"
        else:
            raise AssertionError("unset budget must deny")


def test_null_limit_row_is_unset_and_denies() -> None:
    from pr_reviewer.control_plane.budget import reserve_repository_budget, upsert_repository_budget
    from pr_reviewer.reliability.budget import BudgetDenied

    installation_id = 18002
    github_repository_id = 28002
    _install(installation_id, github_repository_id, "null-limits")
    with connection() as conn, conn.transaction():
        upsert_repository_budget(
            conn,
            installation_id=installation_id,
            github_repository_id=github_repository_id,
            max_tokens=None,
            max_cost_usd=None,
        )
        try:
            reserve_repository_budget(
                conn,
                installation_id=installation_id,
                github_repository_id=github_repository_id,
                job_id=str(uuid.uuid4()),
                tokens=1,
                cost_usd=Decimal("0.01"),
            )
        except BudgetDenied as denied:
            assert denied.reason == "unset"
        else:
            raise AssertionError("null limits must deny")


def test_zero_limit_is_unset_and_denies() -> None:
    from pr_reviewer.reliability.budget import BudgetDenied, BudgetLimit, require_configured

    try:
        require_configured(BudgetLimit(max_tokens=0, max_cost_usd=Decimal("0")))
    except BudgetDenied as denied:
        assert denied.reason == "unset"
    else:
        raise AssertionError("zero is not a configured budget")


def test_configured_limit_is_not_treated_as_unset() -> None:
    from pr_reviewer.reliability.budget import BudgetLimit, is_configured

    assert is_configured(None) is False
    assert is_configured(BudgetLimit(max_tokens=None, max_cost_usd=Decimal("1"))) is False
    assert is_configured(BudgetLimit(max_tokens=100, max_cost_usd=None)) is False
    assert is_configured(BudgetLimit(max_tokens=100, max_cost_usd=Decimal("1"))) is True


def test_two_connections_cannot_exceed_one_repository_budget() -> None:
    from pr_reviewer.control_plane.budget import reserve_repository_budget, upsert_repository_budget
    from pr_reviewer.reliability.budget import BudgetDenied

    installation_id = 18003
    github_repository_id = 28003
    _install(installation_id, github_repository_id, "race")
    with connection() as conn, conn.transaction():
        upsert_repository_budget(
            conn,
            installation_id=installation_id,
            github_repository_id=github_repository_id,
            max_tokens=100,
            max_cost_usd=Decimal("10"),
        )
        conn.execute(
            """
            create or replace function pr_reviewer_slow_budget() returns trigger as $$
            begin
              perform pg_sleep(0.2);
              return new;
            end;
            $$ language plpgsql
            """
        )
        conn.execute("drop trigger if exists pr_reviewer_slow_budget_trg on repository_budgets")
        conn.execute(
            """
            create trigger pr_reviewer_slow_budget_trg
            before update on repository_budgets
            for each row execute function pr_reviewer_slow_budget()
            """
        )

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def attempt(job_suffix: str) -> None:
        barrier.wait(timeout=5)
        try:
            with connection() as conn, conn.transaction():
                reserve_repository_budget(
                    conn,
                    installation_id=installation_id,
                    github_repository_id=github_repository_id,
                    job_id=str(uuid.uuid5(uuid.NAMESPACE_URL, job_suffix)),
                    tokens=60,
                    cost_usd=Decimal("1"),
                )
            outcomes.append("ok")
        except BudgetDenied:
            outcomes.append("denied")

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, "a"), pool.submit(attempt, "b")]
            for future in futures:
                future.result(timeout=10)
    finally:
        with connection() as conn, conn.transaction():
            conn.execute("drop trigger if exists pr_reviewer_slow_budget_trg on repository_budgets")
            conn.execute("drop function if exists pr_reviewer_slow_budget()")

    assert outcomes.count("ok") == 1, outcomes
    assert outcomes.count("denied") == 1, outcomes
    with connection() as conn:
        row = conn.execute(
            """
            select reserved_tokens from repository_budgets
            where installation_id = %s and github_repository_id = %s
            """,
            (installation_id, github_repository_id),
        ).fetchone()
    assert row is not None
    assert int(row["reserved_tokens"]) == 60


def test_hosted_reservation_sql_is_one_update_not_select_then_write() -> None:
    from pr_reviewer.control_plane import budget as hosted_budget

    source = Path(hosted_budget.__file__).read_text(encoding="utf-8")
    assert "update repository_budgets" in source.lower()
    lowered = " ".join(source.lower().split())
    assert "select reserved_tokens" not in lowered
    assert "select max_tokens" not in lowered or "returning" in lowered


def test_local_job_reservation_denies_when_job_budget_unset(tmp_path: Path) -> None:
    from pr_reviewer.contracts.runner import JobBudget, JobEnvelope
    from pr_reviewer.local_store.budget import reserve_job_budget
    from pr_reviewer.reliability.budget import BudgetDenied

    store = open_local_store(tmp_path / "local.sqlite3")
    job = JobEnvelope(
        job_id=uuid.uuid4(),
        installation_id=18004,
        repository_id=28004,
        pull_request_number=1,
        base_sha="a" * 40,
        head_sha="b" * 40,
        policy_version="v1",
        budget=JobBudget(max_tokens=0, max_cost_usd=Decimal("0")),
        trace_id=uuid.uuid4(),
        lease_token="lease-budget",
    )
    store.jobs.record_claimed(job)
    try:
        reserve_job_budget(store, str(job.job_id), tokens=1, cost_usd=Decimal("0.01"))
    except BudgetDenied as denied:
        assert denied.reason == "unset"
    else:
        raise AssertionError("unset local job budget must deny")


def test_local_job_reservation_is_atomic_against_the_job_cap(tmp_path: Path) -> None:
    from pr_reviewer.contracts.runner import JobBudget, JobEnvelope
    from pr_reviewer.local_store.budget import reserve_job_budget
    from pr_reviewer.reliability.budget import BudgetDenied

    store = open_local_store(tmp_path / "local.sqlite3")
    job = JobEnvelope(
        job_id=uuid.uuid4(),
        installation_id=18005,
        repository_id=28005,
        pull_request_number=1,
        base_sha="a" * 40,
        head_sha="b" * 40,
        policy_version="v1",
        budget=JobBudget(max_tokens=100, max_cost_usd=Decimal("1")),
        trace_id=uuid.uuid4(),
        lease_token="lease-local",
    )
    store.jobs.record_claimed(job)
    reserve_job_budget(store, str(job.job_id), tokens=60, cost_usd=Decimal("0.40"))
    try:
        reserve_job_budget(store, str(job.job_id), tokens=60, cost_usd=Decimal("0.40"))
    except BudgetDenied as denied:
        assert denied.reason == "insufficient"
    else:
        raise AssertionError("second local reserve must not exceed the job cap")


def test_runner_offline_mid_job_keeps_hosted_reservation_until_job_is_dead() -> None:
    """Hosted aggregate is the source of truth. Local reservation dies with the process.

    While the runner is gone, the job still holds its hosted reservation so a sibling job
    cannot spend the same cap. Lease expiry does not free it. Terminal failure does.
    """
    from pr_reviewer.control_plane.budget import (
        release_repository_reservation,
        reserve_repository_budget,
        upsert_repository_budget,
    )
    from pr_reviewer.reliability.budget import BudgetDenied

    installation_id = 18006
    github_repository_id = 28006
    _install(installation_id, github_repository_id, "offline")
    job_a = str(uuid.uuid4())
    job_b = str(uuid.uuid4())
    with connection() as conn, conn.transaction():
        upsert_repository_budget(
            conn,
            installation_id=installation_id,
            github_repository_id=github_repository_id,
            max_tokens=100,
            max_cost_usd=Decimal("10"),
        )
        reserve_repository_budget(
            conn,
            installation_id=installation_id,
            github_repository_id=github_repository_id,
            job_id=job_a,
            tokens=100,
            cost_usd=Decimal("1"),
        )
        try:
            reserve_repository_budget(
                conn,
                installation_id=installation_id,
                github_repository_id=github_repository_id,
                job_id=job_b,
                tokens=1,
                cost_usd=Decimal("0.01"),
            )
        except BudgetDenied as denied:
            assert denied.reason == "insufficient"
        else:
            raise AssertionError("sibling must wait while the offline job still holds the cap")
        release_repository_reservation(conn, job_a)
        reserve_repository_budget(
            conn,
            installation_id=installation_id,
            github_repository_id=github_repository_id,
            job_id=job_b,
            tokens=1,
            cost_usd=Decimal("0.01"),
        )


def test_reliability_budget_module_does_not_import_either_plane() -> None:
    import ast
    from pathlib import Path as PathType

    source = (
        PathType(__file__).resolve().parent.parent
        / "src"
        / "pr_reviewer"
        / "reliability"
        / "budget.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = (
        "pr_reviewer.db",
        "pr_reviewer.control_plane",
        "pr_reviewer.runner",
        "pr_reviewer.local_store",
    )
    for token in forbidden:
        assert token not in source
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("pr_reviewer.db")
            assert not node.module.startswith("pr_reviewer.control_plane")
            assert not node.module.startswith("pr_reviewer.local_store")
