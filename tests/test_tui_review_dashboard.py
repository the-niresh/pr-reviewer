"""Findings appear in the reviews dashboard as they land."""

from __future__ import annotations

import asyncio

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.reviewer.receipt import (
    AssertedVerification,
    FindingReceipt,
    ReceiptContextSource,
    ReceiptModelCall,
    ReceiptTokens,
    SandboxVerification,
)
from pr_reviewer.tui.screens.review import ReviewPanel


def _finding(*, finding_id: str, verified: bool) -> Finding:
    return Finding(
        id=finding_id,
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
        verified=verified,
        verification_method="sandbox" if verified else "not_applicable",
        public_safe=True,
        status="posted",
    )


def _receipt(finding: Finding, *, verified: bool) -> FindingReceipt:
    model_call = ReceiptModelCall(
        provider="openai",
        model="gpt-5-mini",
        prompt_version_id="prompt-1",
        tokens=ReceiptTokens(input_tokens=10, output_tokens=5),
        cost_usd="0.001",
    )
    verification = (
        SandboxVerification(sandbox_run_id="run-1", command_id="cmd-1", detail="checks passed")
        if verified
        else AssertedVerification(reason="No sandbox available for this check.")
    )
    return FindingReceipt(
        finding_id=finding.id,
        review_job_id=finding.review_job_id,
        prompt_version_id="prompt-1",
        model_call=model_call,
        context_sources=(ReceiptContextSource(kind="diff", name="pr-diff", reference="hunk-1"),),
        verification=verification,
    )


def test_findings_appear_as_they_land() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(())

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            first = _finding(finding_id="finding-1", verified=True)
            panel.add_finding(first, _receipt(first, verified=True))
            assert pilot.app.query("#finding-finding-1")
            assert not pilot.app.query("#finding-finding-2")
            second = _finding(finding_id="finding-2", verified=False)
            panel.add_finding(second, _receipt(second, verified=False))
            await pilot.pause()
            assert pilot.app.query_one("#finding-finding-2")

    asyncio.run(exercise())
