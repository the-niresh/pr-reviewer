"""A depleted provider balance ends a review without losing earlier findings."""

from __future__ import annotations


def test_out_of_tokens_is_a_typed_terminal_state_with_preserved_findings() -> None:
    from pr_reviewer.contracts.finding_candidate import FindingCandidate
    from pr_reviewer.models.provider_errors import OutOfTokensState, stopped_early_review

    finding = FindingCandidate.model_validate(
        {
            "concern": "correctness",
            "severity": "high",
            "category": "logic",
            "file_path": "app.py",
            "line_start": 4,
            "line_end": 4,
            "title": "Missing check",
            "rationale": "the value can be absent",
            "evidence": ["app.py:4"],
            "confidence": 0.9,
        }
    )

    state = stopped_early_review(
        findings=(finding,),
        provider="anthropic",
        reason="tier spend cap reached",
    )

    assert isinstance(state.stop, OutOfTokensState)
    assert not isinstance(state.stop, Exception)
    assert state.stop.provider == "anthropic"
    assert state.stop.reason == "tier spend cap reached"
    assert state.findings == (finding,)
    assert state.summary_fields() == {"status": "stopped_early", "stopped_early": True}
