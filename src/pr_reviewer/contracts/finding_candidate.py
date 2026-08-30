"""Model-emitted finding shape. System code owns id, verification, and status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Concern = Literal["security", "correctness", "tests", "docs", "maintainability"]
Severity = Literal["critical", "high", "medium", "low", "info"]


class FindingCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concern: Concern
    severity: Severity
    category: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    line_start: int = Field(gt=0)
    line_end: int = Field(gt=0)
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_line_range(self) -> FindingCandidate:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self
