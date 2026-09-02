"""Push a finished review summary to the hosted plane (findings only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

ALLOWED_FINDING_FIELDS = frozenset(
    {"concern", "severity", "file_path", "line_start", "line_end", "title", "status"}
)
ALLOWED_SUMMARY_FIELDS = frozenset(
    {
        "review_job_id",
        "installation_id",
        "github_repository_id",
        "pull_request_number",
        "head_sha",
        "status",
        "stopped_early",
        "findings",
    }
)
FORBIDDEN_PAYLOAD_KEYS = frozenset({"reasoning", "diff", "source", "api_key", "model_key"})


@dataclass(frozen=True)
class ReviewFindingSummary:
    concern: str
    severity: str
    file_path: str
    line_start: int
    line_end: int
    title: str
    status: str


@dataclass(frozen=True)
class ReviewSummaryPush:
    review_job_id: str
    installation_id: int
    github_repository_id: int
    pull_request_number: int
    head_sha: str
    status: str
    stopped_early: bool = False
    findings: tuple[ReviewFindingSummary, ...] = ()


@dataclass(frozen=True)
class PushReviewSummaryResult:
    ok: bool
    error: str = ""


class ReviewSummaryClient(Protocol):
    def push(self, payload: dict[str, object]) -> None: ...


def build_summary_payload(summary: ReviewSummaryPush) -> dict[str, object]:
    findings = [
        {field: getattr(finding, field) for field in ALLOWED_FINDING_FIELDS}
        for finding in summary.findings
    ]
    payload = {
        "review_job_id": summary.review_job_id,
        "installation_id": summary.installation_id,
        "github_repository_id": summary.github_repository_id,
        "pull_request_number": summary.pull_request_number,
        "head_sha": summary.head_sha,
        "status": summary.status,
        "stopped_early": summary.stopped_early,
        "findings": findings,
    }
    extra = set(payload) - ALLOWED_SUMMARY_FIELDS
    if extra:
        raise ValueError(f"unexpected summary fields: {sorted(extra)}")
    return payload


def _reject_forbidden_values(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError(f"forbidden field {key!r}")
            _reject_forbidden_values(nested)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_values(item)


def push_review_summary(
    client: ReviewSummaryClient,
    summary: ReviewSummaryPush,
) -> PushReviewSummaryResult:
    try:
        payload = build_summary_payload(summary)
        _reject_forbidden_values(payload)
        client.push(payload)
    except Exception as exc:  # noqa: BLE001 - return to the TUI
        return PushReviewSummaryResult(ok=False, error=str(exc))
    return PushReviewSummaryResult(ok=True)
