"""Dashboard request and response shapes. No I/O."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApprovalBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Literal["approved", "rejected"]


class JobItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str = Field(min_length=1)
    runner_id: str = Field(min_length=1)
    repository_id: int
    status: str = Field(min_length=1)


class FindingItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    review_job_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: str = Field(min_length=1)


class CostItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
