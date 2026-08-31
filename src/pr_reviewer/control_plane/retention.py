"""Hosted deletes scoped to one repository. Never the whole installation."""

from __future__ import annotations

from pr_reviewer.db.client import connection


def purge_hosted_repository(installation_id: int, github_repository_id: int) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            """
            delete from repository_budget_reservations
            where installation_id = %s and github_repository_id = %s
            """,
            (installation_id, github_repository_id),
        )
        conn.execute(
            """
            delete from review_jobs
            where installation_id = %s and github_repository_id = %s
            """,
            (installation_id, github_repository_id),
        )
        conn.execute(
            """
            delete from repository_budgets
            where installation_id = %s and github_repository_id = %s
            """,
            (installation_id, github_repository_id),
        )
        conn.execute(
            """
            delete from repositories
            where installation_id = %s and github_repository_id = %s
            """,
            (installation_id, github_repository_id),
        )
