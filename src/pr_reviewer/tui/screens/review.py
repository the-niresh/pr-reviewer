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

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.contracts.review_context import PackedDiff
from pr_reviewer.local_store.budget import BudgetStatus
from pr_reviewer.local_store.review_log import ReviewLogStore
from pr_reviewer.reviewer.receipt import FindingReceipt, SandboxVerification
from pr_reviewer.reviewer.specialists import SPECIALIST_CONCERNS
from pr_reviewer.tui.widgets.cost_meter import CostMeter

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

    ReviewPanel .finding-row {
        margin-bottom: 1;
        border-left: thick $panel;
        padding: 0 1;
    }

    ReviewPanel .finding-badge {
        text-style: bold;
    }

    ReviewPanel .finding-badge.finding-verified {
        color: $success;
    }

    ReviewPanel .finding-badge.finding-asserted {
        color: $warning;
    }

    ReviewPanel .finding-detail {
        color: $text-muted;
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
            CostMeter(id="review-budget-meter"),
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
            Label("What this review could not determine", id="review-undetermined-heading"),
            Vertical(id="review-undetermined-panel"),
            classes="review-undetermined",
            id="review-undetermined",
        )
        yield Vertical(
            Label("Agent reasoning", id="review-agents-heading"),
            Vertical(id="review-reasoning-stream"),
            Label("Findings", id="review-findings-heading"),
            Vertical(id="review-findings-stream"),
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

    def set_undetermined(self, packed: PackedDiff) -> None:
        """A first-class panel for what the review could not determine, not a footnote:
        every omitted file with its real reason (diff_budget.py), shown even when the answer
        is "nothing was omitted" rather than leaving the panel silently empty.
        """
        container = self.query_one("#review-undetermined-panel", Vertical)
        container.remove_children()
        if not packed.omitted_files:
            container.mount(Static("Full coverage: every changed file was reviewed."))
            return
        for item in packed.omitted_files:
            container.mount(
                Static(
                    f"{item.path} ({item.change_size} bytes) - omitted: {item.reason}",
                    classes="undetermined-item",
                    id=f"undetermined-{item.path.replace('/', '-').replace('.', '_')}",
                )
            )

    def set_budget_status(self, status: BudgetStatus | None) -> None:
        self.query_one("#review-budget-meter", CostMeter).update_status(status)

    def add_finding(self, finding: Finding, receipt: FindingReceipt) -> None:
        """Render a finding beside its receipt. receipt.verified (receipt.py:115) is the only
        source of the verified/asserted split: a finding is never styled verified because a
        sandbox run was not actually cited.
        """
        is_verified = isinstance(receipt.verification, SandboxVerification)
        status_class = "finding-verified" if is_verified else "finding-asserted"
        if isinstance(receipt.verification, SandboxVerification):
            detail = receipt.verification.detail
        else:
            detail = receipt.verification.reason
        container = self.query_one("#review-findings-stream", Vertical)
        location = f"{finding.file_path}:{finding.line_start}"
        model_call = receipt.model_call
        sources = ", ".join(f"{source.kind}:{source.name}" for source in receipt.context_sources)
        meta = (
            f"{model_call.provider}/{model_call.model} (prompt {receipt.prompt_version_id}, "
            f"{model_call.tokens.total_tokens} tokens, ${model_call.cost_usd}) - {sources}"
        )
        container.mount(
            Vertical(
                Label(
                    f"{receipt.verification.status.upper()} - {finding.title}",
                    classes=f"finding-badge {status_class}",
                ),
                Static(f"{location} - {detail}", classes="finding-detail"),
                Static(meta, classes="finding-meta"),
                classes="finding-row",
                id=f"finding-{finding.id}",
            )
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
