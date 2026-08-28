from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer",
)
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-secret")

from pr_reviewer.db.client import close_pool, connection  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database() -> Iterator[None]:
    with connection() as conn, conn.transaction():
        conn.execute(
            """
            truncate
              model_calls,
              agent_events,
              review_jobs,
              github_deliveries,
              prompt_versions,
              repository_assignments,
              runners,
              repositories,
              installations
            restart identity cascade
            """
        )
    yield


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    close_pool()
