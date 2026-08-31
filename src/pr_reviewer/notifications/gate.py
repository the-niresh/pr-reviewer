"""System-owned routing. The model does not choose the destination."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.retrieval.sensitivity import SensitivityScore
from pr_reviewer.security.instruction_sources import ReviewPolicy
from pr_reviewer.verification.docker_sandbox import VerificationResult

NotifyPurpose = Literal["security_alert", "review_ping"]
RequiredConfidentiality = Literal["restricted", "ordinary"]

_HIGH_FIX_DENSITY = 0.25
_HIGH_CALLER_COUNT = 3


@dataclass(frozen=True)
class GateDecision:
    queue_for_human: bool
    confidentiality: RequiredConfidentiality
    notify_purpose: NotifyPurpose | None
    allow_public_post: bool
    reason: str


def is_high_sensitivity(score: SensitivityScore) -> bool:
    return bool(score.structural_flags) or score.fix_density >= _HIGH_FIX_DENSITY or (
        score.caller_count >= _HIGH_CALLER_COUNT
    )


def route_finding(
    finding: Finding,
    policy: ReviewPolicy,
    *,
    sensitivity_by_path: Mapping[str, SensitivityScore] | None = None,
    verification: VerificationResult | None = None,
) -> GateDecision:
    private = finding.concern == "security" and (
        not finding.public_safe or finding.severity == "critical"
    )
    score = None if sensitivity_by_path is None else sensitivity_by_path.get(finding.file_path)
    high = score is not None and is_high_sensitivity(score)
    inconclusive = verification is not None and verification.status in {"failed", "inconclusive"}
    allow_public_post = (
        policy.auto_post
        and policy.public_posting
        and finding.verified
        and finding.public_safe
        and not private
        and not high
        and not inconclusive
    )
    queue_for_human = not allow_public_post
    confidentiality: RequiredConfidentiality = "restricted" if private else "ordinary"
    notify_purpose: NotifyPurpose | None = "security_alert" if private else None
    if private:
        reason = "unsafe or critical security finding"
    elif not finding.verified or inconclusive:
        reason = "unverified or inconclusive finding"
    elif high:
        reason = "high-sensitivity file"
    elif queue_for_human:
        reason = "policy queues for a person"
    else:
        reason = "public-safe and verified"
    return GateDecision(
        queue_for_human=queue_for_human,
        confidentiality=confidentiality,
        notify_purpose=notify_purpose,
        allow_public_post=allow_public_post,
        reason=reason,
    )
