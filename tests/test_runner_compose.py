"""Static contract for docker-compose.runner.yml (Runtime Task 7).

This file is about the compose document itself, not a running container. Loopback binding, the
named volume, digest pinning, the non-root user, the health check, and the absence of a
plaintext password are all properties of the file on disk. If a later change relaxes any of them
in the YAML and the live service still happens to work, these tests must still fail.

LocalVectorStore behaviour (start/migrate/health/stop, full-mode gate, secret storage) lives in
tests/test_local_pgvector.py. This file never imports that module, so a missing postgres.py
cannot interrupt collection here.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_PATH = REPO_ROOT / "docker-compose.runner.yml"


def _compose_text() -> str:
    return COMPOSE_PATH.read_text(encoding="utf-8")


def test_runner_compose_file_exists() -> None:
    assert COMPOSE_PATH.is_file(), (
        "docker-compose.runner.yml is the runner's pgvector service definition; it is not "
        "docker-compose.yml, which is the hosted-dev database."
    )


def test_pgvector_image_is_pinned_by_digest() -> None:
    # Tag+digest (pgvector/pgvector:pg16@sha256:...) is fine. A tag alone is not.
    text = _compose_text()
    assert "@sha256:" in text
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("image:"):
            continue
        assert "@sha256:" in stripped, f"image must be pinned by digest: {stripped!r}"


def test_postgres_runs_as_a_non_root_user() -> None:
    text = _compose_text()
    lowered = text.lower()
    assert "user:" in lowered
    assert "user: \"0\"" not in lowered
    assert "user: '0'" not in lowered
    assert "user: 0" not in lowered
    assert "user: root" not in lowered
    assert "user: \"root\"" not in lowered
    # Invoking uid/gid, not the image's postgres user. Hardcoding 999:999 is the path that
    # cannot read a 0600 password file owned by a non-root operator.
    assert "999:999" not in text
    assert "${PR_REVIEWER_PG_UID}" in text
    assert "${PR_REVIEWER_PG_GID}" in text


def test_postgres_binds_loopback_only() -> None:
    text = _compose_text()
    assert "127.0.0.1:" in text
    assert "0.0.0.0:" not in text
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("-") or ":" not in stripped:
            continue
        if "5432" in stripped and "127.0.0.1" not in stripped:
            raise AssertionError(
                f"port mapping {stripped!r} is not loopback-only; a bare host port publishes "
                "on every interface"
            )


def test_postgres_data_uses_a_named_volume() -> None:
    text = _compose_text()
    assert "volumes:" in text
    assert "/var/lib/postgresql/data" in text
    for line in text.splitlines():
        if "/var/lib/postgresql/data" in line and (":/" in line or "./" in line):
            raise AssertionError(
                f"postgres data must be a named volume, not a host bind: {line!r}"
            )


def test_compose_defines_a_healthcheck() -> None:
    text = _compose_text()
    assert "healthcheck:" in text


def test_compose_file_does_not_embed_a_database_password() -> None:
    text = _compose_text()
    assert "POSTGRES_PASSWORD:" not in text
    assert "postgresql://" not in text
    assert "POSTGRES_PASSWORD_FILE" in text or "secrets:" in text
