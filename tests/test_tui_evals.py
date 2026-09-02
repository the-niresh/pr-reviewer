"""Phase 31: the fifth TUI section shows the same numbers and refusals as the scorecard."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pr_reviewer.tui.screens.evals import REGRESSION_GATE_REFUSAL, EvalsPanel


def test_evals_panel_shows_the_real_scorecard_refusal(tmp_path: Path) -> None:
    scorecard_path = tmp_path / "scorecard.json"
    scorecard_path.write_text(
        json.dumps({"precision_per_finding": "holdout is empty; refusing to report a baseline"}),
        encoding="utf-8",
    )
    flags_path = tmp_path / "feature_flags.json"
    flags_path.write_text(
        json.dumps(
            [{"name": "specialists", "enabled": False, "measurement": "holdout is empty"}]
        ),
        encoding="utf-8",
    )

    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield EvalsPanel(scorecard_path=scorecard_path, feature_flags_path=flags_path)

        async with Harness().run_test() as pilot:
            await pilot.pause()
            scorecard = pilot.app.query_one("#evals-scorecard")
            text = " ".join(str(child.render()) for child in scorecard.query("*"))
            assert "holdout is empty; refusing to report a baseline" in text
            assert "0.0" not in text

            flag_row = pilot.app.query_one("#evals-flag-specialists")
            flag_text = str(flag_row.render())
            assert "off" in flag_text
            assert "holdout is empty" in flag_text

            gate = pilot.app.query_one("#evals-regression-gate")
            assert REGRESSION_GATE_REFUSAL in str(gate.render())

    asyncio.run(exercise())


def test_evals_panel_never_shows_a_zero_when_files_are_missing(tmp_path: Path) -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield EvalsPanel(
                    scorecard_path=tmp_path / "missing_scorecard.json",
                    feature_flags_path=tmp_path / "missing_flags.json",
                )

        async with Harness().run_test() as pilot:
            await pilot.pause()
            scorecard = pilot.app.query_one("#evals-scorecard")
            assert list(scorecard.query("*")) == []

    asyncio.run(exercise())
