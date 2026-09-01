"""Supply-chain checks run locally and from CI. Absence of a check is a test failure."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pr_reviewer.supply_chain import (
    COMMANDS,
    secret_refusals,
    unpinned_image_refs,
)

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_supply_chain.py"
CI = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ci_invokes_each_local_check_without_fail_open() -> None:
    assert "|| true" not in CI
    for name in COMMANDS:
        needle = f"scripts/check_supply_chain.py {name}"
        assert needle in CI, needle


def test_local_script_exists_for_each_check() -> None:
    assert SCRIPT.is_file()
    text = SCRIPT.read_text(encoding="utf-8")
    assert "pr_reviewer.supply_chain" in text


def test_secret_scan_refuses_a_tracked_pem() -> None:
    hits = secret_refusals(
        "src/pr_reviewer/widget.py",
        "-----BEGIN PRIVATE KEY-----\nMIIFake\n",
    )
    assert hits == ["src/pr_reviewer/widget.py:1: private-key header"]


def test_secret_scan_allows_localhost_postgres_and_test_canaries() -> None:
    assert (
        secret_refusals(
            "src/pr_reviewer/config.py",
            'LOCAL_DATABASE_HOST = "postgresql://pr_reviewer:pr_reviewer@localhost:54329"\n',
        )
        == []
    )
    assert (
        secret_refusals(
            "tests/test_connector_contracts.py",
            "-----BEGIN PRIVATE KEY-----\ngho_must_never_be_stored\n",
        )
        == []
    )
    assert (
        secret_refusals(
            "src/pr_reviewer/connectors/audit.py",
            r'_PEM_HEADER_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")',
        )
        == []
    )


def test_secret_scan_refuses_a_remote_postgres_url() -> None:
    hits = secret_refusals(
        "src/pr_reviewer/config.py",
        'url = "postgresql://user:pass@db.example.net/app"\n',
    )
    assert hits == ["src/pr_reviewer/config.py:1: remote postgres url"]


def test_container_scan_refuses_an_unpinned_tag() -> None:
    hits = unpinned_image_refs("Dockerfile", "FROM python:3.12\n")
    assert hits == ["Dockerfile:1: unpinned python:3.12"]


def test_container_scan_accepts_a_digest_pin() -> None:
    digest = "sha256:" + ("a" * 64)
    assert unpinned_image_refs("Dockerfile", f"FROM busybox@{digest}\n") == []


def test_all_four_checks_pass_on_this_checkout() -> None:
    result = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "all"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert "lock: uv.lock matches the project" in combined
    assert "secret scan: no refused hits in tracked files" in combined
    assert "container scan: digest-pinned images" in combined
