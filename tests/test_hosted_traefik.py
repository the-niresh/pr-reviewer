"""Hosted Traefik overlay is present, valid, and not a live deploy."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SECRET_MARKERS = (
    "DATABASE_URL",
    "NEON",
    "WEBHOOK_SECRET",
    "GITHUB_APP_PRIVATE_KEY",
    "BEGIN ",
    "PRIVATE KEY",
)


def test_runbook_says_nothing_is_applied() -> None:
    text = (REPO / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    first = text.splitlines()[0]
    assert first.startswith("Nothing in this file is applied.")
    assert "reviewer.niresh.tech" in text
    assert "76.13.243.12" in text
    assert "4771544" in text
    assert "https://reviewer.niresh.tech/api/auth/github/callback" in text
    assert "https://reviewer.niresh.tech/api/github/webhook" in text


def test_traefik_file_defines_reviewer_router_and_service() -> None:
    text = (REPO / "deploy" / "traefik" / "reviewer.yml").read_text(encoding="utf-8")
    assert "Host(`reviewer.niresh.tech`)" in text
    assert "websecure" in text
    assert "http://api:8000" in text
    assert not any(marker in text for marker in SECRET_MARKERS)


def test_hosted_compose_labels_match_the_traefik_file() -> None:
    text = (REPO / "docker-compose.hosted.yml").read_text(encoding="utf-8")
    assert "Host(`reviewer.niresh.tech`)" in text
    assert "n8n-mkvx_proxy" in text
    assert 'traefik.http.services.reviewer.loadbalancer.server.port: "8000"' in text
    assert "up" not in text.split()
    assert not any(marker in text for marker in SECRET_MARKERS)


def test_hosted_compose_config_renders_offline() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is required to render compose config")
    result = subprocess.run(
        [
            docker,
            "compose",
            "-f",
            str(REPO / "compose.release.yml"),
            "-f",
            str(REPO / "docker-compose.hosted.yml"),
            "config",
            "--no-interpolate",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "reviewer.niresh.tech" in result.stdout
    assert "n8n-mkvx_proxy" in result.stdout
