"""Concern-specific specialist reviewers. Off by default."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.contracts.review_context import PackedDiff, ReviewContextItem
from pr_reviewer.github.pull_request import PullRequestSnapshot
from pr_reviewer.reviewer.aggregate_findings import aggregate_findings
from pr_reviewer.security.instruction_sources import ReviewPolicy

SPECIALIST_CONCERNS = ("security", "correctness", "tests", "docs")

SpecialistFn = Callable[
    [PullRequestSnapshot, PackedDiff, Sequence[ReviewContextItem]],
    Sequence[FindingCandidate],
]


class SpecialistTimeout(Exception):
    """One specialist exceeded its deadline. Other concerns keep their findings."""

    def __init__(self, concern: str) -> None:
        self.concern = concern
        super().__init__(concern)


@dataclass(frozen=True)
class SpecialistRun:
    candidates: tuple[FindingCandidate, ...]
    timed_out_concerns: tuple[str, ...]
    missing_concerns: tuple[str, ...]


def specialists_enabled(policy: ReviewPolicy) -> bool:
    return policy.specialist_mode


def run_specialists(
    snapshot: PullRequestSnapshot,
    packed: PackedDiff,
    context: Sequence[ReviewContextItem],
    reviewers: Mapping[str, SpecialistFn],
    *,
    policy: ReviewPolicy,
) -> SpecialistRun:
    if not policy.specialist_mode:
        return SpecialistRun(candidates=(), timed_out_concerns=(), missing_concerns=())

    missing = tuple(concern for concern in SPECIALIST_CONCERNS if concern not in reviewers)
    collected: list[FindingCandidate] = []
    timed_out: list[str] = []
    for concern in SPECIALIST_CONCERNS:
        reviewer = reviewers.get(concern)
        if reviewer is None:
            continue
        try:
            collected.extend(reviewer(snapshot, packed, context))
        except SpecialistTimeout:
            timed_out.append(concern)
    merged = aggregate_findings(
        collected,
        repository=f"{snapshot.repo_owner}/{snapshot.repo_name}",
        head_sha=snapshot.head_sha,
    )
    return SpecialistRun(
        candidates=merged,
        timed_out_concerns=tuple(timed_out),
        missing_concerns=missing,
    )
