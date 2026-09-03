"""A yes/no confirmation modal for actions that are not safely undoable from the TUI.

Logging out is the first caller: it revokes the runner hosted-side (control_plane/pairing
never creates a way to un-revoke one), so a single stray keypress or an accidental click on
the footer's own "Log out" hint must not be enough to trigger it on its own.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }

    ConfirmScreen > Vertical {
        width: auto;
        max-width: 60;
        padding: 1 3;
        border: thick $panel;
        background: $surface;
    }

    ConfirmScreen .confirm-message {
        margin-bottom: 1;
    }

    ConfirmScreen Horizontal {
        width: auto;
        align: right middle;
    }

    ConfirmScreen Button {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        message: str,
        *,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
    ) -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self._message, classes="confirm-message"),
            Horizontal(
                Button(self._cancel_label, id="confirm-cancel"),
                Button(self._confirm_label, id="confirm-yes", variant="error"),
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(False)
