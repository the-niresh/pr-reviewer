"""Failing tests for PR lifecycle actions (master Task 7).

handle_pull_request_event decides whether a webhook should enqueue, ignore, or cancel. It does
not reimplement supersession: enqueue_review_job already marks older pending/running jobs for the
same installation, repository, and PR number as superseded. These tests pin the action policy
and verify that existing enqueue behaviour covers synchronize.

Imports of github.lifecycle stay inside test bodies so a missing module fails the test instead
of interrupting collection.
"""

from __future__ import annotations

from pr_reviewer.db.client import connection
from pr_reviewer.jobs import enqueue_review_job

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
NEWER_HEAD_SHA = "c" * 40


def _identity():
    from pr_reviewer.contracts.github import RepositoryIdentity

    return RepositoryIdentity(
        installation_id=7201,
        repository_id=82001,
        owner="acme",
        name="widgets",
    )


def _delivery(
    *,
    action: str,
    draft: bool = False,
    head_sha: str = HEAD_SHA,
    delivery_id: str = "delivery-lifecycle-1",
):
    from pr_reviewer.contracts.github import GitHubDelivery, PullRequestRef

    identity = _identity()
    return GitHubDelivery(
        delivery_id=delivery_id,
        event="pull_request",
        action=action,
        repository_identity=identity,
        pull_request=PullRequestRef(
            owner=identity.owner, repository=identity.name, number=12
        ),
        draft=draft,
        base_sha=BASE_SHA,
        head_sha=head_sha,
    )


def test_opened_non_draft_is_enqueued() -> None:
    from pr_reviewer.github.lifecycle import handle_pull_request_event

    decision = handle_pull_request_event(_delivery(action="opened", draft=False))
    assert decision.kind == "enqueue"


def test_opened_draft_is_ignored() -> None:
    from pr_reviewer.github.lifecycle import handle_pull_request_event

    decision = handle_pull_request_event(_delivery(action="opened", draft=True))
    assert decision.kind == "ignore"


def test_reopened_is_enqueued() -> None:
    from pr_reviewer.github.lifecycle import handle_pull_request_event

    decision = handle_pull_request_event(_delivery(action="reopened"))
    assert decision.kind == "enqueue"


def test_ready_for_review_is_enqueued() -> None:
    from pr_reviewer.github.lifecycle import handle_pull_request_event

    decision = handle_pull_request_event(_delivery(action="ready_for_review"))
    assert decision.kind == "enqueue"


def test_synchronize_is_enqueued_not_a_new_lifecycle_verb() -> None:
    from pr_reviewer.github.lifecycle import handle_pull_request_event

    decision = handle_pull_request_event(_delivery(action="synchronize", head_sha=NEWER_HEAD_SHA))
    assert decision.kind == "enqueue"


def test_converted_to_draft_is_cancelled() -> None:
    from pr_reviewer.github.lifecycle import handle_pull_request_event

    decision = handle_pull_request_event(_delivery(action="converted_to_draft", draft=True))
    assert decision.kind == "cancel"


def test_closed_is_cancelled() -> None:
    from pr_reviewer.github.lifecycle import handle_pull_request_event

    decision = handle_pull_request_event(_delivery(action="closed"))
    assert decision.kind == "cancel"


def test_unsupported_action_is_ignored() -> None:
    from pr_reviewer.github.lifecycle import handle_pull_request_event

    decision = handle_pull_request_event(_delivery(action="labeled"))
    assert decision.kind == "ignore"


def test_repository_identity_uses_numeric_installation_and_repository_ids() -> None:
    identity = _identity()
    assert identity.installation_id == 7201
    assert identity.repository_id == 82001
    delivery = _delivery(action="opened")
    assert delivery.repository_identity.installation_id == 7201
    assert delivery.repository_identity.repository_id == 82001


def test_enqueue_review_job_already_supersedes_older_active_jobs_for_the_same_pr() -> None:
    """Runtime Task 3 already did this. Synchronize must enqueue, not grow a second copy."""
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (7201, "acme"),
        )

    payload_old = {
        "action": "opened",
        "installation": {"id": 7201},
        "repository": {"id": 82001, "name": "widgets"},
        "pull_request": {
            "number": 12,
            "base": {"sha": BASE_SHA},
            "head": {"sha": HEAD_SHA},
        },
    }
    payload_new = {
        **payload_old,
        "action": "synchronize",
        "pull_request": {
            "number": 12,
            "base": {"sha": BASE_SHA},
            "head": {"sha": NEWER_HEAD_SHA},
        },
    }
    assert enqueue_review_job("delivery-lifecycle-old", "pull_request", payload_old) == "enqueued"
    assert enqueue_review_job("delivery-lifecycle-new", "pull_request", payload_new) == "enqueued"

    with connection() as conn:
        rows = conn.execute(
            """
            select delivery_id, status, head_sha
            from review_jobs
            where installation_id = %s and github_repository_id = %s and pull_request_number = 12
            order by created_at
            """,
            (7201, 82001),
        ).fetchall()
    assert [row["delivery_id"] for row in rows] == [
        "delivery-lifecycle-old",
        "delivery-lifecycle-new",
    ]
    assert rows[0]["status"] == "superseded"
    assert rows[0]["head_sha"] == HEAD_SHA
    assert rows[1]["status"] == "pending"
    assert rows[1]["head_sha"] == NEWER_HEAD_SHA
