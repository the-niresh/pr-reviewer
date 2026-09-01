"""Task 31.2: the feature-flag table refuses to invent a measurement (real refusals only)."""

from __future__ import annotations

from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.evals.feature_flags import generate_feature_flags
from pr_reviewer.evals.run_eval import (
    BaselineBlocked,
    load_public_eval_cases,
    run_context_source_comparison,
    run_retrieval_comparison,
    run_specialist_comparison,
)
from pr_reviewer.evals.types import EvalCase


def _empty_reviewer(_case: EvalCase) -> list[FindingCandidate]:
    return []


def test_every_flag_is_off_until_a_real_switch_turns_it_on() -> None:
    flags = generate_feature_flags()
    by_name = {flag.name: flag for flag in flags}
    assert set(by_name) == {"retrieval", "code_graph", "specialists", "langgraph"}
    assert by_name["retrieval"].enabled is False
    assert by_name["code_graph"].enabled is False
    assert by_name["specialists"].enabled is False
    assert by_name["langgraph"].enabled is False


def test_each_measurement_is_the_real_verbatim_refusal_for_that_comparison() -> None:
    cases = load_public_eval_cases()
    flags = generate_feature_flags()
    by_name = {flag.name: flag for flag in flags}

    try:
        run_retrieval_comparison(cases, _empty_reviewer, _empty_reviewer)
        raise AssertionError("the real public dataset must have zero holdout cases right now")
    except BaselineBlocked as exc:
        assert by_name["retrieval"].measurement == str(exc)

    try:
        run_context_source_comparison(cases, _empty_reviewer, _empty_reviewer, _empty_reviewer)
        raise AssertionError("the real public dataset must have zero holdout cases right now")
    except BaselineBlocked as exc:
        assert by_name["code_graph"].measurement == str(exc)

    try:
        run_specialist_comparison(cases, _empty_reviewer, _empty_reviewer)
        raise AssertionError("the real public dataset must have zero holdout cases right now")
    except BaselineBlocked as exc:
        assert by_name["specialists"].measurement == str(exc)

    for flag in flags:
        assert "holdout is empty" in flag.measurement
