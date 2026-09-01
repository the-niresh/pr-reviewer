"""Phase 31: the scorecard generator.

Every number here comes from a real eval run against the frozen holdout, produced by
run_diff_only_baseline. When the holdout is empty, generate_scorecard does not compute
anything and does not invent a number: every field becomes the verbatim BaselineBlocked
message, the same string that run_diff_only_baseline itself raises. There is no
hand-typed scorecard and no placeholder path.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from pr_reviewer.evals.run_eval import (
    BaselineBlocked,
    load_public_eval_cases,
    run_diff_only_baseline,
)
from pr_reviewer.evals.types import EvalCase, ReviewerCallable


class Scorecard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    precision_per_finding: float | str
    precision_per_case: float | str
    recall_per_finding: float | str
    recall_per_case: float | str
    false_findings_per_pr: float | str
    cost_usd: float | str
    reviewed_pr_count: int | str


def generate_scorecard(
    reviewer: ReviewerCallable,
    *,
    cases: Sequence[EvalCase] | None = None,
    repeats: int = 3,
) -> Scorecard:
    source_cases = list(cases) if cases is not None else load_public_eval_cases()
    try:
        run = run_diff_only_baseline(source_cases, reviewer, repeats=repeats)
    except BaselineBlocked as exc:
        refusal = str(exc)
        return Scorecard(
            precision_per_finding=refusal,
            precision_per_case=refusal,
            recall_per_finding=refusal,
            recall_per_case=refusal,
            false_findings_per_pr=refusal,
            cost_usd=refusal,
            reviewed_pr_count=refusal,
        )

    metrics = run.metrics
    return Scorecard(
        precision_per_finding=metrics.precision_per_finding,
        precision_per_case=metrics.precision_per_case,
        recall_per_finding=metrics.recall_per_finding,
        recall_per_case=metrics.recall_per_case,
        false_findings_per_pr=metrics.false_findings_per_pr,
        cost_usd=metrics.cost_usd,
        reviewed_pr_count=metrics.reviewed_pr_count,
    )
