from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer",
)
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-secret")

from pr_reviewer.contracts.runner import VerifiedInstallationAccess  # noqa: E402
from pr_reviewer.db.client import close_pool, connection  # noqa: E402


@pytest.fixture
def make_verified_installation_access() -> (
    Callable[[int, int, dict[int, str] | None], VerifiedInstallationAccess]
):
    """Test-only construction of VerifiedInstallationAccess.

    VerifiedInstallationAccess has exactly one real construction site in src/
    (control_plane/github_oauth.py's verify_installation_access, which calls GitHub's own
    /user/installations), enforced by
    test_verified_installation_access_construction_site_is_exactly_github_oauth in
    tests/test_github_oauth.py. Tests need a way to build one anyway, so this factory lives in
    tests/conftest.py, outside the src/ scan that check enforces, rather than adding a second
    construction site to production code. A fixture, not a plain importable function, because
    tests/ has no __init__.py and is not set up as an importable package.

    repositories maps github_repository_id -> name, the same shape GitHub's own response would
    give the real verifier. Defaults to empty for tests that never call approve_pairing with a
    non-empty repository_ids list.
    """

    def factory(
        github_user_id: int, installation_id: int, repositories: dict[int, str] | None = None
    ) -> VerifiedInstallationAccess:
        return VerifiedInstallationAccess(
            github_user_id=github_user_id,
            installation_id=installation_id,
            repositories=repositories or {},
        )

    return factory


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
              pairing_codes,
              oauth_states,
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
