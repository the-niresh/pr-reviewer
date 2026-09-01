"""Repositories screen listing installation-permitted repositories."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, Select, Static

from pr_reviewer.local_store.repo_config import (
    RepoConfigStore,
    RepoModelChoice,
    default_repo_model_choice,
)
from pr_reviewer.models.catalogue import list_providers, models_for
from pr_reviewer.security.instruction_sources import ReviewPolicy, default_review_policy
from pr_reviewer.tui.installation_snapshot import InstallationSnapshot


def format_policy_summary(policy: ReviewPolicy) -> str:
    flags: list[str] = []
    if policy.instructions_enabled:
        flags.append("instructions")
    if policy.auto_post:
        flags.append("auto_post")
    if policy.specialist_mode:
        flags.append("specialists")
    if not policy.verification_required:
        flags.append("no_verify")
    if policy.public_posting:
        flags.append("public_post")
    return ", ".join(flags) if flags else "defaults"


def format_model_summary(choice: RepoModelChoice) -> str:
    return f"{choice.provider_id}/{choice.model_id}"


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

    def __init__(
        self,
        snapshot: InstallationSnapshot,
        *,
        repo_config: RepoConfigStore | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._snapshot = snapshot
        self._repo_config = repo_config

    def compose(self) -> ComposeResult:
        repo_ids = [repo.github_repository_id for repo in self._snapshot.repositories]
        policies = (
            self._repo_config.all_for(repo_ids)
            if self._repo_config is not None
            else {repo_id: default_review_policy() for repo_id in repo_ids}
        )
        model_choices = (
            self._repo_config.all_model_choices_for(repo_ids)
            if self._repo_config is not None
            else {repo_id: default_repo_model_choice() for repo_id in repo_ids}
        )
        provider_options = [
            (provider.label, provider.provider_id) for provider in list_providers()
        ]
        rows: list[Widget] = [
            Label("Repositories", classes="repositories-heading", id="repositories-heading")
        ]
        for repo in self._snapshot.repositories:
            repo_id = repo.github_repository_id
            choice = model_choices[repo_id]
            rows.append(
                Static(
                    (
                        f"{repo.name} ({repo_id})"
                        f" - {format_policy_summary(policies[repo_id])}"
                    ),
                    classes="repository-row",
                    id=f"repo-{repo_id}",
                )
            )
            rows.append(
                Select(
                    provider_options,
                    id=f"repo-provider-{repo_id}",
                    value=choice.provider_id,
                )
            )
            rows.append(
                Select(
                    [(model.label, model.model_id) for model in models_for(choice.provider_id)],
                    id=f"repo-model-{repo_id}",
                    value=choice.model_id,
                )
            )
            rows.append(
                Static(
                    format_model_summary(choice),
                    classes="repository-model-summary",
                    id=f"repo-model-summary-{repo_id}",
                )
            )
        yield Vertical(*rows, id="repositories-panel")

    def on_select_changed(self, event: Select.Changed) -> None:
        if self._repo_config is None or event.value is Select.NULL:
            return
        widget_id = event.select.id
        if widget_id is None:
            return
        if widget_id.startswith("repo-provider-"):
            repo_id = int(widget_id.removeprefix("repo-provider-"))
            provider_id = str(event.value)
            model_id = models_for(provider_id)[0].model_id
            model_select = self.query_one(f"#repo-model-{repo_id}", Select)
            model_select.set_options(
                [(model.label, model.model_id) for model in models_for(provider_id)]
            )
            model_select.value = model_id
            choice = RepoModelChoice(provider_id=provider_id, model_id=model_id)
            self._repo_config.set_model_choice(repo_id, choice)
            self._update_model_summary(repo_id, choice)
            return
        if widget_id.startswith("repo-model-"):
            repo_id = int(widget_id.removeprefix("repo-model-"))
            provider_id = str(self.query_one(f"#repo-provider-{repo_id}", Select).value)
            model_id = str(event.value)
            choice = RepoModelChoice(provider_id=provider_id, model_id=model_id)
            self._repo_config.set_model_choice(repo_id, choice)
            self._update_model_summary(repo_id, choice)

    def _update_model_summary(self, repo_id: int, choice: RepoModelChoice) -> None:
        summary = self.query_one(f"#repo-model-summary-{repo_id}", Static)
        summary.update(format_model_summary(choice))
