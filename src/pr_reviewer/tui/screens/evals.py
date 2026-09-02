"""Phase 31: the fifth TUI section, evals. Shows the same numbers and the same refusals the
scorecard already emits (evals/scorecard.py, evals/feature_flags.py) -- never a blank, never a
zero standing in for an unmeasured number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

_REPO_ROOT = Path(__file__).resolve().parents[4]
SCORECARD_PATH = _REPO_ROOT / "docs" / "reports" / "scorecard.json"
FEATURE_FLAGS_PATH = _REPO_ROOT / "docs" / "reports" / "feature_flags.json"
REGRESSION_GATE_REFUSAL = (
    "Regression gate: not run. It compares two real eval reports (a baseline and a "
    "candidate); neither exists until the holdout is audited and a run is recorded."
)


class EvalsPanel(Widget):
    """Reads the same generated JSON the public scorecard page reads, so the TUI and the web
    can never quietly disagree with each other.
    """

    def __init__(
        self,
        *,
        scorecard_path: Path = SCORECARD_PATH,
        feature_flags_path: Path = FEATURE_FLAGS_PATH,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._scorecard_path = scorecard_path
        self._feature_flags_path = feature_flags_path

    def compose(self) -> ComposeResult:
        yield Label("Evals", id="evals-heading")
        yield Vertical(id="evals-scorecard")
        yield Vertical(id="evals-flags")
        yield Static(REGRESSION_GATE_REFUSAL, id="evals-regression-gate")

    def on_mount(self) -> None:
        self.refresh_evals()

    def refresh_evals(self) -> None:
        scorecard_container = self.query_one("#evals-scorecard", Vertical)
        scorecard_container.remove_children()
        for key, value in self._read_json(self._scorecard_path).items():
            scorecard_container.mount(Static(f"{key}: {value}", classes="evals-metric"))

        flags_container = self.query_one("#evals-flags", Vertical)
        flags_container.remove_children()
        for flag in self._read_flags():
            state = "on" if flag.get("enabled") else "off"
            flags_container.mount(
                Static(
                    f"{flag.get('name')}: {state} - {flag.get('measurement')}",
                    classes="evals-flag",
                    id=f"evals-flag-{flag.get('name')}",
                )
            )

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def _read_flags(self) -> list[dict[str, Any]]:
        if not self._feature_flags_path.exists():
            return []
        data: list[dict[str, Any]] = json.loads(
            self._feature_flags_path.read_text(encoding="utf-8")
        )
        return data
