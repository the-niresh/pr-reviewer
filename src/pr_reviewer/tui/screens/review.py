"""Live review screen: diffs first, then agent reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from pr_reviewer.contracts.review_context import PackedDiff

ReviewPhase = Literal["diffs", "agents"]


@dataclass(frozen=True)
class ReviewDiffItem:
    file_path: str
    content: str


def diff_items_from_packed(packed: PackedDiff) -> tuple[ReviewDiffItem, ...]:
    return tuple(
        ReviewDiffItem(file_path=item.file_path, content=item.content) for item in packed.items
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
    """

    phase: reactive[ReviewPhase] = reactive("diffs")

    def __init__(
        self,
        diff_items: tuple[ReviewDiffItem, ...] = (),
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._diff_items = diff_items

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
            Static("Waiting for agents to speak.", id="review-agents-placeholder"),
            classes="review-agents",
            id="review-agents",
        )

    def on_mount(self) -> None:
        self._sync_phase_visibility()

    def watch_phase(self, _phase: ReviewPhase) -> None:
        self._sync_phase_visibility()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "review-continue":
            self.phase = "agents"

    def _sync_phase_visibility(self) -> None:
        showing_diffs = self.phase == "diffs"
        self.query_one("#review-diffs-panel").display = True
        self.query_one("#review-continue", Button).display = showing_diffs
        self.query_one("#review-agents").display = not showing_diffs

    @property
    def agents_visible(self) -> bool:
        return self.phase == "agents"
