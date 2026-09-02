"""Task 27.3: a completed review's findings and per-agent reasoning land in Neon."""

from __future__ import annotations

import random
import uuid

import pytest

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
from pr_reviewer.control_plane.review_projection import (
    ReceiptContextSourceInput,
    ReceiptInput,
    project_review,
    reviews_for_repository,
)
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


def _random_id() -> int:
    # Large and random, not sequential: four other processes share this test database.
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
            values (%s, 'succeeded', %s, %s, 7, 'deadbeef')
            returning id
            """,
            (delivery_id, installation_id, github_repository_id),
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


def test_reviews_for_repository_returns_data_for_a_granted_repository() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    review_job_id = _create_review_job_for_repo(installation_id, github_repository_id)
    finding = _finding(review_job_id)
    project_review(review_job_id, [finding])

    assertion = LiveInstallationAssertion(
        github_user_id=1,
        installations={installation_id: {github_repository_id: "octocat/widget"}},
        expires_at=2_000_000_000,
    )

    reviews = reviews_for_repository(assertion, installation_id, github_repository_id)

    assert reviews is not None
    assert len(reviews) == 1
    review = reviews[0]
    assert review.review_job_id == review_job_id
    assert review.pull_request_number == 7
    assert review.findings[0].title == finding.title


def test_reviews_for_repository_is_none_when_the_repository_is_not_granted() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    _create_review_job_for_repo(installation_id, github_repository_id)

    assertion = LiveInstallationAssertion(
        github_user_id=1,
        installations={installation_id: {_random_id(): "octocat/some-other-repo"}},
        expires_at=2_000_000_000,
    )

    assert reviews_for_repository(assertion, installation_id, github_repository_id) is None


def test_reviews_for_repository_is_none_when_the_installation_is_not_controlled() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    _create_review_job_for_repo(installation_id, github_repository_id)

    assertion = LiveInstallationAssertion(
        github_user_id=1, installations={}, expires_at=2_000_000_000
    )

    assert reviews_for_repository(assertion, installation_id, github_repository_id) is None


def _create_model_call(review_job_id: str, prompt_version_id: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            insert into model_calls (review_job_id, prompt_version_id, provider, model_name,
                                      input_tokens, output_tokens, cost_usd)
            values (%s, %s, 'openai', 'gpt-5-mini', 100, 50, 0.01)
            """,
            (review_job_id, prompt_version_id),
        )


def _create_prompt_version() -> str:
    with connection() as conn:
        row = conn.execute(
            "insert into prompt_versions (name, version, content) values "
            "('reviewer', %s, 'content') returning id",
            (str(uuid.uuid4()),),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def test_project_review_writes_a_verified_receipt_with_context_sources() -> None:
    review_job_id = _create_review_job()
    prompt_version_id = _create_prompt_version()
    _create_model_call(review_job_id, prompt_version_id)
    finding = _finding(review_job_id)
    receipt = ReceiptInput(
        finding_id=finding.id,
        review_job_id=review_job_id,
        prompt_version_id=prompt_version_id,
        context_sources=(
            ReceiptContextSourceInput(kind="diff", name="pr-diff", reference="hunk-1"),
        ),
        verified=True,
        sandbox_run_id="run-1",
        command_id="cmd-1",
        verification_detail="sandbox command exited 0",
    )

    project_review(review_job_id, [finding], receipts=[receipt])

    with connection() as conn:
        row = conn.execute(
            "select verified, sandbox_run_id, command_id, verification_detail, model_call_id "
            "from review_findings where id = %s",
            (finding.id,),
        ).fetchone()
        sources = conn.execute(
            "select kind, name, reference from finding_context_sources where finding_id = %s",
            (finding.id,),
        ).fetchall()
    assert row is not None
    assert row["verified"] is True
    assert row["sandbox_run_id"] == "run-1"
    assert row["command_id"] == "cmd-1"
    assert row["verification_detail"] == "sandbox command exited 0"
    assert row["model_call_id"] is not None
    assert [dict(source) for source in sources] == [
        {"kind": "diff", "name": "pr-diff", "reference": "hunk-1"}
    ]


def test_reviews_for_repository_renders_verified_and_asserted_receipts_distinctly() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    review_job_id = _create_review_job_for_repo(installation_id, github_repository_id)
    prompt_version_id = _create_prompt_version()
    _create_model_call(review_job_id, prompt_version_id)

    verified_finding = _finding(review_job_id, finding_id=f"verified-{uuid.uuid4()}")
    verified_receipt = ReceiptInput(
        finding_id=verified_finding.id,
        review_job_id=review_job_id,
        prompt_version_id=prompt_version_id,
        context_sources=(
            ReceiptContextSourceInput(kind="diff", name="pr-diff", reference="hunk-1"),
        ),
        verified=True,
        sandbox_run_id="run-2",
        command_id="cmd-2",
        verification_detail="static checks passed",
    )

    asserted_finding = Finding(
        id=f"asserted-{uuid.uuid4()}",
        review_job_id=review_job_id,
        concern="docs",
        severity="low",
        category="typo",
        file_path="README.md",
        line_start=1,
        line_end=1,
        title="Typo in README",
        rationale="Says 'recieve' instead of 'receive'.",
        evidence=["README.md:1"],
        confidence=0.6,
        verified=False,
        verification_method="not_applicable",
        public_safe=True,
        status="posted",
    )
    asserted_receipt = ReceiptInput(
        finding_id=asserted_finding.id,
        review_job_id=review_job_id,
        prompt_version_id=prompt_version_id,
        context_sources=(
            ReceiptContextSourceInput(kind="diff", name="pr-diff", reference="hunk-2"),
        ),
        verified=False,
        verification_reason="A typo cannot be run in a sandbox.",
    )

    project_review(
        review_job_id,
        [verified_finding, asserted_finding],
        receipts=[verified_receipt, asserted_receipt],
    )

    assertion = LiveInstallationAssertion(
        github_user_id=1,
        installations={installation_id: {github_repository_id: "octocat/widget"}},
        expires_at=2_000_000_000,
    )
    reviews = reviews_for_repository(assertion, installation_id, github_repository_id)

    assert reviews is not None
    findings_by_id = {finding.id: finding for finding in reviews[0].findings}
    verified_summary = findings_by_id[verified_finding.id]
    asserted_summary = findings_by_id[asserted_finding.id]

    assert verified_summary.receipt is not None
    assert verified_summary.receipt.verification_status == "verified"
    assert verified_summary.receipt.sandbox_run_id == "run-2"
    assert verified_summary.receipt.cost_usd is not None
    assert float(verified_summary.receipt.cost_usd) == 0.01

    assert asserted_summary.receipt is not None
    assert asserted_summary.receipt.verification_status == "asserted"
    assert asserted_summary.receipt.verification_reason == "A typo cannot be run in a sandbox."
    assert asserted_summary.receipt.sandbox_run_id is None
