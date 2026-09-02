"""Terminal dashboard for review summaries."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from pr_reviewer.local_store.review_log import ReviewLogStore
from pr_reviewer.tui.installation_snapshot import InstallationSnapshot

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")
STOPPED_EARLY_MESSAGE = (
    "This review stopped early: the provider ran out of tokens partway through. "
    "Add credits or switch provider on your machine to finish reviewing the rest."
)


@dataclass(frozen=True)
class DashboardFinding:
    concern: str
    severity: str
    file_path: str
    line_start: int
    line_end: int
    title: str
    status: str


@dataclass(frozen=True)
class DashboardReview:
    review_job_id: str
    pull_request_number: int | None
    head_sha: str | None
    status: str
    stopped_early: bool
    stopped_early_message: str | None
    created_at: datetime
    findings: tuple[DashboardFinding, ...]


@dataclass(frozen=True)
class DashboardRepository:
    installation_id: int
    github_repository_id: int
    repository_name: str
    reviews: tuple[DashboardReview, ...]


class ReviewDashboardPanel(Widget):
    DEFAULT_CSS = """
    ReviewDashboardPanel {
        padding: 1 2;
    }

    ReviewDashboardPanel .dashboard-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    ReviewDashboardPanel .dashboard-overview {
        color: $text;
        border: solid $panel;
        padding: 1;
        margin-bottom: 1;
    }

    ReviewDashboardPanel Button.review-row {
        width: 100%;
        text-align: left;
        border: none;
        border-left: thick transparent;
        background: transparent;
        color: $text;
    }

    ReviewDashboardPanel Button.review-row:focus {
        background: $accent 25%;
        border-left: thick $accent;
        text-style: bold;
    }

    ReviewDashboardPanel .review-detail {
        border: solid $panel;
        padding: 1;
        margin-top: 1;
    }

    ReviewDashboardPanel .severity-critical {
        color: $error;
        text-style: bold;
    }

    ReviewDashboardPanel .severity-high {
        color: $warning;
        text-style: bold;
    }

    ReviewDashboardPanel .severity-medium {
        color: $accent;
        text-style: bold;
    }

    ReviewDashboardPanel .severity-low,
    ReviewDashboardPanel .severity-info {
        color: $text-muted;
    }
    """

    selected_review_id: reactive[str | None] = reactive(None)

    def __init__(
        self,
        repositories: Iterable[DashboardRepository],
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._repositories = tuple(repositories)
        self._reviews = tuple(
            (repository, review)
            for repository in self._repositories
            for review in repository.reviews
        )

    def compose(self) -> ComposeResult:
        yield Label("Reviews", classes="dashboard-heading", id="review-dashboard-heading")
        yield Static(
            self._overview_text(),
            classes="dashboard-overview",
            id="review-dashboard-overview",
        )
        yield Label(
            "Reviews table",
            classes="dashboard-heading",
            id="review-dashboard-table-heading",
        )
        yield Vertical(*self._row_buttons(), id="review-dashboard-table")
        yield Vertical(classes="review-detail", id="review-dashboard-detail")

    def on_mount(self) -> None:
        self._render_detail()

    def watch_selected_review_id(self, _review_id: str | None) -> None:
        self._render_detail()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("review-row-"):
            self.selected_review_id = button_id.removeprefix("review-row-")
            return
        if button_id == "review-detail-back":
            self.selected_review_id = None

    def back_to_table(self) -> bool:
        if self.selected_review_id is None:
            return False
        self.selected_review_id = None
        first_row = self.query("Button.review-row").first()
        if first_row is not None:
            first_row.focus()
        return True

    def _overview_text(self) -> str:
        reviews = [review for _repository, review in self._reviews]
        findings = [finding for review in reviews for finding in review.findings]
        counts = {level: 0 for level in SEVERITY_ORDER}
        for finding in findings:
            level = finding.severity.lower()
            if level in counts:
                counts[level] += 1
        return (
            f"Reviews: {len(reviews)}\n"
            f"Findings: {len(findings)}\n"
            f"Critical: {counts['critical']}  High: {counts['high']}  "
            f"Medium: {counts['medium']}  Low: {counts['low']}  Info: {counts['info']}"
        )

    def _row_buttons(self) -> list[Button | Static]:
        if not self._reviews:
            return [Static("No reviews yet. Run a review and it will appear here.")]
        rows: list[Button | Static] = []
        for repository, review in sorted(
            self._reviews,
            key=lambda item: item[1].created_at,
            reverse=True,
        ):
            rows.append(
                Button(
                    self._row_label(repository, review),
                    id=f"review-row-{_safe_id(review.review_job_id)}",
                    classes=f"review-row severity-{_worst_severity(review) or 'info'}",
                )
            )
        return rows

    def _row_label(self, repository: DashboardRepository, review: DashboardReview) -> str:
        severity = _worst_severity(review)
        severity_label = f"{severity.upper()} severity" if severity else "NO FINDINGS"
        status = "Stopped early" if review.stopped_early else review.status
        pr = (
            f"PR #{review.pull_request_number}"
            if review.pull_request_number is not None
            else "PR #?"
        )
        date = review.created_at.astimezone(UTC).date().isoformat()
        return (
            f"{repository.repository_name} | {pr} | {status} | "
            f"Findings {len(review.findings)} | {severity_label} | {date}"
        )

    def _render_detail(self) -> None:
        detail = self.query_one("#review-dashboard-detail", Vertical)
        detail.remove_children()
        if self.selected_review_id is None:
            detail.mount(Static("Press enter on a review row to open it."))
            return
        match = self._find_review(self.selected_review_id)
        if match is None:
            detail.mount(Static("Review not found."))
            return
        repository, review = match
        detail.mount(Button("Back to reviews", id="review-detail-back"))
        pr = (
            f"PR #{review.pull_request_number}"
            if review.pull_request_number is not None
            else "PR #?"
        )
        detail.mount(Label(pr, id="review-detail-title", classes="dashboard-heading"))
        detail.mount(Static(self._detail_status(review), id="review-detail-status"))
        head = review.head_sha[:12] if review.head_sha else "unknown head"
        detail.mount(Static(f"{repository.repository_name} | {head}"))
        detail.mount(Static(self._detail_findings(review), id="review-detail-findings"))

    def _detail_status(self, review: DashboardReview) -> str:
        if review.stopped_early:
            return f"Stopped early. {review.stopped_early_message or STOPPED_EARLY_MESSAGE}"
        return review.status

    def _detail_findings(self, review: DashboardReview) -> str:
        if not review.findings:
            return "No findings were recorded for this review."
        lines = []
        for finding in review.findings:
            severity = finding.severity.upper()
            lines.append(
                f"{severity} severity - {finding.title}\n"
                f"{finding.file_path}:{finding.line_start}-{finding.line_end} "
                f"| {finding.concern} | {finding.status}"
            )
        return "\n\n".join(lines)

    def _find_review(
        self,
        safe_review_id: str,
    ) -> tuple[DashboardRepository, DashboardReview] | None:
        for repository, review in self._reviews:
            if _safe_id(review.review_job_id) == safe_review_id:
                return repository, review
        return None


def dashboard_repositories_from_log(
    snapshot: InstallationSnapshot,
    review_log: ReviewLogStore,
) -> tuple[DashboardRepository, ...]:
    names_by_id = {repo.github_repository_id: repo.name for repo in snapshot.repositories}
    grouped: dict[int, list[DashboardReview]] = {}
    for payload in review_log.list_review_summaries():
        github_repository_id = int(payload["github_repository_id"])
        grouped.setdefault(github_repository_id, []).append(_review_from_payload(payload))
    repositories: list[DashboardRepository] = []
    for github_repository_id, name in names_by_id.items():
        repositories.append(
            DashboardRepository(
                installation_id=snapshot.installation_id,
                github_repository_id=github_repository_id,
                repository_name=name,
                reviews=tuple(grouped.get(github_repository_id, [])),
            )
        )
    return tuple(repositories)


def _review_from_payload(payload: dict[str, Any]) -> DashboardReview:
    created_at = payload.get("created_at")
    if isinstance(created_at, str):
        timestamp = datetime.fromisoformat(created_at)
    else:
        timestamp = datetime.now(UTC)
    return DashboardReview(
        review_job_id=str(payload["review_job_id"]),
        pull_request_number=int(payload["pull_request_number"]),
        head_sha=str(payload["head_sha"]),
        status=str(payload["status"]),
        stopped_early=bool(payload.get("stopped_early", False)),
        stopped_early_message=(
            STOPPED_EARLY_MESSAGE if bool(payload.get("stopped_early", False)) else None
        ),
        created_at=timestamp,
        findings=tuple(_finding_from_payload(item) for item in payload.get("findings", [])),
    )


def _finding_from_payload(payload: dict[str, Any]) -> DashboardFinding:
    return DashboardFinding(
        concern=str(payload["concern"]),
        severity=str(payload["severity"]),
        file_path=str(payload["file_path"]),
        line_start=int(payload["line_start"]),
        line_end=int(payload["line_end"]),
        title=str(payload["title"]),
        status=str(payload["status"]),
    )


def _worst_severity(review: DashboardReview) -> str | None:
    worst = None
    worst_rank = -1
    for finding in review.findings:
        severity = finding.severity.lower()
        rank = SEVERITY_RANK.get(severity, 0)
        if rank > worst_rank:
            worst = severity
            worst_rank = rank
    return worst


def _safe_id(value: str) -> str:
        return "".join(
            character if character.isalnum() or character == "-" else "-"
            for character in value
        )
