"""Failing tests for eval mining and candidate contracts (master Task 9).

Mining produces candidates, never labels. A commit message is evidence, not ground truth.
FindingCandidate is a separate type from Finding: no inheritance, extra=forbid on both.
Private FoodSpector cases stay out of git via datasets/private/.

Imports of new evals modules stay inside test bodies.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from pr_reviewer.contracts.finding import Finding

REPO = Path(__file__).resolve().parent.parent


def _finding(**overrides: object) -> Finding:
    fields: dict[str, object] = {
        "id": "finding-1",
        "review_job_id": "job-1",
        "concern": "correctness",
        "severity": "high",
        "category": "null-check",
        "file_path": "src/widget.py",
        "line_start": 10,
        "line_end": 12,
        "title": "Missing null check",
        "rationale": "widget.value can be None.",
        "evidence": ["src/widget.py:10"],
        "confidence": 0.8,
        "verified": True,
        "verification_method": "sandbox",
        "public_safe": True,
        "status": "queued_for_human",
    }
    fields.update(overrides)
    return Finding(**fields)


def test_finding_candidate_rejects_verified_true() -> None:
    from pr_reviewer.contracts.finding_candidate import FindingCandidate

    with pytest.raises(ValidationError):
        FindingCandidate(
            concern="correctness",
            severity="high",
            category="null-check",
            file_path="src/widget.py",
            line_start=10,
            line_end=12,
            title="Missing null check",
            rationale="widget.value can be None.",
            evidence=["src/widget.py:10"],
            confidence=0.8,
            verified=True,
        )


def test_finding_is_not_a_finding_candidate() -> None:
    from pr_reviewer.contracts.finding_candidate import FindingCandidate

    finding = _finding()
    assert not isinstance(finding, FindingCandidate)
    assert FindingCandidate not in Finding.__mro__


def test_finding_and_candidate_forbid_unknown_fields() -> None:
    from pr_reviewer.contracts.finding_candidate import FindingCandidate

    with pytest.raises(ValidationError):
        _finding(unexpected_field=True)
    with pytest.raises(ValidationError):
        FindingCandidate(
            concern="correctness",
            severity="high",
            category="null-check",
            file_path="src/widget.py",
            line_start=10,
            line_end=12,
            title="Missing null check",
            rationale="widget.value can be None.",
            evidence=["src/widget.py:10"],
            confidence=0.8,
            review_job_id="job-1",
        )


def test_mining_emits_candidates_not_labels(tmp_path: Path) -> None:
    from pr_reviewer.evals.mine_candidates import mine_eval_candidates
    from pr_reviewer.evals.types import EvalCandidate, EvalLabel

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "widget.py").write_text("value = widget.value\n", encoding="utf-8")
    mined = mine_eval_candidates(repo, max_cases=10)
    assert mined
    assert all(isinstance(item, EvalCandidate) for item in mined)
    assert not any(isinstance(item, EvalLabel) for item in mined)
    for item in mined:
        assert getattr(item, "expected_labels", None) in (None, [])


def test_commit_message_is_evidence_not_ground_truth(tmp_path: Path) -> None:
    from pr_reviewer.evals.mine_candidates import mine_eval_candidates

    repo = tmp_path / "repo"
    repo.mkdir()
    mined = mine_eval_candidates(repo, max_cases=10)
    assert mined
    for item in mined:
        evidence = " ".join(item.source_evidence).lower()
        assert "fix null check" in evidence or item.source_evidence
        assert not getattr(item, "is_label", False)


def test_holdout_case_without_a_human_auditor_is_rejected() -> None:
    from pr_reviewer.evals.types import EvalCase, EvalLabel

    label = EvalLabel(
        concern="correctness",
        category="null-check",
        file_path="src/widget.py",
        line_start=10,
        line_end=12,
    )
    with pytest.raises((ValidationError, ValueError)):
        EvalCase(
            id="case-holdout-1",
            split="holdout",
            diff="@@ -1 +1 @@\n+value = widget.value",
            expected_labels=[label],
            source_evidence=["fix null check"],
            human_auditor=None,
            committed_at=date(2026, 1, 1),
        )


def test_split_is_time_based_not_random() -> None:
    from pr_reviewer.evals.types import EvalCase, EvalLabel, assign_time_split

    label = EvalLabel(
        concern="correctness",
        category="null-check",
        file_path="src/widget.py",
        line_start=10,
        line_end=12,
    )
    older = EvalCase(
        id="old",
        split="dev",
        diff="@@ old",
        expected_labels=[label],
        source_evidence=["older commit"],
        human_auditor="niresh",
        committed_at=date(2024, 1, 1),
    )
    newer = EvalCase(
        id="new",
        split="dev",
        diff="@@ new",
        expected_labels=[label],
        source_evidence=["newer commit"],
        human_auditor="niresh",
        committed_at=date(2026, 1, 1),
    )
    split = assign_time_split([newer, older], holdout_after=date(2025, 6, 1))
    by_id = {case.id: case.split for case in split}
    assert by_id["old"] == "dev"
    assert by_id["new"] == "holdout"


def test_private_foodspector_cases_are_gitignored_public_cases_are_not() -> None:
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "datasets/private/" in gitignore
    lines = [
        line.strip()
        for line in gitignore.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert "datasets/" not in lines
    assert "datasets/public/" not in lines
    assert (REPO / "datasets" / "public" / "eval_cases.jsonl").is_file()
    assert (REPO / "docs" / "EVAL_DATASET.md").is_file()
