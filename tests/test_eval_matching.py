"""Failing tests for deterministic eval matching (master Task 9).

Match on concern, file, overlapping line range, and normalised category.
A semantic near-miss is needs_human_match, never a silent pass. An LLM does not
set ground truth.
"""

from __future__ import annotations


def _candidate(**overrides: object) -> object:
    from pr_reviewer.contracts.finding_candidate import FindingCandidate

    fields: dict[str, object] = {
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
    }
    fields.update(overrides)
    return FindingCandidate(**fields)


def _label(**overrides: object) -> object:
    from pr_reviewer.evals.types import EvalLabel

    fields: dict[str, object] = {
        "concern": "correctness",
        "category": "null-check",
        "file_path": "src/widget.py",
        "line_start": 10,
        "line_end": 12,
    }
    fields.update(overrides)
    return EvalLabel(**fields)


def test_match_on_concern_file_overlap_and_normalised_category() -> None:
    from pr_reviewer.evals.match_findings import match_findings

    expected = [_label(category="null_check")]
    actual = [_candidate(category="null-check", line_start=11, line_end=14)]
    result = match_findings(expected, actual)
    assert result.matched
    assert not result.unmatched_expected
    assert not result.unmatched_actual
    assert not result.needs_human_match


def test_no_line_overlap_is_not_a_match() -> None:
    from pr_reviewer.evals.match_findings import match_findings

    expected = [_label(line_start=10, line_end=12)]
    actual = [_candidate(line_start=40, line_end=44)]
    result = match_findings(expected, actual)
    assert not result.matched
    assert result.unmatched_expected
    assert result.unmatched_actual


def test_semantic_near_miss_needs_human_match_and_is_not_a_pass() -> None:
    from pr_reviewer.evals.match_findings import match_findings

    expected = [_label(file_path="src/widget.py")]
    actual = [
        _candidate(
            file_path="src/other.py",
            title="Missing null check",
            rationale="widget.value can be None.",
        )
    ]
    result = match_findings(expected, actual)
    assert result.needs_human_match
    assert not result.matched
