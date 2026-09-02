"""Repositories screen: permitted repositories, open pull requests, start review."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from pr_reviewer.tui.github_reads import (
    FakeInstallationRepositoriesReader,
    FakeOpenPullRequestsReader,
    InstallationRepositoriesReader,
    OpenPullRequest,
    OpenPullRequestsReader,
    PermittedRepository,
    try_real_installation_repositories_reader,
    try_real_open_pull_requests_reader,
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
        self._repositories_reader = (
            repositories_reader
            or try_real_installation_repositories_reader()
            or FakeInstallationRepositoriesReader()
        )
        self._pull_requests_reader = (
            pull_requests_reader
            or try_real_open_pull_requests_reader()
            or FakeOpenPullRequestsReader()
        )
        self._repositories = self._repositories_reader.list_repositories(installation_id)
        self._selected_repository: PermittedRepository | None = None
        self._pull_requests: tuple[OpenPullRequest, ...] = ()

    def compose(self) -> ComposeResult:
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
            if not self._pull_requests:
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
            self._pull_requests = self._pull_requests_reader.list_open_pull_requests(owner, name)
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
