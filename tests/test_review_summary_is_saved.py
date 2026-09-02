"""Sending side of review summary push, plus proof it actually lands in the hosted store.

The sending-side tests below only prove tui/push_review_summary.py builds the right payload and
calls whatever client it is given; they never touch a database and would still pass if
control_plane/review_projection.py's receiving endpoint were deleted. The tests further down
close that gap: they push through the real hosted path (an authenticated HTTP call to
POST /api/reviews/summary, the same route the TUI calls in production) and then read the row back
directly from Postgres, so a broken save path fails here, not just at the sender.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient

from pr_reviewer.contracts.runner import RunnerCredential, VerifiedInstallationAccess
from pr_reviewer.control_plane.pairing import (
    approve_pairing,
    create_pairing_code,
    exchange_pairing_code,
)
from pr_reviewer.db.client import connection
from pr_reviewer.tui.push_review_summary import (
    ReviewFindingSummary,
    ReviewSummaryClient,
    ReviewSummaryPush,
    build_summary_payload,
    push_review_summary,
)
from pr_reviewer.web.app import app

VerifiedAccessFactory = Callable[[int, int, dict[int, str] | None], VerifiedInstallationAccess]


class RecordingClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.should_fail = False

    def push(self, payload: dict[str, object]) -> None:
        if self.should_fail:
            raise RuntimeError("hosted plane unavailable")
        self.payloads.append(payload)


def test_build_summary_payload_uses_an_allowlist() -> None:
    summary = ReviewSummaryPush(
        review_job_id="job-1",
        installation_id=7010,
        github_repository_id=11,
        pull_request_number=42,
        head_sha="a" * 40,
        status="completed",
        findings=(
            ReviewFindingSummary(
                concern="security",
                severity="high",
                file_path="app.py",
                line_start=1,
                line_end=2,
                title="Leak",
                status="posted",
            ),
        ),
    )
    payload = build_summary_payload(summary)
    assert set(payload) == {
        "review_job_id",
        "installation_id",
        "github_repository_id",
        "pull_request_number",
        "head_sha",
        "status",
        "stopped_early",
        "findings",
    }
    assert "reasoning" not in payload


def test_push_payload_never_includes_reasoning() -> None:
    client = RecordingClient()
    push_review_summary(
        client,
        ReviewSummaryPush(
            review_job_id="job-1",
            installation_id=1,
            github_repository_id=2,
            pull_request_number=3,
            head_sha="b" * 40,
            status="completed",
        ),
    )
    assert client.payloads
    assert "reasoning" not in client.payloads[0]


def test_failed_push_does_not_raise() -> None:
    client = RecordingClient()
    client.should_fail = True
    result = push_review_summary(
        client,
        ReviewSummaryPush(
            review_job_id="job-1",
            installation_id=1,
            github_repository_id=2,
            pull_request_number=3,
            head_sha="c" * 40,
            status="completed",
        ),
    )
    assert result.ok is False
    assert client.payloads == []


# --- Below: the summary actually lands in the hosted store. ---


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pair_runner(
    installation_id: int,
    github_repository_id: int,
    make_verified_installation_access: VerifiedAccessFactory,
) -> str:
    """A runner authenticated and assigned to one repository, the same way a real device would
    reach this state: paired through control_plane/pairing.py, never fabricated by inserting a
    runners row directly.
    """
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
    """What the TUI actually has in production: an HTTP call to the hosted endpoint, not an
    in-memory fake. Wiring push_review_summary() to this is what makes these tests exercise the
    real save path built in control_plane/review_projection.py instead of only the sender.
    """

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


def _random_id() -> int:
    import random

    return random.randint(10_000_000, 2_000_000_000)


def test_pushed_review_summary_is_saved_in_the_hosted_store(
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
        pull_request_number=42,
        head_sha="a" * 40,
        status="completed",
        findings=(
            ReviewFindingSummary(
                concern="security",
                severity="high",
                file_path="app.py",
                line_start=1,
                line_end=2,
                title="Leak",
                status="posted",
            ),
        ),
    )

    result = push_review_summary(client, summary)
    assert result.ok is True

    with connection() as conn:
        job = conn.execute(
            "select status from review_jobs where id = %s", (review_job_id,)
        ).fetchone()
        findings = conn.execute(
            "select concern, severity, file_path, line_start, line_end, title, status "
            "from review_findings where review_job_id = %s",
            (review_job_id,),
        ).fetchall()
    assert job is not None
    assert job["status"] == "completed"
    assert len(findings) == 1
    assert findings[0]["title"] == "Leak"


def test_retried_push_updates_rather_than_duplicates(make_verified_installation_access) -> None:
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
        head_sha="b" * 40,
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

    assert push_review_summary(client, summary).ok is True
    # A network retry resends the identical payload; it must not create a second row.
    assert push_review_summary(client, summary).ok is True

    with connection() as conn:
        job_count = conn.execute(
            "select count(*) as c from review_jobs where id = %s", (review_job_id,)
        ).fetchone()
        finding_count = conn.execute(
            "select count(*) as c from review_findings where review_job_id = %s",
            (review_job_id,),
        ).fetchone()
    assert job_count["c"] == 1
    assert finding_count["c"] == 1


def test_review_with_zero_findings_still_saves_a_row(make_verified_installation_access) -> None:
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
        pull_request_number=1,
        head_sha="c" * 40,
        status="completed",
        findings=(),
    )

    assert push_review_summary(client, summary).ok is True

    with connection() as conn:
        job = conn.execute(
            "select status from review_jobs where id = %s", (review_job_id,)
        ).fetchone()
    # "Reviewed and found nothing" is a saved row, distinguishable from a review_job_id that was
    # never pushed at all (which would fetch None here).
    assert job is not None
    assert job["status"] == "completed"


def test_stopped_early_is_recorded_distinctly_from_completed(
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
        pull_request_number=1,
        head_sha="d" * 40,
        status="stopped_early",
        stopped_early=True,
        findings=(),
    )

    assert push_review_summary(client, summary).ok is True

    with connection() as conn:
        job = conn.execute(
            "select status from review_jobs where id = %s", (review_job_id,)
        ).fetchone()
    assert job is not None
    # Must never collapse to "completed": the web cannot tell a partial review from a finished
    # one unless this status stays its own value.
    assert job["status"] == "stopped_early"


def test_a_payload_carrying_reasoning_is_rejected_loudly(make_verified_installation_access) -> None:
    installation_id = _random_id()
    github_repository_id = _random_id()
    credential = _pair_runner(
        installation_id, github_repository_id, make_verified_installation_access
    )
    test_client = TestClient(app)

    payload = {
        "review_job_id": str(uuid.uuid4()),
        "installation_id": installation_id,
        "github_repository_id": github_repository_id,
        "pull_request_number": 1,
        "head_sha": "e" * 40,
        "status": "completed",
        "stopped_early": False,
        "findings": [],
        "reasoning": "should never be accepted",
    }
    response = test_client.post(
        "/api/reviews/summary",
        json=payload,
        headers={"Authorization": f"Bearer {credential}"},
    )
    # A mistake on the sending side must be visible, not a silent 200 that drops the field.
    assert response.status_code == 422
    assert "reasoning" in response.text
