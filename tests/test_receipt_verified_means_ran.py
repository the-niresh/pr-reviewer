from __future__ import annotations

import pytest
from pydantic import ValidationError

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.events.record_model_call import ModelCallInput
from pr_reviewer.reviewer.receipt import (
    AssertedVerification,
    FindingReceipt,
    ReceiptContextSource,
    SandboxVerification,
    build_finding_receipt,
)


def _finding(
    *,
    verified: bool = True,
    verification_method: str = "sandbox",
) -> Finding:
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
        confidence=0.82,
        verified=verified,
        verification_method=verification_method,  # type: ignore[arg-type]
        public_safe=False,
        status="queued_for_human",
    )


def _model_call() -> ModelCallInput:
    return ModelCallInput(
        review_job_id="job-1",
        provider="openai",
        model="gpt-5-mini",
        prompt_version_id="prompt-version-1",
        input_tokens=100,
        output_tokens=25,
        cost_usd="0.000123",
        latency_ms=42,
    )


def _sources() -> tuple[ReceiptContextSource, ...]:
    return (
        ReceiptContextSource(kind="diff", name="packed diff", reference="diff:app.py"),
    )


def test_verified_receipt_requires_a_sandbox_method_and_citation() -> None:
    receipt = build_finding_receipt(
        finding=_finding(),
        model_call=_model_call(),
        context_sources=_sources(),
        verification=SandboxVerification(
            sandbox_run_id="sandbox-run-1",
            command_id="pytest",
            detail="sandbox command exited 0",
        ),
    )

    assert receipt.model_dump(mode="json")["verified"] is True
    assert receipt.verification.status == "verified"


def test_verified_static_finding_is_refused_even_with_a_citation() -> None:
    with pytest.raises(ValueError, match="verified findings must come from a sandbox run"):
        build_finding_receipt(
            finding=_finding(verification_method="static"),
            model_call=_model_call(),
            context_sources=_sources(),
            verification=SandboxVerification(
                sandbox_run_id="sandbox-run-1",
                command_id="pytest",
                detail="static checks passed",
            ),
        )


def test_verified_finding_without_a_sandbox_citation_is_refused() -> None:
    with pytest.raises(ValueError, match="verified findings must cite a sandbox run"):
        build_finding_receipt(
            finding=_finding(),
            model_call=_model_call(),
            context_sources=_sources(),
            verification=AssertedVerification(reason="model said it was certain"),
        )


def test_model_payload_cannot_set_receipt_verified() -> None:
    with pytest.raises(ValidationError):
        FindingReceipt.model_validate(
            {
                "finding_id": "finding-1",
                "review_job_id": "job-1",
                "prompt_version_id": "prompt-version-1",
                "model_call": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "prompt_version_id": "prompt-version-1",
                    "tokens": {"input_tokens": 100, "output_tokens": 25},
                    "cost_usd": "0.000123",
                },
                "context_sources": [
                    {
                        "kind": "diff",
                        "name": "packed diff",
                        "reference": "diff:app.py",
                    }
                ],
                "verification": {
                    "status": "asserted",
                    "reason": "model said it was certain",
                },
                "verified": True,
            }
        )
