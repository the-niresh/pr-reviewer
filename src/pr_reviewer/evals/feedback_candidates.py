"""Promote repeated, audited feedback into eval candidates. Never rewrite policy."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pr_reviewer.security.instruction_sources import ReviewPolicy

FeedbackAction = Literal["approved", "rejected", "disputed", "edited"]


class FeedbackEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_fingerprint: str = Field(min_length=1)
    action: FeedbackAction
    actor: str = Field(min_length=1)
    human_audited: bool = False


class FeedbackCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_fingerprint: str = Field(min_length=1)
    human_audited: bool
    evidence_count: int = Field(ge=1)


@dataclass(frozen=True)
class FeedbackConsideration:
    candidates: tuple[FeedbackCandidate, ...]
    prompt_rewrites: tuple[str, ...]
    policy_changes: tuple[str, ...]
    label_changes: tuple[str, ...]
    routing_changes: tuple[str, ...]


def consider_feedback(
    events: Sequence[FeedbackEvent],
    *,
    prompts: Mapping[str, str],
    policy: ReviewPolicy,
    labels: Sequence[str],
    routing: str,
    min_repeats: int = 3,
) -> FeedbackConsideration:
    del prompts, policy, labels, routing
    grouped: dict[str, list[FeedbackEvent]] = defaultdict(list)
    for event in events:
        if event.action == "disputed":
            grouped[event.finding_fingerprint].append(event)
    candidates: list[FeedbackCandidate] = []
    for fingerprint in sorted(grouped):
        group = grouped[fingerprint]
        if len(group) < min_repeats:
            continue
        if not any(item.human_audited for item in group):
            continue
        candidates.append(
            FeedbackCandidate(
                finding_fingerprint=fingerprint,
                human_audited=True,
                evidence_count=len(group),
            )
        )
    return FeedbackConsideration(
        candidates=tuple(candidates),
        prompt_rewrites=(),
        policy_changes=(),
        label_changes=(),
        routing_changes=(),
    )
