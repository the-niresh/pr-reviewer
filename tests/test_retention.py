"""Failing tests for Task 18 retention.

Uninstall of one repository must not delete shared installation data or a sibling
repository on the same installation. Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from pr_reviewer.contracts.runner import JobBudget, JobEnvelope
from pr_reviewer.db.client import connection
from pr_reviewer.local_store.sqlite import open_local_store


def _install_two_repos() -> tuple[int, int, int]:
    installation_id = 18100
    repo_a = 28100
    repo_b = 28101
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (installation_id, "acme"),
        )
        for github_repository_id, name in ((repo_a, "keep-me"), (repo_b, "drop-me")):
            conn.execute(
                """
                insert into repositories (installation_id, github_repository_id, name)
                values (%s, %s, %s)
                """,
                (installation_id, github_repository_id, name),
            )
        conn.execute(
            """
            insert into github_deliveries (id, event_name) values
              ('delivery-keep', 'pull_request'),
              ('delivery-drop', 'pull_request')
            """
        )
        conn.execute(
            """
            insert into review_jobs (
              delivery_id, status, installation_id, github_repository_id,
              pull_request_number, trace_id
            ) values
              ('delivery-keep', 'succeeded', %s, %s, 1, %s),
              ('delivery-drop', 'succeeded', %s, %s, 2, %s)
            """,
            (
                installation_id,
                repo_a,
                uuid.uuid4(),
                installation_id,
                repo_b,
                uuid.uuid4(),
            ),
        )
    return installation_id, repo_a, repo_b


def test_uninstall_one_repository_leaves_sibling_and_installation_intact() -> None:
    from pr_reviewer.security.retention import uninstall_repository

    installation_id, repo_a, repo_b = _install_two_repos()
    now = datetime.now(UTC)
    uninstall_repository(
        installation_id=installation_id,
        github_repository_id=repo_b,
        now=now,
        deadline=now + timedelta(seconds=5),
    )
    with connection() as conn:
        installation = conn.execute(
            "select id from installations where id = %s", (installation_id,)
        ).fetchone()
        remaining = conn.execute(
            """
            select github_repository_id from repositories
            where installation_id = %s order by github_repository_id
            """,
            (installation_id,),
        ).fetchall()
        jobs = conn.execute(
            """
            select github_repository_id from review_jobs
            where installation_id = %s order by github_repository_id
            """,
            (installation_id,),
        ).fetchall()
    assert installation is not None
    assert [int(row["github_repository_id"]) for row in remaining] == [repo_a]
    assert [int(row["github_repository_id"]) for row in jobs] == [repo_a]


def test_retention_does_not_use_a_where_clause_on_installation_alone() -> None:
    from pr_reviewer.security import retention

    source = Path(retention.__file__).read_text(encoding="utf-8")
    lowered = " ".join(source.lower().split())
    assert "github_repository_id" in lowered
    assert "delete from installations" not in lowered


def test_expired_local_jobs_are_purged_for_one_repo_only(tmp_path: Path) -> None:
    from pr_reviewer.security.retention import purge_expired_local

    store = open_local_store(tmp_path / "local.sqlite3")
    keep = JobEnvelope(
        job_id=uuid.uuid4(),
        installation_id=18100,
        repository_id=28100,
        pull_request_number=1,
        base_sha="a" * 40,
        head_sha="b" * 40,
        policy_version="v1",
        budget=JobBudget(max_tokens=100, max_cost_usd=Decimal("1")),
        trace_id=uuid.uuid4(),
        lease_token="lease-keep",
    )
    drop = JobEnvelope(
        job_id=uuid.uuid4(),
        installation_id=18100,
        repository_id=28101,
        pull_request_number=2,
        base_sha="a" * 40,
        head_sha="c" * 40,
        policy_version="v1",
        budget=JobBudget(max_tokens=100, max_cost_usd=Decimal("1")),
        trace_id=uuid.uuid4(),
        lease_token="lease-drop",
    )
    store.jobs.record_claimed(keep)
    store.jobs.record_claimed(drop)
    now = datetime.now(UTC)
    purge_expired_local(
        store,
        github_repository_id=28101,
        now=now,
        deadline=now + timedelta(seconds=5),
        snapshot_max_age=timedelta(seconds=0),
    )
    assert store.jobs.get(str(keep.job_id)) is not None
    assert store.jobs.get(str(drop.job_id)) is None


def test_retention_sweep_raises_loudly_when_the_deadline_passes() -> None:
    from pr_reviewer.security.retention import RetentionSweepTimedOut, uninstall_repository

    now = datetime.now(UTC)
    with pytest.raises(RetentionSweepTimedOut, match="deadline"):
        uninstall_repository(
            installation_id=1,
            github_repository_id=1,
            now=now,
            deadline=now - timedelta(seconds=1),
        )


def test_connector_metadata_for_the_other_repository_survives() -> None:
    from pr_reviewer.security.retention import uninstall_repository

    installation_id, repo_a, repo_b = _install_two_repos()
    keep_job_id = ""
    with connection() as conn, conn.transaction():
        keep_job = conn.execute(
            "select id, trace_id from review_jobs where github_repository_id = %s",
            (repo_a,),
        ).fetchone()
        drop_job = conn.execute(
            "select id, trace_id from review_jobs where github_repository_id = %s",
            (repo_b,),
        ).fetchone()
        assert keep_job is not None
        assert drop_job is not None
        keep_job_id = str(keep_job["id"])
        for job in (keep_job, drop_job):
            conn.execute(
                """
                insert into connector_runs (
                  review_job_id, trace_id, connector, operation,
                  request_bytes, response_bytes, payload_hash
                ) values (
                  %s, %s, 'github', 'fetch_pull_request', 1, 1,
                  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
                )
                """,
                (job["id"], job["trace_id"]),
            )
    now = datetime.now(UTC)
    uninstall_repository(
        installation_id=installation_id,
        github_repository_id=repo_b,
        now=now,
        deadline=now + timedelta(seconds=5),
    )
    with connection() as conn:
        rows = conn.execute("select review_job_id from connector_runs").fetchall()
    assert len(rows) == 1
    assert str(rows[0]["review_job_id"]) == keep_job_id
