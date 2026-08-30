"""Deterministic finding match. A near-miss is needs_human_match, never a pass."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.evals.types import EvalLabel


class MatchResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    matched: list[tuple[EvalLabel, FindingCandidate]]
    unmatched_expected: list[EvalLabel]
    unmatched_actual: list[FindingCandidate]
    needs_human_match: bool


def _normalise_category(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _lines_overlap(left: EvalLabel, right: FindingCandidate) -> bool:
    return not (left.line_end < right.line_start or right.line_end < left.line_start)


def _structural_match(label: EvalLabel, candidate: FindingCandidate) -> bool:
    return (
        label.concern == candidate.concern
        and label.file_path == candidate.file_path
        and _lines_overlap(label, candidate)
        and _normalise_category(label.category) == _normalise_category(candidate.category)
    )


def _near_miss(label: EvalLabel, candidate: FindingCandidate) -> bool:
    if _structural_match(label, candidate):
        return False
    return (
        label.concern == candidate.concern
        and _normalise_category(label.category) == _normalise_category(candidate.category)
        and label.file_path != candidate.file_path
    )


def match_findings(
    expected: Sequence[EvalLabel],
    actual: Sequence[FindingCandidate],
) -> MatchResult:
    remaining_actual = list(actual)
    matched: list[tuple[EvalLabel, FindingCandidate]] = []
    unmatched_expected: list[EvalLabel] = []
    for label in expected:
        hit_index: int | None = None
        for index, candidate in enumerate(remaining_actual):
            if _structural_match(label, candidate):
                hit_index = index
                break
        if hit_index is None:
            unmatched_expected.append(label)
            continue
        matched.append((label, remaining_actual.pop(hit_index)))
    needs_human = any(
        _near_miss(label, candidate)
        for label in unmatched_expected
        for candidate in remaining_actual
    )
    return MatchResult(
        matched=matched,
        unmatched_expected=unmatched_expected,
        unmatched_actual=remaining_actual,
        needs_human_match=needs_human,
    )
