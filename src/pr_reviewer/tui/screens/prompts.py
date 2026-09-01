"""Agent-prompts screen listing every specialist and its current prompt."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

from pr_reviewer.tui.agent_prompt_catalogue import list_builtin_agent_prompts


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
    """

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
        yield Vertical(*rows, id="agent-prompts-panel")
