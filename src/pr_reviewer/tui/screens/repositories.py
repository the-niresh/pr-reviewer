"""Repositories screen: permitted repositories, open pull requests, start review."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from pr_reviewer.tui.github_reads import (
    InstallationRepositoriesReader,
    OpenPullRequest,
    OpenPullRequestsReader,
    PermittedRepository,
    ReaderUnavailable,
    resolve_installation_repositories_reader,
    resolve_open_pull_requests_reader,
)


class PullRequestSelected(Message):
    def __init__(
        self,
        *,
        repository_full_name: str,
        pull_request_number: int,
        head_sha: str,
    ) -> None:
        self.repository_full_name = repository_full_name
        self.pull_request_number = pull_request_number
        self.head_sha = head_sha
        super().__init__()


class RepositoriesPanel(Widget):
    DEFAULT_CSS = """
    RepositoriesPanel {
        padding: 1 2;
    }

    RepositoriesPanel .repositories-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    RepositoriesPanel .repository-row {
        margin-bottom: 1;
    }
    """

    view: reactive[str] = reactive("repositories")

    def __init__(
        self,
        installation_id: int,
        *,
        repositories_reader: InstallationRepositoriesReader | None = None,
        pull_requests_reader: OpenPullRequestsReader | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._installation_id = installation_id

        # An injected reader (tests, or a caller that already resolved one) is used as-is.
        # Otherwise this must go through the hosted plane for real -- and if that cannot
        # happen yet, the reason is kept so compose() can say so on screen, never silently
        # rendering an empty list that looks identical to "this installation has zero repos".
        self._pull_requests_reader: OpenPullRequestsReader | None = pull_requests_reader
        self._pull_requests_unavailable_reason: str | None = None
        if pull_requests_reader is None:
            resolved_pull_requests = resolve_open_pull_requests_reader()
            if isinstance(resolved_pull_requests, ReaderUnavailable):
                self._pull_requests_unavailable_reason = resolved_pull_requests.reason
            else:
                self._pull_requests_reader = resolved_pull_requests

        repositories_source: InstallationRepositoriesReader | None = repositories_reader
        self._repositories_unavailable_reason: str | None = None
        if repositories_source is None:
            resolved_repositories = resolve_installation_repositories_reader()
            if isinstance(resolved_repositories, ReaderUnavailable):
                self._repositories_unavailable_reason = resolved_repositories.reason
            else:
                repositories_source = resolved_repositories

        self._repositories: tuple[PermittedRepository, ...] = ()
        if repositories_source is not None:
            try:
                self._repositories = repositories_source.list_repositories(installation_id)
            except Exception as exc:  # hosted plane or GitHub call failed after all
                self._repositories_unavailable_reason = f"Could not load repositories: {exc}"

        self._selected_repository: PermittedRepository | None = None
        self._pull_requests: tuple[OpenPullRequest, ...] = ()
        self._pull_requests_error: str | None = None

    def compose(self) -> ComposeResult:
        if self._repositories_unavailable_reason is not None:
            yield Vertical(
                Label("Repositories", classes="repositories-heading", id="repositories-heading"),
                Static(self._repositories_unavailable_reason, id="repositories-unavailable"),
            )
            return

        if not self._repositories:
            yield Vertical(
                Label("Repositories", classes="repositories-heading", id="repositories-heading"),
                Static(
                    "No repositories are permitted for this installation yet.",
                    id="repositories-empty",
                ),
            )
            return

        if self.view == "pull_requests" and self._selected_repository is not None:
            repo = self._selected_repository
            rows: list[Widget] = [
                Label(f"Pull requests for {repo.full_name}", classes="repositories-heading"),
                Button("Back to repositories", id="repositories-back"),
            ]
            if self._pull_requests_error is not None:
                rows.append(Static(self._pull_requests_error, id="pull-requests-unavailable"))
            elif not self._pull_requests:
                rows.append(
                    Static(
                        f"No open pull requests on {repo.full_name}.",
                        id="pull-requests-empty",
                    )
                )
            else:
                for pull_request in self._pull_requests:
                    rows.append(
                        Button(
                            f"#{pull_request.number} {pull_request.title} by {pull_request.author}",
                            id=f"pull-request-{pull_request.number}",
                            classes="repository-row",
                        )
                    )
            yield Vertical(*rows)
            return

        rows = [
            Label("Repositories", classes="repositories-heading", id="repositories-heading"),
        ]
        for repository in self._repositories:
            rows.append(
                Button(
                    repository.full_name,
                    id=f"repository-{repository.id}",
                    classes="repository-row",
                )
            )
        yield Vertical(*rows)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "repositories-back":
            self.view = "repositories"
            self._selected_repository = None
            self._pull_requests = ()
            self.refresh(recompose=True)
            return
        if button_id.startswith("repository-"):
            repo_id = int(button_id.removeprefix("repository-"))
            selected = next(repo for repo in self._repositories if repo.id == repo_id)
            owner, _, name = selected.full_name.partition("/")
            self._selected_repository = selected
            if self._pull_requests_reader is None:
                self._pull_requests = ()
                self._pull_requests_error = (
                    self._pull_requests_unavailable_reason or "Could not load pull requests."
                )
            else:
                try:
                    self._pull_requests = self._pull_requests_reader.list_open_pull_requests(
                        owner, name
                    )
                    self._pull_requests_error = None
                except Exception as exc:  # hosted plane or GitHub call failed after all
                    self._pull_requests = ()
                    self._pull_requests_error = f"Could not load pull requests: {exc}"
            self.view = "pull_requests"
            self.refresh(recompose=True)
            return
        if button_id.startswith("pull-request-"):
            number = int(button_id.removeprefix("pull-request-"))
            pull_request = next(pr for pr in self._pull_requests if pr.number == number)
            assert self._selected_repository is not None
            self.post_message(
                PullRequestSelected(
                    repository_full_name=self._selected_repository.full_name,
                    pull_request_number=pull_request.number,
                    head_sha=pull_request.head_sha,
                )
            )
