import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { db } from "./client";

const migrationsDirectory = join(
  dirname(fileURLToPath(import.meta.url)),
  "migrations",
);

type Migration = {
  filename: string;
  sql: string;
  checksum: string;
};

type AppliedMigration = {
  filename: string;
  checksum: string;
};

export function getMissingAppliedMigrationFilenames(
  appliedFilenames: readonly string[],
  availableFilenames: readonly string[],
): string[] {
  const available = new Set(availableFilenames);

  return appliedFilenames.filter((filename) => !available.has(filename));
}

async function loadMigrations(): Promise<Migration[]> {
  const filenames = (await readdir(migrationsDirectory))
    .filter((filename) => filename.endsWith(".sql"))
    .sort();

  return Promise.all(
    filenames.map(async (filename) => {
      const sql = await readFile(join(migrationsDirectory, filename), "utf8");

      return {
        filename,
        sql,
        checksum: createHash("sha256").update(sql).digest("hex"),
      };
    }),
  );
}

export async function migrate(): Promise<void> {
  const migrations = await loadMigrations();
  const client = await db.connect();

  try {
    await client.query("select pg_advisory_lock(41920260825)");
    await client.query(`
      create table if not exists schema_migrations (
        filename text primary key,
        checksum text not null,
        applied_at timestamptz not null default now()
      )
    `);

    const appliedResult = await client.query<AppliedMigration>(
      "select filename, checksum from schema_migrations",
    );
    const missingAppliedMigrations = getMissingAppliedMigrationFilenames(
      appliedResult.rows.map(({ filename }) => filename),
      migrations.map(({ filename }) => filename),
    );

    if (missingAppliedMigrations.length > 0) {
      throw new Error(
        `Applied migration files are missing: ${missingAppliedMigrations.join(", ")}`,
      );
    }

    const appliedMigrations = new Map(
      appliedResult.rows.map(({ filename, checksum }) => [filename, checksum]),
    );

    for (const migration of migrations) {
      const appliedChecksum = appliedMigrations.get(migration.filename);

      if (appliedChecksum !== undefined) {
        if (appliedChecksum !== migration.checksum) {
          throw new Error(`Migration checksum mismatch: ${migration.filename}`);
        }
        continue;
      }

      await client.query("begin");
      try {
        await client.query(migration.sql);
        await client.query(
          "insert into schema_migrations (filename, checksum) values ($1, $2)",
          [migration.filename, migration.checksum],
        );
        await client.query("commit");
      } catch (error) {
        await client.query("rollback");
        throw error;
      }
    }
  } finally {
    await client.query("select pg_advisory_unlock(41920260825)");
    client.release();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  migrate()
    .then(() => {
      process.stdout.write("Database migrations complete.\n");
    })
    .finally(() => db.end());
}
