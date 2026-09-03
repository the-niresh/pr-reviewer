"""reviewer logout: the non-interactive counterpart to the TUI's `l` binding."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_refuses_without_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pr_reviewer.runner.cli.logout import main
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "some-credential")
    monkeypatch.setattr("pr_reviewer.runner.cli.logout.default_config_dir", lambda: tmp_path)

    code = main([])

    assert code == 1
    assert secrets.get("runner_credential") == "some-credential"


def test_reports_when_not_signed_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pr_reviewer.runner.cli.logout import main

    monkeypatch.setattr("pr_reviewer.runner.cli.logout.default_config_dir", lambda: tmp_path)

    assert main(["--yes"]) == 1


def test_yes_deletes_the_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pr_reviewer.runner.cli.logout import main
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "some-credential")
    monkeypatch.setattr("pr_reviewer.runner.cli.logout.default_config_dir", lambda: tmp_path)
    # No hosted origin override: resolved_hosted_origin() defaults to production, so this
    # also proves the best-effort revoke never blocks the local logout even when that call
    # would go out over a real network -- see runner/logout.py's own module docstring.
    monkeypatch.delenv("PR_REVIEWER_HOSTED_ORIGIN", raising=False)

    code = main(["--yes"])

    assert code == 0
    assert secrets.get("runner_credential") is None


def test_setup_uninstall_and_the_tui_agree_on_one_config_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: reviewer setup wrote to ~/.config/pr-reviewer/secrets, reviewer
    # uninstall/start/stop wrote to ~/.local/share/pr-reviewer/secrets, and the TUI wrote
    # to ~/.config/pr-reviewer directly -- three directories, so a model key or runner
    # credential set through one entry point was invisible to the others. All of them
    # now resolve through the one shared default_config_dir().
    import pr_reviewer.cli.main as setup_module
    from pr_reviewer.runner.secrets import FileSecretStore, default_config_dir

    assert default_config_dir() == Path.home() / ".config" / "pr-reviewer"

    calls: list[Path] = []
    real_file_secret_store = FileSecretStore

    class RecordingFileSecretStore(real_file_secret_store):  # type: ignore[misc]
        def __init__(self, directory: str | Path) -> None:
            calls.append(Path(directory))
            super().__init__(directory)

    monkeypatch.setattr("pr_reviewer.runner.secrets.FileSecretStore", RecordingFileSecretStore)

    # This environment has no usable OS secret service (see runner/secrets.py's own probe),
    # so get_secret_store already falls back to FileSecretStore here without forcing it.
    setup_module._default_secrets()

    assert calls == [default_config_dir()]
