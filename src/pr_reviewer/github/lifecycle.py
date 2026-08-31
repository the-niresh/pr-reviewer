"""PR webhook action policy (master Task 7).

handle_pull_request_event decides enqueue, ignore, or cancel. It does not mark older jobs
superseded: enqueue_review_job already does that for the same installation, repository, and
PR number. synchronize is enqueue, not a second verb.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pr_reviewer.contracts.github import GitHubDelivery

LifecycleKind = Literal["enqueue", "ignore", "cancel"]

_ENQUEUE_ACTIONS = frozenset({"opened", "reopened", "ready_for_review", "synchronize"})
_CANCEL_ACTIONS = frozenset({"closed", "converted_to_draft"})


def reviewed_head_is_current(reviewed_head_sha: str, live_head_sha: str) -> bool:
    """True only when the SHA we reviewed is still the PR head. Call this
    immediately before the posting API, not at the start of the review.
    """
    return reviewed_head_sha == live_head_sha


@dataclass(frozen=True)
class LifecycleDecision:
    kind: LifecycleKind


def handle_pull_request_event(delivery: GitHubDelivery) -> LifecycleDecision:
    if delivery.event != "pull_request":
        return LifecycleDecision(kind="ignore")
    if delivery.action in _CANCEL_ACTIONS:
        return LifecycleDecision(kind="cancel")
    if delivery.action not in _ENQUEUE_ACTIONS:
        return LifecycleDecision(kind="ignore")
    if delivery.action == "opened" and delivery.draft:
        return LifecycleDecision(kind="ignore")
    return LifecycleDecision(kind="enqueue")
