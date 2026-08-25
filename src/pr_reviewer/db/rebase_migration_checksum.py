from __future__ import annotations

import hashlib
import os
from pathlib import Path

from pr_reviewer.db.client import close_pool, connection
from pr_reviewer.db.migrate import MIGRATION_LOCK_ID, MIGRATIONS_DIRECTORY


def validate_migration_rebase_request(
    environment: dict[str, str | None],
    filename: str | None,
) -> str:
    if environment.get("ALLOW_DEV_MIGRATION_REBASE") != "1":
        raise RuntimeError("Set ALLOW_DEV_MIGRATION_REBASE=1 to repair a migration checksum")
    if not filename:
        raise RuntimeError("A migration filename is required")
    path = Path(filename)
    if path.name != filename or not filename.endswith(".sql"):
        raise RuntimeError(f"Invalid migration filename: {filename}")
    return filename


def rebase_migration_checksum(
    filename: str | None,
    environment: dict[str, str | None] | None = None,
) -> None:
    migration_filename = validate_migration_rebase_request(
        environment or dict(os.environ),
        filename,
    )
    sql = (MIGRATIONS_DIRECTORY / migration_filename).read_text(encoding="utf-8")
    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()

    with connection() as conn:
        conn.execute("select pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
        try:
            with conn.transaction():
                cursor = conn.execute(
                    """
                    update schema_migrations
                    set checksum = %s
                    where filename = %s
                    returning filename
                    """,
                    (checksum, migration_filename),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Migration is not recorded: {migration_filename}")
        finally:
            conn.execute("select pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
            conn.commit()


def main() -> None:
    import sys

    try:
        rebase_migration_checksum(sys.argv[1] if len(sys.argv) > 1 else None)
        print("Migration checksum repaired.")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
