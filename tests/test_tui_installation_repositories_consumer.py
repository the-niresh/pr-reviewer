"""TUI consumes the installation repository reader contract."""

from __future__ import annotations

from pr_reviewer.tui.github_reads import (
    FakeInstallationRepositoriesReader,
    PermittedRepository,
)
from pr_reviewer.tui.screens.repositories import RepositoriesPanel


def test_repositories_panel_calls_the_reader_for_live_data() -> None:
    reader = FakeInstallationRepositoriesReader(
        repositories=(PermittedRepository(id=99, full_name="acme/live"),)
    )
    panel = RepositoriesPanel(7010, repositories_reader=reader)
    assert panel._repositories[0].full_name == "acme/live"
