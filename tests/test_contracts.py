from __future__ import annotations

import pytest
from pydantic import ValidationError

from pr_reviewer.contracts import Finding, PullRequestRef


def test_finding_requires_valid_line_range() -> None:
    with pytest.raises(ValidationError):
        Finding(
            id="finding-1",
            review_job_id="job-1",
            concern="security",
            severity="high",
            category="sql",
            file_path="app.py",
            line_start=10,
            line_end=9,
            title="Unsafe query",
            rationale="The input reaches SQL text.",
            evidence=["app.py:10"],
            confidence=0.8,
            verified=True,
            verification_method="sandbox",
            public_safe=False,
            status="queued_for_human",
        )


def test_pull_request_ref_requires_positive_number() -> None:
    with pytest.raises(ValidationError):
        PullRequestRef(owner="foodspector", repository="api", number=0)
