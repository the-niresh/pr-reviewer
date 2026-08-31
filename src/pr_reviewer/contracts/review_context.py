"""Packed review context. OmissionReason lives in contracts.github and is not redefined here."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.contracts.github import OmissionReason

PACKING_STRATEGY_VERSION = "v1-sensitivity-desc-change-size-desc-path-asc"


class ContextBudget(BaseModel):
    """Tokens the packer may spend. Output allowance has already been subtracted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tokens: int = Field(ge=0)

    @classmethod
    def from_window(cls, context_window: int, output_allowance: int) -> Self:
        if context_window < 0 or output_allowance < 0:
            raise ValueError("context_window and output_allowance must be >= 0")
        remaining = context_window - output_allowance
        return cls(tokens=max(remaining, 0))


class FilePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    patch: str
    previous_path: str | None = None


class ReviewContextItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_kind: Literal["diff_file"]
    file_path: str = Field(min_length=1)
    line_start: int = Field(ge=0)
    line_end: int = Field(ge=0)
    content: str
    content_hash: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_line_range(self) -> ReviewContextItem:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class OmittedFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    reason: OmissionReason
    change_size: int = Field(ge=0)


class PackedDiff(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    packing_strategy_version: str = Field(min_length=1)
    items: tuple[ReviewContextItem, ...]
    included_files: tuple[str, ...]
    omitted_files: tuple[OmittedFile, ...]
    prompt_tokens: int = Field(ge=0)
    covers_all_changed_files: bool


class ReviewResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    omitted_files: tuple[OmittedFile, ...]
    covers_all_changed_files: bool


class ReviewOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[FindingCandidate, ...]
    packing_strategy_version: str = Field(min_length=1)
    covers_all_changed_files: bool
    omitted_files: tuple[OmittedFile, ...]
    cancelled: bool = False

    def is_complete(self) -> bool:
        return not self.cancelled and self.covers_all_changed_files
