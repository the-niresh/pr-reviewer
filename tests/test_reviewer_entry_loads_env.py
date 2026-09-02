"""`reviewer` must load .env before anything reads os.environ.

config.get_settings() calls load_dotenv, but the TUI connect path reads os.environ
directly and never calls it. That gap meant PR_REVIEWER_HOSTED_ORIGIN and
GITHUB_APP_SLUG were invisible to the TUI, so the connect screen could only ever
raise "is not set" and never show the GitHub link. The whole point of the product is
that the link comes from the TUI, so this is load-bearing, not cosmetic.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run(script: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_entry_point_loads_dotenv_so_the_tui_can_read_it(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "PR_REVIEWER_HOSTED_ORIGIN=https://example.test\nGITHUB_APP_SLUG=example-slug\n",
        encoding="utf-8",
    )
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "PYTHONPATH": str(REPO / "src"),
    }
    script = (
        "from pr_reviewer.reviewer_entry import main\n"
        "main(['--no-such-subcommand'])\n"
        "import os\n"
        "print('ORIGIN=' + os.environ.get('PR_REVIEWER_HOSTED_ORIGIN', ''))\n"
        "print('SLUG=' + os.environ.get('GITHUB_APP_SLUG', ''))\n"
    )
    result = _run(script, tmp_path, env)
    assert "ORIGIN=https://example.test" in result.stdout, result.stdout + result.stderr
    assert "SLUG=example-slug" in result.stdout, result.stdout + result.stderr


def test_the_check_fails_when_no_dotenv_is_present(tmp_path: Path) -> None:
    """Without a .env the variables stay unset, so the test above cannot pass vacuously."""
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "PYTHONPATH": str(REPO / "src"),
    }
    script = (
        "from pr_reviewer.reviewer_entry import main\n"
        "main(['--no-such-subcommand'])\n"
        "import os\n"
        "print('ORIGIN=' + os.environ.get('PR_REVIEWER_HOSTED_ORIGIN', ''))\n"
    )
    result = _run(script, tmp_path, env)
    assert "ORIGIN=\n" in result.stdout or result.stdout.strip().endswith("ORIGIN="), (
        result.stdout + result.stderr
    )
