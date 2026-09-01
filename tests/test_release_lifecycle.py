"""Live compose.release.yml startup, health, stop, and same-digest restart.

Task 23 remaining step. These tests drive local Docker Compose. They do not
talk to GitHub and they do not use a published prior release tag. A distinct
prior GitHub release image is not present on this machine, so rollback here
is stop then start again on the same pinned digest.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO / "compose.release.yml"
PROJECT = "pr-reviewer-release-lifecycle"
WAIT_SECONDS = 60


def _docker() -> str:
    binary = shutil.which("docker")
    if binary is None:
        pytest.skip("docker is required for release compose lifecycle tests")
    return binary


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    docker = _docker()
    command = [
        docker,
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "-p",
        PROJECT,
        *args,
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=WAIT_SECONDS,
        cwd=REPO,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"{command} failed ({result.returncode}): {result.stderr}\n{result.stdout}"
        )
    return result


def _ps() -> list[dict[str, object]]:
    result = _compose("ps", "--format", "json", check=False)
    if result.returncode != 0:
        return []
    text = result.stdout.strip()
    if not text:
        return []
    rows: list[dict[str, object]] = []
    if text.startswith("["):
        parsed = json.loads(text)
        assert isinstance(parsed, list)
        rows = [item for item in parsed if isinstance(item, dict)]
    else:
        for line in text.splitlines():
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _all_healthy(rows: list[dict[str, object]]) -> bool:
    if len(rows) < 4:
        return False
    for row in rows:
        health = str(row.get("Health") or "")
        state = str(row.get("State") or "")
        if health.lower() != "healthy" and "healthy" not in state.lower():
            return False
    return True


def _none_running(rows: list[dict[str, object]]) -> bool:
    for row in rows:
        state = str(row.get("State") or "").lower()
        if state in {"running", "restarting"}:
            return False
    return True


def _wait_until(
    predicate: Callable[[list[dict[str, object]]], bool], *, message: str
) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    last: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        last = _ps()
        if predicate(last):
            return
        time.sleep(0.5)
    raise TimeoutError(f"{message} within {WAIT_SECONDS}s; last ps={last!r}")


@pytest.fixture
def release_stack() -> Iterator[None]:
    _compose("down", "--remove-orphans", check=False)
    yield
    _compose("down", "--remove-orphans", check=False)


def test_release_compose_starts_reports_healthy_and_stops_gracefully(
    release_stack: None,
) -> None:
    _compose("up", "-d", "--no-build")
    _wait_until(_all_healthy, message="release stack did not become healthy")
    _compose("stop", "-t", "5")
    _wait_until(_none_running, message="release stack did not stop")


def test_release_compose_stop_then_start_again_on_the_same_digest(
    release_stack: None,
) -> None:
    """Same pinned digest after stop. Not a prior GitHub release image."""
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "@sha256:" in text
    assert ":latest" not in text
    _compose("up", "-d", "--no-build")
    _wait_until(_all_healthy, message="first start was not healthy")
    _compose("stop", "-t", "5")
    _wait_until(_none_running, message="first stop did not complete")
    _compose("up", "-d", "--no-build")
    _wait_until(_all_healthy, message="restart on the same digest was not healthy")
    _compose("stop", "-t", "5")
    _wait_until(_none_running, message="final stop did not complete")
