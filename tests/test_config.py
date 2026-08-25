from __future__ import annotations

import certifi

from pr_reviewer.config import normalize_database_url


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
