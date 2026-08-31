from __future__ import annotations

from pathlib import Path

import certifi
import pytest

from pr_reviewer.config import normalize_database_url


def test_two_different_roots_produce_two_different_database_names() -> None:
    from pr_reviewer.config import database_name_for_root

    first = database_name_for_root(Path("/tmp/pr-reviewer-13a"))
    second = database_name_for_root(Path("/tmp/pr-reviewer-13b"))
    assert first != second
    assert first == "pr_reviewer_13a"
    assert second == "pr_reviewer_13b"


def test_explicit_database_url_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    from pr_reviewer.config import get_settings

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@example.com:5432/explicit")
    assert "explicit" in get_settings().database_url
    assert "example.com" in get_settings().database_url


def test_database_url_adds_system_root_cert_for_verify_full() -> None:
    value = normalize_database_url(
        "postgresql://user:pass@example.com/db?sslmode=verify-full"
    )

    assert "sslmode=verify-full" in value
    assert "sslrootcert=" in value
    assert certifi.where().replace("/", "%2F") in value


def test_database_url_keeps_existing_root_cert() -> None:
    value = normalize_database_url(
        "postgresql://user:pass@example.com/db?sslmode=verify-full&sslrootcert=/tmp/root.crt"
    )

    assert "sslrootcert=%2Ftmp%2Froot.crt" in value
