"""Failing tests for eval mining and candidate contracts (master Task 9).

Mining produces candidates, never labels. A commit message is evidence, not ground truth.
FindingCandidate is a separate type from Finding: no inheritance, extra=forbid on both.
Private FoodSpector cases stay out of git via datasets/private/.

Imports of new evals modules stay inside test bodies.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pr_reviewer.contracts.finding import Finding

REPO = Path(__file__).resolve().parent.parent


def _finding(**overrides: Any) -> Finding:
    fields: dict[str, Any] = {
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
        FindingCandidate(  # type: ignore[call-arg]
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
    assert Finding not in FindingCandidate.__mro__


def test_finding_and_candidate_forbid_unknown_fields() -> None:
    from pr_reviewer.contracts.finding_candidate import FindingCandidate

    with pytest.raises(ValidationError):
        _finding(unexpected_field=True)
    with pytest.raises(ValidationError):
        FindingCandidate(  # type: ignore[call-arg]
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


def _init_git_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "eval@test.example"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Eval Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def _commit_file(repo: Path, relative: str, content: str, message: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "--", relative], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def _commit_file_at(
    repo: Path, relative: str, content: str, message: str, when: str
) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
    }
    subprocess.run(["git", "add", "--", relative], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def _git_repo_with_commit(root: Path, message: str) -> Path:
    repo = _init_git_repo(root)
    _commit_file(repo, "src/widget.py", "value = widget.value\n", message)
    return repo


def test_mining_emits_candidates_not_labels(tmp_path: Path) -> None:
    from pr_reviewer.evals.mine_candidates import mine_eval_candidates
    from pr_reviewer.evals.types import EvalCandidate, EvalLabel

    repo = _git_repo_with_commit(tmp_path, "fix null check")
    mined = mine_eval_candidates(repo, max_cases=10).candidates
    assert mined
    assert all(isinstance(item, EvalCandidate) for item in mined)
    assert not any(isinstance(item, EvalLabel) for item in mined)
    assert "expected_labels" not in EvalCandidate.model_fields


def test_mining_survives_a_non_utf8_byte_in_the_repo(tmp_path: Path) -> None:
    from pr_reviewer.evals.mine_candidates import mine_eval_candidates

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "eval@test.example"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Eval Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "notes.txt").write_bytes(b"ascii prefix \xff suffix\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add notes"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    patch = subprocess.run(
        ["git", "-C", str(repo), "log", "-p", "--pretty=format:"],
        check=True,
        capture_output=True,
    )
    assert b"\xff" in patch.stdout
    mined = mine_eval_candidates(repo, max_cases=10)
    assert mined.candidates
    assert "\ufffd" in mined.candidates[0].diff or "suffix" in mined.candidates[0].diff


def test_commit_message_is_evidence_not_ground_truth(tmp_path: Path) -> None:
    from pr_reviewer.evals.mine_candidates import mine_eval_candidates
    from pr_reviewer.evals.types import EvalCandidate

    repo = _git_repo_with_commit(tmp_path, "fix null check")
    mined = mine_eval_candidates(repo, max_cases=10).candidates
    assert mined
    for item in mined:
        evidence = " ".join(item.source_evidence).lower()
        assert "fix null check" in evidence
        assert "expected_labels" not in EvalCandidate.model_fields
        assert "is_label" not in EvalCandidate.model_fields


def test_mining_emits_one_candidate_per_commit(tmp_path: Path) -> None:
    from pr_reviewer.evals.mine_candidates import mine_eval_candidates

    subjects = (
        "fix null check in widget",
        "add alpha helper",
        "document beta flag",
    )
    marks = (
        ("src/widget.py", "WIDGET_UNIQUE = 1\n"),
        ("src/alpha.py", "ALPHA_UNIQUE = 1\n"),
        ("src/beta.py", "BETA_UNIQUE = 1\n"),
    )
    repo = _init_git_repo(tmp_path)
    for (relative, content), subject in zip(marks, subjects, strict=True):
        _commit_file(repo, relative, content, subject)

    mined = mine_eval_candidates(repo, max_cases=10).candidates
    assert len(mined) == 3
    by_subject = {item.source_evidence[0]: item for item in mined}
    assert set(by_subject) == set(subjects)
    for (relative, content), subject in zip(marks, subjects, strict=True):
        candidate = by_subject[subject]
        mark = content.split("=", 1)[0].strip()
        assert mark in candidate.diff
        assert relative in candidate.diff
        for other_subject, other_mark in zip(subjects, marks, strict=True):
            if other_subject == subject:
                continue
            assert other_subject not in " ".join(candidate.source_evidence)
            other_token = other_mark[1].split("=", 1)[0].strip()
            assert other_token not in candidate.diff


def test_oversized_commit_is_skipped_with_a_recorded_reason(tmp_path: Path) -> None:
    from pr_reviewer.context_budget import context_budget_for_model
    from pr_reviewer.evals.mine_candidates import estimate_diff_tokens, mine_eval_candidates

    budget = context_budget_for_model("gpt-4o-mini")
    repo = _init_git_repo(tmp_path)
    _commit_file(repo, "src/small.py", "SMALL_UNIQUE = 1\n", "add small helper")
    huge = "H" * (budget.tokens * 4 + 64) + "\n"
    _commit_file(repo, "src/huge.py", huge, "add huge blob")
    _commit_file(repo, "src/other.py", "OTHER_UNIQUE = 1\n", "add other helper")

    result = mine_eval_candidates(repo, max_cases=10)
    assert len(result.candidates) == 2
    assert {item.source_evidence[0] for item in result.candidates} == {
        "add small helper",
        "add other helper",
    }
    assert all("huge blob" not in " ".join(item.source_evidence) for item in result.candidates)
    assert len(result.skipped) == 1
    skipped = result.skipped[0]
    assert skipped.reason == "diff_exceeds_packed_budget"
    assert skipped.subject == "add huge blob"
    assert skipped.token_budget == budget.tokens
    assert skipped.token_count > budget.tokens
    for item in result.candidates:
        assert estimate_diff_tokens(item.diff) <= budget.tokens


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


def _dated_repo(root: Path) -> Path:
    repo = _init_git_repo(root)
    marks = (
        ("src/jun1.py", "JUN1 = 1\n", "june one", "2026-06-05T12:00:00"),
        ("src/jun2.py", "JUN2 = 1\n", "june two", "2026-06-15T12:00:00"),
        ("src/jun3.py", "JUN3 = 1\n", "june three", "2026-06-25T12:00:00"),
        ("src/jul1.py", "JUL1 = 1\n", "july one", "2026-07-05T12:00:00"),
        ("src/jul2.py", "JUL2 = 1\n", "july two", "2026-07-15T12:00:00"),
        ("src/jul3.py", "JUL3 = 1\n", "july three", "2026-07-25T12:00:00"),
    )
    for relative, content, message, when in marks:
        _commit_file_at(repo, relative, content, message, when)
    return repo


def test_since_until_keeps_only_commits_inside_the_window(tmp_path: Path) -> None:
    from pr_reviewer.evals.mine_candidates import mine_eval_candidates

    repo = _dated_repo(tmp_path)
    mined = mine_eval_candidates(
        repo,
        max_cases=10,
        since=date(2026, 6, 1),
        until=date(2026, 7, 1),
    ).candidates
    subjects = [item.source_evidence[0] for item in mined]
    assert subjects == ["june three", "june two", "june one"] or set(subjects) == {
        "june one",
        "june two",
        "june three",
    }
    assert all(item.committed_at is not None and item.committed_at.month == 6 for item in mined)
    assert all("july" not in item.source_evidence[0] for item in mined)


def test_max_cases_without_per_window_still_takes_newest(tmp_path: Path) -> None:
    from pr_reviewer.evals.mine_candidates import mine_eval_candidates

    repo = _dated_repo(tmp_path)
    mined = mine_eval_candidates(repo, max_cases=2).candidates
    subjects = [item.source_evidence[0] for item in mined]
    assert subjects == ["july three", "july two"]


def test_per_window_samples_evenly_instead_of_newest(tmp_path: Path) -> None:
    from pr_reviewer.evals.mine_candidates import mine_eval_candidates

    repo = _init_git_repo(tmp_path)
    for index in range(10):
        day = f"{index + 1:02d}"
        _commit_file_at(
            repo,
            f"src/c{index}.py",
            f"C{index} = 1\n",
            f"commit-{index}",
            f"2026-06-{day}T12:00:00",
        )
    newest = mine_eval_candidates(repo, max_cases=3).candidates
    newest_subjects = [item.source_evidence[0] for item in newest]
    assert newest_subjects == ["commit-9", "commit-8", "commit-7"]
    sampled = mine_eval_candidates(repo, per_window=3).candidates
    sampled_subjects = [item.source_evidence[0] for item in sampled]
    assert len(sampled_subjects) == 3
    assert sampled_subjects != newest_subjects
    assert "commit-0" in sampled_subjects


def test_write_sheet_prints_per_month_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from pr_reviewer.evals.holdout_sheet import main, write_candidate_sheet

    repo = _dated_repo(tmp_path)
    sheet = tmp_path / "sheet.jsonl"
    stats = write_candidate_sheet(
        repo,
        sheet,
        since=date(2026, 6, 1),
        until=date(2026, 8, 1),
        per_window=4,
    )
    assert stats.per_month["2026-06"] >= 1
    assert stats.per_month["2026-07"] >= 1
    code = main(
        [
            "write-sheet",
            "--repo",
            str(repo),
            "--out",
            str(tmp_path / "cli.jsonl"),
            "--since",
            "2026-06-01",
            "--until",
            "2026-07-01",
            "--per-window",
            "2",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "2026-06:" in captured.out
    assert "2026-07:" not in captured.out

