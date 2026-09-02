"""Phase 29: copy the remediation prompt from the TUI."""

from __future__ import annotations

import asyncio

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.reviewer.receipt import (
    AssertedVerification,
    FindingReceipt,
    ReceiptContextSource,
    ReceiptModelCall,
    ReceiptTokens,
)
from pr_reviewer.reviewer.remediation import remediation_prompt_for_finding
from pr_reviewer.tui.screens.review import ReviewPanel


def _finding() -> Finding:
    return Finding(
        id="finding-1",
        review_job_id="job-1",
        concern="correctness",
        severity="high",
        category="null-check",
        file_path="app.py",
        line_start=12,
        line_end=12,
        title="Missing null check",
        rationale="value can be None before it is used.",
        evidence=["app.py:12"],
        confidence=0.8,
        verified=False,
        verification_method="not_applicable",
        public_safe=True,
        status="posted",
    )


def _receipt(finding: Finding) -> FindingReceipt:
    return FindingReceipt(
        finding_id=finding.id,
        review_job_id=finding.review_job_id,
        prompt_version_id="prompt-1",
        model_call=ReceiptModelCall(
            provider="openai",
            model="gpt-5-mini",
            prompt_version_id="prompt-1",
            tokens=ReceiptTokens(input_tokens=10, output_tokens=5),
            cost_usd="0.001",
        ),
        context_sources=(ReceiptContextSource(kind="diff", name="pr-diff", reference="hunk-1"),),
        verification=AssertedVerification(reason="No sandbox available for this check."),
    )


def test_copy_remediation_button_copies_the_real_prompt_to_the_clipboard() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Button

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(())

        finding = _finding()
        receipt = _receipt(finding)
        remediation = remediation_prompt_for_finding(finding)

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.add_finding(finding, receipt, remediation)
            await pilot.pause()

            button = pilot.app.query_one(f"#copy-remediation-{finding.id}", Button)
            copied: list[str] = []
            pilot.app.copy_to_clipboard = copied.append  # type: ignore[assignment]
            panel.on_button_pressed(Button.Pressed(button))

            assert copied == [remediation.prompt]
            assert "Missing null check" in remediation.prompt

    asyncio.run(exercise())


def test_finding_without_a_remediation_prompt_has_no_copy_button() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(())

        finding = _finding()
        receipt = _receipt(finding)

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.add_finding(finding, receipt)
            await pilot.pause()

            row = pilot.app.query_one(f"#finding-{finding.id}")
            assert list(row.query(".finding-remediation-button")) == []

    asyncio.run(exercise())
