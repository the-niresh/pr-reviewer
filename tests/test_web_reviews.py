"""Task 27.4: the web reviews API is scoped to the signed-in viewer's own repositories."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.control_plane.app import app
from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
from pr_reviewer.control_plane.github_oauth import LIVE_SIGN_IN_COOKIE_NAME, issue_live_sign_in
from pr_reviewer.control_plane.review_projection import AgentReasoningEntry, project_review
from pr_reviewer.db.client import connection


def _client(cookie: str | None = None) -> TestClient:
    cookies = {LIVE_SIGN_IN_COOKIE_NAME: cookie} if cookie is not None else {}
    return TestClient(app, cookies=cookies)


def _random_id() -> int:
    import random

    return random.randint(10_000_000, 2_000_000_000)


def _create_installation() -> int:
    installation_id = _random_id()
    with connection() as conn:
        conn.execute(
            "insert into installations (id, account_login) values (%s, 'octocat')",
            (installation_id,),
        )
    return installation_id


def _create_review_job_for_repo(installation_id: int, github_repository_id: int) -> str:
    with connection() as conn:
        delivery_id = f"delivery-{uuid.uuid4()}"
        conn.execute(
            "insert into github_deliveries (id, event_name) values (%s, 'pull_request')",
            (delivery_id,),
        )
        row = conn.execute(
            """
            insert into review_jobs (
              delivery_id, status, installation_id, github_repository_id,
              pull_request_number, head_sha
            )
            values (%s, 'succeeded', %s, %s, 3, 'cafef00d')
            returning id
            """,
            (delivery_id, installation_id, github_repository_id),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def _signed_in_cookie(installations: dict[int, dict[int, str]]) -> str:
    assertion = LiveInstallationAssertion(
        github_user_id=1, installations=installations, expires_at=2_000_000_000
    )
    return issue_live_sign_in(assertion)


def test_no_cookie_is_401() -> None:
    response = _client().get("/api/reviews")
    assert response.status_code == 401


def test_signed_in_with_no_installations_returns_an_empty_list() -> None:
    cookie = _signed_in_cookie({})
    response = _client(cookie).get("/api/reviews")
    assert response.status_code == 200
    assert response.json() == {"repositories": []}


def test_signed_in_viewer_sees_their_own_repositorys_findings_and_reasoning() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    review_job_id = _create_review_job_for_repo(installation_id, github_repository_id)
    finding = Finding(
        id=f"finding-{uuid.uuid4()}",
        review_job_id=review_job_id,
        concern="security",
        severity="critical",
        category="injection",
        file_path="app.py",
        line_start=5,
        line_end=5,
        title="Unsanitized shell call",
        rationale="user input reaches subprocess.run with shell=True.",
        evidence=["app.py:5"],
        confidence=0.95,
        verified=True,
        verification_method="static",
        public_safe=True,
        status="posted",
    )
    reasoning = AgentReasoningEntry(
        review_job_id=review_job_id, concern="security", reasoning="Traced the input to argv."
    )
    project_review(review_job_id, [finding], [reasoning])

    cookie = _signed_in_cookie({installation_id: {github_repository_id: "octocat/widget"}})
    response = _client(cookie).get("/api/reviews")

    assert response.status_code == 200
    body = response.json()
    assert len(body["repositories"]) == 1
    repo = body["repositories"][0]
    assert repo["repository_name"] == "octocat/widget"
    assert len(repo["reviews"]) == 1
    review = repo["reviews"][0]
    assert review["pull_request_number"] == 3
    assert review["findings"][0]["title"] == "Unsanitized shell call"
    assert review["reasoning"][0]["reasoning"] == reasoning.reasoning
    assert "evidence" not in review["findings"][0]


def test_a_repository_not_granted_to_the_viewer_is_404_not_403() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    _create_review_job_for_repo(installation_id, github_repository_id)

    cookie = _signed_in_cookie({installation_id: {_random_id(): "octocat/some-other-repo"}})
    response = _client(cookie).get(
        "/api/reviews",
        params={"installation_id": installation_id, "github_repository_id": github_repository_id},
    )
    assert response.status_code == 404


def test_an_uncontrolled_installation_is_404_not_403() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    _create_review_job_for_repo(installation_id, github_repository_id)

    cookie = _signed_in_cookie({})
    response = _client(cookie).get(
        "/api/reviews",
        params={"installation_id": installation_id, "github_repository_id": github_repository_id},
    )
    assert response.status_code == 404
