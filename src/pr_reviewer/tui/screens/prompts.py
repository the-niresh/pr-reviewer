"""Agent-prompts screen listing every specialist and its current prompt."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Button, Label, Select, Static, TextArea

from pr_reviewer.local_store.repo_config import RepoConfigStore
from pr_reviewer.tui.agent_prompt_catalogue import list_builtin_agent_prompts
from pr_reviewer.tui.installation_snapshot import InstallationSnapshot
from pr_reviewer.tui.repository_prompt import quote_repository_prompt


class AgentPromptsPanel(Widget):
    DEFAULT_CSS = """
    AgentPromptsPanel {
        padding: 1 2;
    }

    AgentPromptsPanel .prompts-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    AgentPromptsPanel .prompt-agent-heading {
        text-style: bold;
        margin-top: 1;
    }

    AgentPromptsPanel .prompt-content {
        color: $text-muted;
        margin-bottom: 1;
    }

    AgentPromptsPanel .custom-prompt-heading {
        text-style: bold;
        color: $accent;
        margin-top: 2;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        snapshot: InstallationSnapshot | None = None,
        *,
        repo_config: RepoConfigStore | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._snapshot = snapshot
        self._repo_config = repo_config
        repo_options = (
            [(repo.name, str(repo.github_repository_id)) for repo in snapshot.repositories]
            if snapshot is not None
            else []
        )
        self._repo_options = repo_options
        self._default_repo = repo_options[0][1] if repo_options else None

    def compose(self) -> ComposeResult:
        rows: list[Widget] = [
            Label("Agent prompts", classes="prompts-heading", id="agent-prompts-heading")
        ]
        for entry in list_builtin_agent_prompts():
            rows.append(
                Static(
                    f"{entry.label} ({entry.agent_id} v{entry.version})",
                    classes="prompt-agent-heading",
                    id=f"prompt-heading-{entry.agent_id}",
                )
            )
            rows.append(
                Static(
                    entry.content,
                    classes="prompt-content",
                    id=f"prompt-content-{entry.agent_id}",
                )
            )
        if self._repo_options:
            rows.extend(
                [
                    Label(
                        "Custom repository prompt",
                        classes="custom-prompt-heading",
                        id="custom-prompt-heading",
                    ),
                    Select(
                        self._repo_options,
                        id="custom-prompt-repo",
                        value=self._default_repo,
                    ),
                    TextArea(id="custom-prompt-input"),
                    Button("Save new version", id="custom-prompt-save", variant="primary"),
                    Static("", id="custom-prompt-status"),
                    Static("", id="custom-prompt-versions"),
                ]
            )
        yield Vertical(*rows, id="agent-prompts-panel")

    def on_mount(self) -> None:
        self._refresh_custom_prompt_display()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "custom-prompt-repo" and event.value is not Select.NULL:
            self._refresh_custom_prompt_display()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "custom-prompt-save" or self._repo_config is None:
            return
        repo_id = self._selected_repo_id()
        if repo_id is None:
            return
        content = self.query_one("#custom-prompt-input", TextArea).text.strip()
        if not content:
            self._set_custom_status("Enter prompt text first.")
            return
        try:
            saved = self._repo_config.add_repository_prompt(repo_id, content)
        except ValueError as exc:
            self._set_custom_status(str(exc))
            return
        quote_repository_prompt(saved.content)
        self.query_one("#custom-prompt-input", TextArea).clear()
        self._set_custom_status(f"Saved v{saved.version} for this repository.")
        self._refresh_custom_prompt_display()

    def _selected_repo_id(self) -> int | None:
        if not self._repo_options:
            return None
        value = self.query_one("#custom-prompt-repo", Select).value
        if value is Select.NULL:
            return None
        return int(str(value))

    def _refresh_custom_prompt_display(self) -> None:
        if self._repo_config is None or not self._repo_options:
            return
        repo_id = self._selected_repo_id()
        if repo_id is None:
            return
        versions = self._repo_config.list_repository_prompt_versions(repo_id)
        if not versions:
            self.query_one("#custom-prompt-versions", Static).update(
                "No custom prompt saved for this repository yet."
            )
            return
        lines = [
            f"v{item.version}{' (locked)' if item.locked else ''}: {item.content[:80]}"
            for item in versions
        ]
        self.query_one("#custom-prompt-versions", Static).update("\n".join(lines))

    def _set_custom_status(self, message: str) -> None:
        self.query_one("#custom-prompt-status", Static).update(message)
