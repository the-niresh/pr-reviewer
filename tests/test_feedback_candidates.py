"""Failing tests for feedback-to-eval promotion (master Task 20).

One dispute must not change prompts, policy, labels, or routing. A candidate
needs repeated evidence and a human audit. Imports of new modules stay inside
test bodies.
"""

from __future__ import annotations

from pathlib import Path

from pr_reviewer.security.instruction_sources import default_review_policy

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_one_dispute_does_not_change_prompts_policy_labels_or_routing() -> None:
    from pr_reviewer.evals.feedback_candidates import FeedbackEvent, consider_feedback

    prompts = {"diff_only_reviewer": "1"}
    policy = default_review_policy()
    labels = ["null-check"]
    routing = "queue_for_human"
    result = consider_feedback(
        [
            FeedbackEvent(
                finding_fingerprint="fp-1",
                action="disputed",
                actor="reviewer-1",
                human_audited=False,
            )
        ],
        prompts=prompts,
        policy=policy,
        labels=labels,
        routing=routing,
    )
    assert prompts == {"diff_only_reviewer": "1"}
    assert policy == default_review_policy()
    assert labels == ["null-check"]
    assert routing == "queue_for_human"
    assert result.candidates == ()
    assert result.prompt_rewrites == ()
    assert result.policy_changes == ()
    assert result.label_changes == ()
    assert result.routing_changes == ()


def test_repeated_disputes_without_human_audit_are_not_candidates() -> None:
    from pr_reviewer.evals.feedback_candidates import FeedbackEvent, consider_feedback

    events = [
        FeedbackEvent(
            finding_fingerprint="fp-1",
            action="disputed",
            actor=f"reviewer-{index}",
            human_audited=False,
        )
        for index in range(3)
    ]
    result = consider_feedback(
        events,
        prompts={"diff_only_reviewer": "1"},
        policy=default_review_policy(),
        labels=["null-check"],
        routing="queue_for_human",
    )
    assert result.candidates == ()


def test_repeated_evidence_plus_human_audit_becomes_an_eval_candidate() -> None:
    from pr_reviewer.evals.feedback_candidates import FeedbackEvent, consider_feedback

    events = [
        FeedbackEvent(
            finding_fingerprint="fp-1",
            action="disputed",
            actor=f"reviewer-{index}",
            human_audited=index == 2,
        )
        for index in range(3)
    ]
    result = consider_feedback(
        events,
        prompts={"diff_only_reviewer": "1"},
        policy=default_review_policy(),
        labels=["null-check"],
        routing="queue_for_human",
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].finding_fingerprint == "fp-1"
    assert result.candidates[0].human_audited is True
    assert result.prompt_rewrites == ()
    assert result.policy_changes == ()
    assert result.label_changes == ()
    assert result.routing_changes == ()


def test_evals_doc_lists_commands_and_does_not_invent_numbers() -> None:
    text = (DOCS / "EVALS.md").read_text(encoding="utf-8")
    assert "run_diff_only_baseline" in text
    assert "write_eval_report" in text
    assert "BaselineBlocked" in text
    assert "holdout" in text.lower()
    for token in ("precision=", "0.87", "p99"):
        assert token not in text
