"""Notification title and body. Restricted titles must not name the finding."""

from __future__ import annotations

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.contracts.notification import Confidentiality, NotificationPreview

RESTRICTED_TITLE = "Review finding needs attention"


def build_preview(finding: Finding, *, confidentiality: Confidentiality) -> NotificationPreview:
    if confidentiality == "restricted":
        return NotificationPreview(
            title=RESTRICTED_TITLE,
            body=(
                f"{finding.title}\n{finding.file_path}:{finding.line_start}\n{finding.rationale}"
            ),
            confidentiality=confidentiality,
        )
    return NotificationPreview(
        title="Your pull request was reviewed",
        body="A review finished.",
        confidentiality=confidentiality,
    )
