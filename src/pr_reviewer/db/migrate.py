from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pr_reviewer.db.client import close_pool, connection

MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")
MIGRATION_LOCK_ID = 41920260825


@dataclass(frozen=True)
class Migration:
    filename: str
    sql: str
    checksum: str


def get_missing_applied_migration_filenames(
    applied_filenames: list[str],
    available_filenames: list[str],
) -> list[str]:
    available = set(available_filenames)
    return [filename for filename in applied_filenames if filename not in available]


def load_migrations() -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(MIGRATIONS_DIRECTORY.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        migrations.append(Migration(filename=path.name, sql=sql, checksum=checksum))
    return migrations


def migrate() -> None:
    migrations = load_migrations()

    with connection() as conn:
        conn.execute("select pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
        try:
            conn.execute(
                """
                create table if not exists schema_migrations (
                  filename text primary key,
                  checksum text not null,
                  applied_at timestamptz not null default now()
                )
                """
            )
            conn.commit()

            cursor = conn.execute("select filename, checksum from schema_migrations")
            applied_rows = [dict(row) for row in cursor.fetchall()]
            applied_filenames = [str(row["filename"]) for row in applied_rows]
            available_filenames = [migration.filename for migration in migrations]
            missing = get_missing_applied_migration_filenames(
                applied_filenames,
                available_filenames,
            )
            if missing:
                raise RuntimeError(f"Applied migration files are missing: {', '.join(missing)}")

            applied = {str(row["filename"]): str(row["checksum"]) for row in applied_rows}

            for migration in migrations:
                applied_checksum = applied.get(migration.filename)
                if applied_checksum is not None:
                    if applied_checksum != migration.checksum:
                        raise RuntimeError(f"Migration checksum mismatch: {migration.filename}")
                    continue

                with conn.transaction():
                    conn.execute(migration.sql)
                    conn.execute(
                        "insert into schema_migrations (filename, checksum) values (%s, %s)",
                        (migration.filename, migration.checksum),
                    )
        finally:
            conn.execute("select pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
            conn.commit()


def main() -> None:
    try:
        migrate()
        print("Database migrations complete.")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
