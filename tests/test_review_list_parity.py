"""TUI and hosted list must show the same saved review record.

The old version of this test only called build_summary_payload and asserted the returned dict
held the values just put into it -- it never touched the hosted plane, never called the web
reviews endpoint's own query, and would still pass with the entire control plane deleted. This
version pushes a real summary through the hosted path built in control_plane/review_projection.py
(the same POST /api/reviews/summary route the TUI calls) and reads it back through
reviews_for_repository, the exact function GET /api/reviews calls for apps/web's reviews page. If
either side drifted -- a renamed field, a dropped column -- one of these assertions fails.
"""

from __future__ import annotations

import hashlib
import random
import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient

from pr_reviewer.contracts.runner import RunnerCredential, VerifiedInstallationAccess
from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
from pr_reviewer.control_plane.pairing import (
    approve_pairing,
    create_pairing_code,
    exchange_pairing_code,
)
from pr_reviewer.control_plane.review_projection import reviews_for_repository
from pr_reviewer.db.client import connection
from pr_reviewer.tui.push_review_summary import (
    ReviewFindingSummary,
    ReviewSummaryClient,
    ReviewSummaryPush,
    push_review_summary,
)
from pr_reviewer.web.app import app

VerifiedAccessFactory = Callable[[int, int, dict[int, str] | None], VerifiedInstallationAccess]


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _random_id() -> int:
    return random.randint(10_000_000, 2_000_000_000)


def _pair_runner(
    installation_id: int,
    github_repository_id: int,
    make_verified_installation_access: VerifiedAccessFactory,
) -> str:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s) on conflict do nothing",
            (installation_id, "acme"),
        )

    verifier = f"verifier-{uuid.uuid4()}"
    challenge = create_pairing_code("laptop", _sha256_hex(verifier))
    access = make_verified_installation_access(
        42, installation_id, {github_repository_id: "widgets"}
    )
    approve_pairing(challenge.code, access, [github_repository_id])
    result = exchange_pairing_code(challenge.code, verifier)
    assert isinstance(result, RunnerCredential)
    return result.credential


class HttpReviewSummaryClient(ReviewSummaryClient):
    def __init__(self, test_client: TestClient, credential: str) -> None:
        self._test_client = test_client
        self._credential = credential

    def push(self, payload: dict[str, object]) -> None:
        response = self._test_client.post(
            "/api/reviews/summary",
            json=payload,
            headers={"Authorization": f"Bearer {self._credential}"},
        )
        if response.status_code != 200:
            raise RuntimeError(f"hosted push rejected: {response.status_code} {response.text}")


def test_tui_pushed_review_matches_the_hosted_summary_the_web_page_reads(
    make_verified_installation_access,
) -> None:
    installation_id = _random_id()
    github_repository_id = _random_id()
    credential = _pair_runner(
        installation_id, github_repository_id, make_verified_installation_access
    )
    client = HttpReviewSummaryClient(TestClient(app), credential)

    review_job_id = str(uuid.uuid4())
    summary = ReviewSummaryPush(
        review_job_id=review_job_id,
        installation_id=installation_id,
        github_repository_id=github_repository_id,
        pull_request_number=7,
        head_sha="d" * 40,
        status="completed",
        findings=(
            ReviewFindingSummary(
                concern="tests",
                severity="medium",
                file_path="tests/test_app.py",
                line_start=4,
                line_end=4,
                title="Missing test",
                status="posted",
            ),
        ),
    )

    result = push_review_summary(client, summary)
    assert result.ok is True

    # This is not a second, parallel read path: it is the literal function
    # control_plane/review_projection.py's GET /api/reviews route calls, which is what
    # apps/web/src/app/dashboard/reviews/page.tsx fetches from.
    assertion = LiveInstallationAssertion(
        github_user_id=1,
        installations={installation_id: {github_repository_id: "acme/widgets"}},
        expires_at=2_000_000_000,
    )
    reviews = reviews_for_repository(assertion, installation_id, github_repository_id)

    assert reviews is not None
    matching = [review for review in reviews if review.review_job_id == review_job_id]
    assert len(matching) == 1
    review = matching[0]

    assert review.pull_request_number == summary.pull_request_number
    assert review.head_sha == summary.head_sha
    assert review.status == summary.status
    assert len(review.findings) == 1

    pushed_finding = summary.findings[0]
    read_finding = review.findings[0]
    assert read_finding.concern == pushed_finding.concern
    assert read_finding.severity == pushed_finding.severity
    assert read_finding.file_path == pushed_finding.file_path
    assert read_finding.line_start == pushed_finding.line_start
    assert read_finding.line_end == pushed_finding.line_end
    assert read_finding.title == pushed_finding.title
    assert read_finding.status == pushed_finding.status
