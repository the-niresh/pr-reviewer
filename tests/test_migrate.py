from __future__ import annotations

from pr_reviewer.db.migrate import get_missing_applied_migration_filenames


def test_finds_missing_applied_migrations() -> None:
    assert get_missing_applied_migration_filenames(
        ["0001_initial.sql", "9999_missing.sql"],
        ["0001_initial.sql"],
    ) == ["9999_missing.sql"]
