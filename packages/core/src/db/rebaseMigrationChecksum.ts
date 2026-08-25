import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { basename, dirname, join } from "node:path";
import { db } from "./client";

const migrationsDirectory = join(dirname(fileURLToPath(import.meta.url)), "migrations");

export function validateMigrationRebaseRequest(
  environment: Record<string, string | undefined>,
  filename: string | undefined,
): string {
  if (environment.ALLOW_DEV_MIGRATION_REBASE !== "1") {
    throw new Error("Set ALLOW_DEV_MIGRATION_REBASE=1 to repair a migration checksum");
  }

  if (filename === undefined || filename.length === 0) {
    throw new Error("A migration filename is required");
  }

  if (filename !== basename(filename) || !filename.endsWith(".sql")) {
    throw new Error(`Invalid migration filename: ${filename}`);
  }

  return filename;
}

export async function rebaseMigrationChecksum(
  filename: string | undefined,
  environment: Record<string, string | undefined> = process.env,
): Promise<void> {
  const migrationFilename = validateMigrationRebaseRequest(environment, filename);
  const sql = await readFile(join(migrationsDirectory, migrationFilename), "utf8");
  const checksum = createHash("sha256").update(sql).digest("hex");
  const client = await db.connect();

  try {
    await client.query("select pg_advisory_lock(41920260825)");
    await client.query("begin");

    const result = await client.query<{ filename: string }>(
      `update schema_migrations
       set checksum = $1
       where filename = $2
       returning filename`,
      [checksum, migrationFilename],
    );

    if (result.rowCount !== 1) {
      throw new Error(`Migration is not recorded: ${migrationFilename}`);
    }

    await client.query("commit");
  } catch (error) {
    await client.query("rollback");
    throw error;
  } finally {
    await client.query("select pg_advisory_unlock(41920260825)");
    client.release();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  rebaseMigrationChecksum(process.argv[2])
    .then(() => {
      process.stdout.write("Migration checksum repaired.\n");
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      process.stderr.write(`${message}\n`);
      process.exitCode = 1;
    })
    .finally(() => db.end());
}
