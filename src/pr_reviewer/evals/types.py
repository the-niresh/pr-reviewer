"""Eval case, candidate, label, and run config. Candidates are not labels."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pr_reviewer.contracts.finding_candidate import FindingCandidate

EvalSplit = Literal["dev", "holdout"]
Concern = Literal["security", "correctness", "tests", "docs", "maintainability"]
ReviewerCallable = Callable[["EvalCase"], Sequence[FindingCandidate]]


class EvalLabel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concern: Concern
    category: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    line_start: int = Field(gt=0)
    line_end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_line_range(self) -> EvalLabel:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class EvalCandidate(BaseModel):
    """Mined evidence. Not ground truth. Has no expected_labels and is not a label."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_evidence: list[str] = Field(min_length=1)
    diff: str = ""
    committed_at: date | None = None


class SkippedMineCommit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    reason: Literal["diff_exceeds_packed_budget"]
    token_count: int = Field(ge=0)
    token_budget: int = Field(ge=0)


class MineResult(BaseModel):
    """Usable candidates plus commits skipped as too large to review."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: list[EvalCandidate]
    skipped: tuple[SkippedMineCommit, ...] = ()


class EvalCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    split: EvalSplit
    diff: str = Field(min_length=1)
    expected_labels: list[EvalLabel] = Field(min_length=1)
    source_evidence: list[str] = Field(min_length=1)
    human_auditor: str | None
    committed_at: date

    @model_validator(mode="after")
    def holdout_requires_a_human_auditor(self) -> EvalCase:
        if self.split == "holdout" and not self.human_auditor:
            raise ValueError("a holdout case without a human auditor is rejected")
        return self


class EvalConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: list[EvalCase] = Field(min_length=1)
    repeats: int = Field(ge=1)


class EvalMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    precision_per_finding: float = Field(ge=0, le=1)
    precision_per_case: float = Field(ge=0, le=1)
    recall_per_finding: float = Field(ge=0, le=1)
    recall_per_case: float = Field(ge=0, le=1)
    false_findings_per_pr: float = Field(ge=0)
    selectivity: float = Field(ge=0, le=1)
    verified_finding_rate: float = Field(ge=0, le=1)
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    needs_human_rate: float = Field(ge=0, le=1)
    reviewed_pr_count: int = Field(ge=0)
    rule_adherence: dict[str, float]


class EvalRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: EvalMetrics


def assign_time_split(cases: Sequence[EvalCase], *, holdout_after: date) -> list[EvalCase]:
    assigned: list[EvalCase] = []
    for case in cases:
        split: EvalSplit = "holdout" if case.committed_at > holdout_after else "dev"
        assigned.append(case.model_copy(update={"split": split}))
    return assigned
