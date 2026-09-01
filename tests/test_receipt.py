from __future__ import annotations

import pytest
from pydantic import ValidationError

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.events.record_model_call import ModelCallInput
from pr_reviewer.reviewer.receipt import (
    AssertedVerification,
    ReceiptContextSource,
    SandboxVerification,
    build_finding_receipt,
)


def _finding(*, verified: bool = False) -> Finding:
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
        verification_method="sandbox" if verified else "failed",
        public_safe=False,
        status="queued_for_human",
    )


def _model_call(**overrides: object) -> ModelCallInput:
    values = {
        "review_job_id": "job-1",
        "provider": "openai",
        "model": "gpt-5-mini",
        "prompt_version_id": "prompt-version-1",
        "input_tokens": 100,
        "output_tokens": 25,
        "cost_usd": "0.000123",
        "latency_ms": 42,
    }
    values.update(overrides)
    return ModelCallInput(**values)  # type: ignore[arg-type]


def _sources() -> tuple[ReceiptContextSource, ...]:
    return (
        ReceiptContextSource(kind="diff", name="packed diff", reference="diff:app.py"),
        ReceiptContextSource(kind="retrieval", name="hybrid search", reference="chunk:abc"),
        ReceiptContextSource(kind="profile", name="repository profile", reference="profile:42"),
        ReceiptContextSource(kind="graph", name="code graph", reference="graph:snapshot-1"),
    )


def test_receipt_joins_prompt_model_tokens_cost_sources_and_assertion_status() -> None:
    receipt = build_finding_receipt(
        finding=_finding(),
        model_call=_model_call(),
        context_sources=_sources(),
        verification=AssertedVerification(reason="no sandbox run was cited"),
    )

    assert receipt.finding_id == "finding-1"
    assert receipt.review_job_id == "job-1"
    assert receipt.prompt_version_id == "prompt-version-1"
    assert receipt.model_call.provider == "openai"
    assert receipt.model_call.model == "gpt-5-mini"
    assert receipt.model_call.tokens.input_tokens == 100
    assert receipt.model_call.tokens.output_tokens == 25
    assert receipt.model_call.cost_usd == "0.000123"
    assert [source.kind for source in receipt.context_sources] == [
        "diff",
        "retrieval",
        "profile",
        "graph",
    ]
    dumped = receipt.model_dump(mode="json")
    assert dumped["model_call"]["tokens"]["total_tokens"] == 125
    assert dumped["verified"] is False


def test_verified_receipt_requires_a_cited_sandbox_run() -> None:
    receipt = build_finding_receipt(
        finding=_finding(verified=True),
        model_call=_model_call(),
        context_sources=_sources(),
        verification=SandboxVerification(
            sandbox_run_id="sandbox-run-1",
            command_id="pytest",
            detail="sandbox command exited 0",
        ),
    )

    dumped = receipt.model_dump(mode="json")
    assert dumped["verified"] is True
    assert dumped["verification"] == {
        "status": "verified",
        "sandbox_run_id": "sandbox-run-1",
        "command_id": "pytest",
        "detail": "sandbox command exited 0",
    }


def test_verified_finding_without_sandbox_citation_is_refused() -> None:
    with pytest.raises(ValueError, match="verified findings must cite a sandbox run"):
        build_finding_receipt(
            finding=_finding(verified=True),
            model_call=_model_call(),
            context_sources=_sources(),
            verification=AssertedVerification(reason="model said it was certain"),
        )


def test_model_payload_cannot_set_verified_on_a_receipt() -> None:
    with pytest.raises(ValidationError):
        AssertedVerification.model_validate(
            {
                "status": "asserted",
                "reason": "model said it was certain",
                "verified": True,
            }
        )


def test_receipt_refuses_mismatched_finding_and_model_call_jobs() -> None:
    with pytest.raises(ValueError, match="same review job"):
        build_finding_receipt(
            finding=_finding(),
            model_call=_model_call(review_job_id="job-2"),
            context_sources=_sources(),
            verification=AssertedVerification(reason="no sandbox run was cited"),
        )
