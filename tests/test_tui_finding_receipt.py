"""Task (phase 30, reassigned): the TUI shows a receipt beside every finding, verified and
asserted visually distinct. receipt.py:115 is the only source of that distinction.
"""

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


def _finding(*, verified: bool) -> Finding:
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


def test_verified_and_asserted_findings_render_with_distinct_classes() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(())

        verified_finding = _finding(verified=True)
        verified_receipt = _receipt(verified_finding, verified=True)
        asserted_finding = Finding(
            **{**_finding(verified=False).model_dump(), "id": "finding-2"}
        )
        asserted_receipt = _receipt(asserted_finding, verified=False)

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.add_finding(verified_finding, verified_receipt)
            panel.add_finding(asserted_finding, asserted_receipt)
            await pilot.pause()

            verified_row = pilot.app.query_one("#finding-finding-1")
            asserted_row = pilot.app.query_one("#finding-finding-2")

            verified_badge = verified_row.query_one(".finding-badge")
            asserted_badge = asserted_row.query_one(".finding-badge")
            assert "finding-verified" in verified_badge.classes
            assert "finding-asserted" not in verified_badge.classes
            assert "finding-asserted" in asserted_badge.classes
            assert "finding-verified" not in asserted_badge.classes
            assert "VERIFIED" in str(verified_badge.render())
            assert "ASSERTED" in str(asserted_badge.render())

    asyncio.run(exercise())
