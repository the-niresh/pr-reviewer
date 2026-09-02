"""Phase 30: the web dashboard and the TUI must show the same receipt for the same finding.

One FindingReceipt goes through both surfaces. If either surface drops a field -- prompt
version, model, tokens, cost, a context source, or the verified/asserted state -- this fails.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
from pr_reviewer.control_plane.review_projection import (
    ReceiptContextSourceInput,
    ReceiptInput,
    project_review,
    reviews_for_repository,
)
from pr_reviewer.db.client import connection
from pr_reviewer.reviewer.receipt import (
    FindingReceipt,
    ReceiptContextSource,
    ReceiptModelCall,
    ReceiptTokens,
    SandboxVerification,
)
from pr_reviewer.tui.screens.review import ReviewPanel

PROVIDER: Literal["openai"] = "openai"
MODEL = "gpt-5-mini"
INPUT_TOKENS = 120
OUTPUT_TOKENS = 40
TOTAL_TOKENS = INPUT_TOKENS + OUTPUT_TOKENS
COST_USD = "0.02"
CONTEXT_KIND: Literal["retrieval"] = "retrieval"
CONTEXT_NAME = "hybrid-index"
CONTEXT_REFERENCE = "chunk-42"


def _random_id() -> int:
    import random

    return random.randint(10_000_000, 2_000_000_000)


def _create_installation() -> int:
    installation_id = _random_id()
    with connection() as conn:
        conn.execute(
            "insert into installations (id, account_login) values (%s, 'octocat')",
            (installation_id,),
        )
    return installation_id


def _create_review_job_for_repo(installation_id: int, github_repository_id: int) -> str:
    with connection() as conn:
        delivery_id = f"delivery-{uuid.uuid4()}"
        conn.execute(
            "insert into github_deliveries (id, event_name) values (%s, 'pull_request')",
            (delivery_id,),
        )
        row = conn.execute(
            """
            insert into review_jobs (
              delivery_id, status, installation_id, github_repository_id,
              pull_request_number, head_sha
            )
            values (%s, 'succeeded', %s, %s, 1, 'deadbeef')
            returning id
            """,
            (delivery_id, installation_id, github_repository_id),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def _create_prompt_version() -> str:
    with connection() as conn:
        row = conn.execute(
            "insert into prompt_versions (name, version, content) values "
            "('reviewer', %s, 'content') returning id",
            (str(uuid.uuid4()),),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def _create_model_call(review_job_id: str, prompt_version_id: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            insert into model_calls (review_job_id, prompt_version_id, provider, model_name,
                                      input_tokens, output_tokens, cost_usd)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                review_job_id,
                prompt_version_id,
                PROVIDER,
                MODEL,
                INPUT_TOKENS,
                OUTPUT_TOKENS,
                COST_USD,
            ),
        )


def _finding(review_job_id: str) -> Finding:
    return Finding(
        id=f"finding-{uuid.uuid4()}",
        review_job_id=review_job_id,
        concern="security",
        severity="critical",
        category="injection",
        file_path="app.py",
        line_start=5,
        line_end=5,
        title="Unsanitized shell call",
        rationale="user input reaches subprocess.run with shell=True.",
        evidence=["app.py:5"],
        confidence=0.95,
        verified=True,
        verification_method="sandbox",
        public_safe=True,
        status="posted",
    )


def _receipt(finding: Finding, prompt_version_id: str) -> FindingReceipt:
    return FindingReceipt(
        finding_id=finding.id,
        review_job_id=finding.review_job_id,
        prompt_version_id=prompt_version_id,
        model_call=ReceiptModelCall(
            provider=PROVIDER,
            model=MODEL,
            prompt_version_id=prompt_version_id,
            tokens=ReceiptTokens(input_tokens=INPUT_TOKENS, output_tokens=OUTPUT_TOKENS),
            cost_usd=COST_USD,
        ),
        context_sources=(
            ReceiptContextSource(kind=CONTEXT_KIND, name=CONTEXT_NAME, reference=CONTEXT_REFERENCE),
        ),
        verification=SandboxVerification(
            sandbox_run_id="run-1", command_id="cmd-1", detail="sandbox command exited 0"
        ),
    )


def test_web_and_tui_show_the_same_receipt_fields() -> None:
    installation_id = _create_installation()
    github_repository_id = _random_id()
    review_job_id = _create_review_job_for_repo(installation_id, github_repository_id)
    prompt_version_id = _create_prompt_version()
    _create_model_call(review_job_id, prompt_version_id)
    finding = _finding(review_job_id)
    receipt = _receipt(finding, prompt_version_id)

    # Web surface: the same FindingReceipt, converted to control_plane's own input shape.
    web_receipt_input = ReceiptInput(
        finding_id=finding.id,
        review_job_id=review_job_id,
        prompt_version_id=prompt_version_id,
        context_sources=(
            ReceiptContextSourceInput(
                kind=CONTEXT_KIND, name=CONTEXT_NAME, reference=CONTEXT_REFERENCE
            ),
        ),
        verified=True,
        sandbox_run_id="run-1",
        command_id="cmd-1",
        verification_detail="sandbox command exited 0",
    )
    project_review(review_job_id, [finding], receipts=[web_receipt_input])
    assertion = LiveInstallationAssertion(
        github_user_id=1,
        installations={installation_id: {github_repository_id: "octocat/widget"}},
        expires_at=2_000_000_000,
    )
    reviews = reviews_for_repository(assertion, installation_id, github_repository_id)
    assert reviews is not None
    web_receipt = reviews[0].findings[0].receipt
    assert web_receipt is not None

    # TUI surface: the exact same FindingReceipt object, rendered by ReviewPanel.
    async def render_tui() -> str:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(())

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.add_finding(finding, receipt)
            await pilot.pause()
            row = pilot.app.query_one(f"#finding-{finding.id}")
            return " ".join(str(child.render()) for child in row.query("*"))

    tui_text = asyncio.run(render_tui())

    # Prompt version, model, tokens, cost, context source, and verified state must appear on
    # both surfaces -- neither may silently drop a field.
    assert web_receipt.prompt_version_id == prompt_version_id
    assert prompt_version_id in tui_text or prompt_version_id[:8] in tui_text

    assert web_receipt.provider == PROVIDER
    assert web_receipt.model == MODEL
    assert f"{PROVIDER}/{MODEL}" in tui_text

    assert web_receipt.input_tokens == INPUT_TOKENS
    assert web_receipt.output_tokens == OUTPUT_TOKENS
    assert str(TOTAL_TOKENS) in tui_text

    assert web_receipt.cost_usd is not None
    assert float(web_receipt.cost_usd) == float(COST_USD)
    assert COST_USD in tui_text

    assert len(web_receipt.context_sources) == 1
    assert web_receipt.context_sources[0].kind == CONTEXT_KIND
    assert web_receipt.context_sources[0].name == CONTEXT_NAME
    assert f"{CONTEXT_KIND}:{CONTEXT_NAME}" in tui_text

    assert web_receipt.verification_status == "verified"
    assert "VERIFIED" in tui_text
