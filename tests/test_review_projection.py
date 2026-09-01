"""Task 27.3: a completed review's findings and per-agent reasoning land in Neon."""

from __future__ import annotations

import uuid

import pytest

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.control_plane.review_projection import AgentReasoningEntry, project_review
from pr_reviewer.db.client import connection


def _create_review_job() -> str:
    with connection() as conn:
        delivery_id = f"delivery-{uuid.uuid4()}"
        conn.execute(
            "insert into github_deliveries (id, event_name) values (%s, 'pull_request')",
            (delivery_id,),
        )
        row = conn.execute(
            "insert into review_jobs (delivery_id, status) values (%s, 'pending') returning id",
            (delivery_id,),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def _finding(review_job_id: str, *, finding_id: str | None = None) -> Finding:
    return Finding(
        id=finding_id or f"finding-{uuid.uuid4()}",
        review_job_id=review_job_id,
        concern="correctness",
        severity="high",
        category="null-check",
        file_path="widget.py",
        line_start=10,
        line_end=12,
        title="widget.value can be None",
        rationale="widget.value is read without a null check on this path.",
        evidence=["widget.py:10"],
        confidence=0.9,
        verified=True,
        verification_method="static",
        public_safe=True,
        status="posted",
    )


def test_project_review_writes_a_finding_row() -> None:
    review_job_id = _create_review_job()
    finding = _finding(review_job_id)

    project_review(review_job_id, [finding])

    with connection() as conn:
        row = conn.execute(
            """
            select review_job_id, concern, severity, category, file_path, line_start, line_end,
                   title, rationale, verified, verification_method, public_safe, status
            from review_findings where id = %s
            """,
            (finding.id,),
        ).fetchone()
    assert row is not None
    assert row["title"] == "widget.value can be None"
    assert row["rationale"] == finding.rationale
    assert row["verified"] is True
    assert row["status"] == "posted"


def test_project_review_writes_agent_reasoning_rows() -> None:
    review_job_id = _create_review_job()
    entry = AgentReasoningEntry(
        review_job_id=review_job_id,
        concern="security",
        reasoning="Checked for injected shell metacharacters in the new subprocess call.",
    )

    project_review(review_job_id, [], [entry])

    with connection() as conn:
        rows = conn.execute(
            "select concern, reasoning from agent_reasoning where review_job_id = %s",
            (review_job_id,),
        ).fetchall()
    assert [dict(row) for row in rows] == [
        {"concern": "security", "reasoning": entry.reasoning}
    ]


def test_project_review_never_writes_the_evidence_field() -> None:
    review_job_id = _create_review_job()
    finding = _finding(review_job_id)
    assert finding.evidence == ["widget.py:10"]

    project_review(review_job_id, [finding])

    with connection() as conn:
        with pytest.raises(Exception) as excinfo:
            conn.execute("select evidence from review_findings where id = %s", (finding.id,))
        assert "evidence" in str(excinfo.value).lower()


def test_project_review_rejects_a_finding_for_a_different_review_job() -> None:
    review_job_id = _create_review_job()
    other_job_id = _create_review_job()
    finding = _finding(other_job_id)

    with pytest.raises(ValueError, match="belongs to review_job_id"):
        project_review(review_job_id, [finding])
