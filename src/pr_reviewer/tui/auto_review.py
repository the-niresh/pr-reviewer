"""Auto-review while the Textual TUI is running.

PR open and synchronize events reuse github.lifecycle policy. Supersession is tracked in-process
because the TUI does not own hosted review_jobs rows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from pr_reviewer.contracts.github import GitHubDelivery, PullRequestRef, RepositoryIdentity
from pr_reviewer.github.lifecycle import handle_pull_request_event

TUI_CLOSED_AUTO_REVIEW_MESSAGE = (
    "No review runs while the TUI is closed. Open reviewer again to watch live reviews."
)

AutoReviewOutcomeKind = Literal[
    "started",
    "superseded",
    "ignored",
    "cancelled",
    "not_running",
]


@dataclass(frozen=True)
class PullRequestSyncEvent:
    action: str
    pull_request_number: int
    head_sha: str
    draft: bool = False
    installation_id: int = 7201
    repository_id: int = 82001
    owner: str = "acme"
    repository: str = "widgets"


@dataclass(frozen=True)
class AutoReviewOutcome:
    kind: AutoReviewOutcomeKind
    pull_request_number: int
    head_sha: str = ""
    previous_head_sha: str = ""


class AutoReviewEventSource(Protocol):
    def poll(self) -> list[PullRequestSyncEvent]: ...


class AutoReviewCoordinator:
    def __init__(
        self,
        *,
        on_start_review: Callable[[PullRequestSyncEvent, bool, str], None] | None = None,
    ) -> None:
        self._on_start_review = on_start_review
        self._running = False
        self._active_heads: dict[int, str] = {}

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True

    def stop(self) -> str:
        self._running = False
        self._active_heads.clear()
        return TUI_CLOSED_AUTO_REVIEW_MESSAGE

    def handle(self, event: PullRequestSyncEvent) -> AutoReviewOutcome:
        if not self._running:
            return AutoReviewOutcome(
                kind="not_running",
                pull_request_number=event.pull_request_number,
            )

        decision = handle_pull_request_event(_delivery_from_event(event))
        if decision.kind == "ignore":
            return AutoReviewOutcome(
                kind="ignored",
                pull_request_number=event.pull_request_number,
                head_sha=event.head_sha,
            )

        if decision.kind == "cancel":
            self._active_heads.pop(event.pull_request_number, None)
            return AutoReviewOutcome(
                kind="cancelled",
                pull_request_number=event.pull_request_number,
                head_sha=event.head_sha,
            )

        previous_head = self._active_heads.get(event.pull_request_number)
        if previous_head == event.head_sha:
            return AutoReviewOutcome(
                kind="ignored",
                pull_request_number=event.pull_request_number,
                head_sha=event.head_sha,
            )

        superseded = previous_head is not None and previous_head != event.head_sha
        self._active_heads[event.pull_request_number] = event.head_sha
        if self._on_start_review is not None:
            self._on_start_review(event, superseded, previous_head or "")

        return AutoReviewOutcome(
            kind="superseded" if superseded else "started",
            pull_request_number=event.pull_request_number,
            head_sha=event.head_sha,
            previous_head_sha=previous_head or "",
        )


def _delivery_from_event(event: PullRequestSyncEvent) -> GitHubDelivery:
    identity = RepositoryIdentity(
        installation_id=event.installation_id,
        repository_id=event.repository_id,
        owner=event.owner,
        name=event.repository,
    )
    return GitHubDelivery(
        delivery_id=f"tui-auto-review-{event.pull_request_number}",
        event="pull_request",
        action=event.action,
        repository_identity=identity,
        pull_request=PullRequestRef(
            owner=event.owner,
            repository=event.repository,
            number=event.pull_request_number,
        ),
        draft=event.draft,
        base_sha="a" * 40,
        head_sha=event.head_sha,
    )
