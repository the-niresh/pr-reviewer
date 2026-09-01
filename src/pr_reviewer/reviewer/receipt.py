"""Provenance receipt attached to a review finding."""

from __future__ import annotations

import re
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, computed_field

from pr_reviewer.contracts.finding import Finding

ContextSourceKind = Literal["diff", "retrieval", "profile", "graph"]
ModelProviderName = Literal["openai", "anthropic"]
COST_USD_PATTERN = re.compile(r"^(?:0|[1-9]\d{0,5})(?:\.\d{1,12})?$")


class ModelCallReceiptInput(Protocol):
    @property
    def review_job_id(self) -> str: ...

    @property
    def provider(self) -> ModelProviderName: ...

    @property
    def model(self) -> str: ...

    @property
    def prompt_version_id(self) -> str: ...

    @property
    def input_tokens(self) -> int: ...

    @property
    def output_tokens(self) -> int: ...

    @property
    def cost_usd(self) -> str: ...


class ReceiptTokens(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)

    @computed_field
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ReceiptModelCall(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: ModelProviderName
    model: str = Field(min_length=1)
    prompt_version_id: str = Field(min_length=1)
    tokens: ReceiptTokens
    cost_usd: str = Field(pattern=COST_USD_PATTERN.pattern)


class ReceiptContextSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ContextSourceKind
    name: str = Field(min_length=1)
    reference: str = Field(min_length=1)


class AssertedVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["asserted"] = "asserted"
    reason: str = Field(min_length=1)


class SandboxVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["verified"] = "verified"
    sandbox_run_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    detail: str = Field(min_length=1)


ReceiptVerification = Annotated[
    AssertedVerification | SandboxVerification,
    Field(discriminator="status"),
]


class FindingReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str = Field(min_length=1)
    review_job_id: str = Field(min_length=1)
    prompt_version_id: str = Field(min_length=1)
    model_call: ReceiptModelCall
    context_sources: tuple[ReceiptContextSource, ...] = Field(min_length=1)
    verification: ReceiptVerification

    @computed_field
    def verified(self) -> bool:
        return isinstance(self.verification, SandboxVerification)


def build_finding_receipt(
    *,
    finding: Finding,
    model_call: ModelCallReceiptInput,
    context_sources: tuple[ReceiptContextSource, ...],
    verification: ReceiptVerification,
) -> FindingReceipt:
    if finding.review_job_id != model_call.review_job_id:
        raise ValueError("finding and model call must belong to the same review job")
    if finding.verified and finding.verification_method != "sandbox":
        raise ValueError("verified findings must come from a sandbox run")
    if finding.verified and not isinstance(verification, SandboxVerification):
        raise ValueError("verified findings must cite a sandbox run")
    if not finding.verified and isinstance(verification, SandboxVerification):
        raise ValueError("asserted findings must not cite a sandbox run as verification")
    return FindingReceipt(
        finding_id=finding.id,
        review_job_id=finding.review_job_id,
        prompt_version_id=model_call.prompt_version_id,
        model_call=ReceiptModelCall(
            provider=model_call.provider,
            model=model_call.model,
            prompt_version_id=model_call.prompt_version_id,
            tokens=ReceiptTokens(
                input_tokens=model_call.input_tokens,
                output_tokens=model_call.output_tokens,
            ),
            cost_usd=model_call.cost_usd,
        ),
        context_sources=context_sources,
        verification=verification,
    )
