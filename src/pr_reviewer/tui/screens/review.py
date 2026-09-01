"""Live review screen: diffs first, then agent reasoning."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from pr_reviewer.contracts.review_context import PackedDiff
from pr_reviewer.local_store.review_log import ReviewLogStore
from pr_reviewer.reviewer.specialists import SPECIALIST_CONCERNS

ReviewPhase = Literal["diffs", "agents"]


@dataclass(frozen=True)
class ReviewDiffItem:
    file_path: str
    content: str


@dataclass(frozen=True)
class AgentReasoningChunk:
    concern: str
    text: str


def diff_items_from_packed(packed: PackedDiff) -> tuple[ReviewDiffItem, ...]:
    return tuple(
        ReviewDiffItem(file_path=item.file_path, content=item.content) for item in packed.items
    )


def default_reasoning_feed() -> tuple[AgentReasoningChunk, ...]:
    return tuple(
        AgentReasoningChunk(concern, f"Reviewing the patch for {concern} issues.")
        for concern in SPECIALIST_CONCERNS
    )


class ReviewPanel(Widget):
    DEFAULT_CSS = """
    ReviewPanel {
        padding: 1 2;
    }

    ReviewPanel .review-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    ReviewPanel .review-diff {
        margin-bottom: 1;
        color: $text;
    }

    ReviewPanel .review-agents {
        margin-top: 1;
        color: $primary;
    }

    ReviewPanel .reasoning-line {
        margin-bottom: 1;
    }
    """

    phase: reactive[ReviewPhase] = reactive("diffs")

    def __init__(
        self,
        diff_items: tuple[ReviewDiffItem, ...] = (),
        *,
        review_log: ReviewLogStore | None = None,
        review_id: str = "live-review",
        reasoning_feed: Iterable[AgentReasoningChunk] | None = None,
        stream_immediately: bool = False,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._diff_items = diff_items
        self._review_log = review_log
        self._review_id = review_id
        self._reasoning_feed = tuple(reasoning_feed or default_reasoning_feed())
        self._stream_immediately = stream_immediately
        self._pending_chunks: list[AgentReasoningChunk] = []
        self._streamed_concerns: list[str] = []
        self._reasoning_timer: Any = None

    def compose(self) -> ComposeResult:
        diff_rows: list[Widget] = [
            Label("Review", classes="review-heading", id="review-heading"),
            Label("Changed files", id="review-diffs-heading"),
        ]
        for index, item in enumerate(self._diff_items):
            diff_rows.append(
                Static(
                    f"{item.file_path}\n{item.content}",
                    classes="review-diff",
                    id=f"review-diff-{index}",
                )
            )
        diff_rows.append(
            Button("Continue to agents", id="review-continue", variant="primary")
        )
        yield Vertical(*diff_rows, id="review-diffs-panel")
        yield Vertical(
            Label("Agent reasoning", id="review-agents-heading"),
            Vertical(id="review-reasoning-stream"),
            classes="review-agents",
            id="review-agents",
        )

    def on_mount(self) -> None:
        self._sync_phase_visibility()

    def watch_phase(self, _phase: ReviewPhase) -> None:
        self._sync_phase_visibility()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "review-continue":
            self.start_agent_reasoning()

    def start_agent_reasoning(
        self,
        chunks: Iterable[AgentReasoningChunk] | None = None,
    ) -> None:
        self.phase = "agents"
        self._pending_chunks = list(chunks or self._reasoning_feed)
        if self._stream_immediately:
            self._flush_pending_reasoning()
            return
        self._reasoning_timer = self.set_interval(0.05, self._deliver_next_reasoning_chunk)

    def _flush_pending_reasoning(self) -> None:
        while self._pending_chunks:
            self._deliver_next_reasoning_chunk()

    def _deliver_next_reasoning_chunk(self) -> None:
        if not self._pending_chunks:
            self._stop_reasoning_stream()
            return
        chunk = self._pending_chunks.pop(0)
        self._streamed_concerns.append(chunk.concern)
        stream = self.query_one("#review-reasoning-stream", Vertical)
        stream.mount(
            Static(
                f"{chunk.concern}: {chunk.text}",
                classes="reasoning-line",
                id=f"reasoning-{chunk.concern}-{len(self._streamed_concerns)}",
            )
        )
        if self._review_log is not None:
            self._review_log.append_reasoning(
                self._review_id,
                chunk.concern,
                chunk.text,
            )

    def _stop_reasoning_stream(self) -> None:
        if self._reasoning_timer is not None:
            self._reasoning_timer.stop()
            self._reasoning_timer = None

    def _sync_phase_visibility(self) -> None:
        showing_diffs = self.phase == "diffs"
        self.query_one("#review-diffs-panel").display = True
        self.query_one("#review-continue", Button).display = showing_diffs
        self.query_one("#review-agents").display = not showing_diffs

    @property
    def agents_visible(self) -> bool:
        return self.phase == "agents"

    @property
    def streamed_concerns(self) -> tuple[str, ...]:
        return tuple(self._streamed_concerns)
