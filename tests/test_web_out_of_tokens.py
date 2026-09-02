"""Task 33.E2: the web reviews page must say plainly when tokens ran out, never a raw error.

Follows tests/test_web_reviews.py's harness: a real review_jobs row read back through the same
GET /api/reviews route apps/web/src/app/dashboard/reviews/page.tsx fetches from. Also guards
page.tsx's own source the way test_web_never_accepts_a_key.py guards other pages, so a regression
in the component -- not just the API payload -- turns this test red too.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from pr_reviewer.control_plane.app import app
from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
from pr_reviewer.control_plane.github_oauth import LIVE_SIGN_IN_COOKIE_NAME, issue_live_sign_in
from pr_reviewer.control_plane.review_projection import STOPPED_EARLY_MESSAGE
from pr_reviewer.db.client import connection

PAGE = (
    Path(__file__).resolve().parent.parent
    / "apps"
    / "web"
    / "src"
    / "app"
    / "dashboard"
    / "reviews"
    / "page.tsx"
)

# A regression that made the badge always render the raw status -- including for
# stopped_early -- would still pass the API-level tests below (they never touch page.tsx) but
# would show the bare enum on screen. This regex names exactly that mistake.
RAW_STATUS_ONLY_BADGE = re.compile(r'<Badge variant="muted">\{review\.status\}</Badge>')
STOPPED_EARLY_HANDLED = re.compile(r'review\.stopped_early\s*\?\s*"Stopped early"')


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


def _create_review_job(installation_id: int, github_repository_id: int, status: str) -> str:
    with connection() as conn:
        row = conn.execute(
            """
            insert into review_jobs (
              delivery_id, status, installation_id, github_repository_id,
              pull_request_number, head_sha
            )
            values (null, %s, %s, %s, 9, %s)
            returning id
            """,
            (status, installation_id, github_repository_id, "f" * 40),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def _signed_in_cookie(installations: dict[int, dict[int, str]]) -> str:
    assertion = LiveInstallationAssertion(
        github_user_id=1, installations=installations, expires_at=2_000_000_000
    )
    return issue_live_sign_in(assertion)


def test_stopped_early_review_carries_a_plain_words_message_not_the_raw_status() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    review_job_id = _create_review_job(installation_id, github_repository_id, "stopped_early")

    cookie = _signed_in_cookie({installation_id: {github_repository_id: "octocat/widget"}})
    response = _client(cookie).get("/api/reviews")

    assert response.status_code == 200
    review = response.json()["repositories"][0]["reviews"][0]
    assert review["review_job_id"] == review_job_id
    assert review["status"] == "stopped_early"
    assert review["stopped_early"] is True
    assert review["stopped_early_message"] == STOPPED_EARLY_MESSAGE
    # The two things this must never become: a raw provider payload, or the bare enum token
    # standing in for an explanation.
    assert "{" not in review["stopped_early_message"]
    assert review["stopped_early_message"] != "stopped_early"
    assert "ran out of tokens" in review["stopped_early_message"]


def test_a_completed_review_carries_no_stopped_early_message() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    _create_review_job(installation_id, github_repository_id, "completed")

    cookie = _signed_in_cookie({installation_id: {github_repository_id: "octocat/widget"}})
    response = _client(cookie).get("/api/reviews")

    review = response.json()["repositories"][0]["reviews"][0]
    assert review["status"] == "completed"
    assert review["stopped_early"] is False
    assert review["stopped_early_message"] is None


def test_the_page_marks_stopped_early_distinctly_from_every_other_status() -> None:
    source = PAGE.read_text(encoding="utf-8")
    assert STOPPED_EARLY_HANDLED.search(source), (
        "page.tsx must render a distinct label for a stopped_early review, not the raw status"
    )
    assert not RAW_STATUS_ONLY_BADGE.search(source), (
        "page.tsx must not fall back to a single badge that always shows the raw status for "
        "every review -- a stopped_early review would then look identical to any other one"
    )


def test_the_page_renders_the_plain_words_message_for_a_stopped_early_review() -> None:
    source = PAGE.read_text(encoding="utf-8")
    assert "stopped_early_message" in source
    assert "review.reason" not in source
    assert "finding.reason" not in source


def test_the_raw_status_badge_pattern_actually_catches_a_violation() -> None:
    # A guard that can never turn red proves nothing. This is the exact line the reviews page
    # used to render for every status before this task; confirm the pattern would catch it if
    # it ever came back, and would not false-positive on the fixed version.
    assert RAW_STATUS_ONLY_BADGE.search('<Badge variant="muted">{review.status}</Badge>')
    fixed = '<Badge variant={review.stopped_early ? "warning" : "muted"}>'
    assert not RAW_STATUS_ONLY_BADGE.search(fixed)
    assert STOPPED_EARLY_HANDLED.search('{review.stopped_early ? "Stopped early" : review.status}')
