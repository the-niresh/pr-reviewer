"""Local signed-webhook to human-decision path. Runtime Task 10 hostname parts stay unfinished."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_post_review import FakeGitHub
from test_runner_job_protocol import pair_runner_assigned_to_repo
from test_webhook import _post_webhook, _pull_request_payload

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.contracts.github import PullRequestRef
from pr_reviewer.contracts.review_context import FilePatch
from pr_reviewer.db.client import connection
from pr_reviewer.web.app import app

REPO = Path(__file__).resolve().parent.parent
INSTALLATION_ID = 8501
REPOSITORY_ID = 95001
HEAD_SHA = "b" * 40
NEWER_SHA = "c" * 40
PATCH = "@@ -1,2 +1,3 @@\n def foo():\n     return 1\n+    return 2\n"


def _payload(action: str, head_sha: str) -> dict[str, Any]:
    payload = _pull_request_payload(
        action=action,
        installation_id=INSTALLATION_ID,
        repository_id=REPOSITORY_ID,
    )
    payload["pull_request"]["head"]["sha"] = head_sha
    return payload


def _job_row(delivery_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """
            select id, status, installation_id, github_repository_id, head_sha
            from review_jobs
            where delivery_id = %s
            """,
            (delivery_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _finding(job_id: str) -> Finding:
    return Finding.model_validate(
        {
            "id": "finding-local-1",
            "review_job_id": job_id,
            "concern": "correctness",
            "severity": "medium",
            "category": "null-check",
            "file_path": "app.py",
            "line_start": 3,
            "line_end": 3,
            "title": "Return value changed",
            "rationale": "foo now returns 2.",
            "evidence": ["app.py:3"],
            "confidence": 0.8,
            "verified": False,
            "verification_method": "not_applicable",
            "public_safe": True,
            "status": "draft",
        }
    )


def _post(
    github: FakeGitHub,
    finding: Finding,
    *,
    allow_public_post: bool,
    reviewed_sha: str,
    live_sha: str,
) -> Any:
    from pr_reviewer.github.post_review import RouteDecision, post_review, posting_idempotency_key
    from pr_reviewer.reviewer.hunk_format import render_hunks

    store: dict[str, Any] = {}
    ref = PullRequestRef(owner="acme", repository="widgets", number=7)
    return post_review(
        ref,
        reviewed_sha,
        [(finding, RouteDecision(allow_public_post=allow_public_post, confidentiality="ordinary"))],
        posting_idempotency_key(ref, reviewed_sha, "v1"),
        patches=[FilePatch(path="app.py", patch=PATCH, previous_path=None)],
        current_head_sha=lambda: live_sha,
        submit=github.submit,
        list_reviews=github.list_reviews,
        render_hunks=render_hunks,
        lookup=store.get,
        record_post=lambda posted: store.__setitem__(posted.idempotency_key, posted),
    )


def test_local_webhook_to_human_decision_path(
    make_verified_installation_access: Any,
) -> None:
    from pr_reviewer.containers.runtime import ContainerProbe
    from pr_reviewer.github.post_review import StalePullRequestHead
    from pr_reviewer.notifications.gate import route_finding
    from pr_reviewer.runner.modes import select_runtime_mode
    from pr_reviewer.security.instruction_sources import ReviewPolicy

    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (INSTALLATION_ID, "acme"),
        )
    credential = pair_runner_assigned_to_repo(
        INSTALLATION_ID, REPOSITORY_ID, make_verified_installation_access
    )
    client = TestClient(app)

    opened = _post_webhook(client, "delivery-local-open", _payload("opened", HEAD_SHA))
    assert opened.status_code == 202
    assert opened.json() == {"result": "enqueued"}
    queued = _job_row("delivery-local-open")
    assert queued["status"] == "pending"
    assert queued["installation_id"] == INSTALLATION_ID
    assert queued["github_repository_id"] == REPOSITORY_ID
    assert queued["head_sha"] == HEAD_SHA

    claimed = client.post(
        "/api/runner/jobs/claim",
        headers={"authorization": f"Bearer {credential.credential}"},
    )
    assert claimed.status_code == 200
    envelope = claimed.json()
    assert envelope["installation_id"] == INSTALLATION_ID
    assert envelope["repository_id"] == REPOSITORY_ID
    assert envelope["head_sha"] == HEAD_SHA
    running = _job_row("delivery-local-open")
    assert running["status"] == "running"
    assert str(running["id"]) == envelope["job_id"]

    probe = ContainerProbe(
        docker_cli_found=True,
        daemon_running=True,
        socket_accessible=True,
        image_pull_succeeded=True,
        runs_as_non_root=True,
        network_isolated=True,
        resource_limits_enforced=True,
        platform_supported=True,
        failures=(),
    )
    mode = select_runtime_mode(probe, "analysis_only")
    assert mode.granted_mode == "analysis_only"
    assert mode.verification_available is False
    assert mode.forces_human_approval is True

    finding = _finding(envelope["job_id"])
    gate = route_finding(finding, ReviewPolicy())
    assert gate.queue_for_human is True
    assert gate.allow_public_post is False

    github = FakeGitHub()
    held = _post(
        github,
        finding,
        allow_public_post=False,
        reviewed_sha=HEAD_SHA,
        live_sha=HEAD_SHA,
    )
    assert held is None
    assert github.submissions == []

    posted = _post(
        github,
        finding,
        allow_public_post=True,
        reviewed_sha=HEAD_SHA,
        live_sha=HEAD_SHA,
    )
    assert posted is not None
    assert len(github.submissions) == 1
    assert github.submissions[0].commit_id == HEAD_SHA

    synced = _post_webhook(client, "delivery-local-sync", _payload("synchronize", NEWER_SHA))
    assert synced.status_code == 202
    assert synced.json() == {"result": "enqueued"}
    stale = _job_row("delivery-local-open")
    fresh = _job_row("delivery-local-sync")
    assert stale["status"] == "superseded"
    assert fresh["status"] == "pending"
    assert fresh["head_sha"] == NEWER_SHA

    stale_github = FakeGitHub()
    with pytest.raises(StalePullRequestHead):
        _post(
            stale_github,
            finding,
            allow_public_post=True,
            reviewed_sha=HEAD_SHA,
            live_sha=NEWER_SHA,
        )
    assert stale_github.submissions == []
    assert len(github.submissions) == 1


def test_runtime_task_10_hosted_parts_stay_unfinished() -> None:
    text = (REPO / "docs" / "DEMO.md").read_text(encoding="utf-8")
    assert "https://reviewer.niresh.tech/api/github/webhook" in text
    assert "DNS A record" in text
    assert "GitHub App homepage, callback, and webhook URLs" in text
    assert "Runtime Task 10" in text
