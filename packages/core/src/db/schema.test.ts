import { describe, expect, it } from "vitest";
import { getMissingAppliedMigrationFilenames } from "./migrate";
import { validateMigrationRebaseRequest } from "./rebaseMigrationChecksum";
import { schemaTableNames } from "./schema";
import { readFile } from "node:fs/promises";

describe("database schema", () => {
  it("contains the durable review tables", () => {
    expect(schemaTableNames).toEqual([
      "github_deliveries",
      "pull_requests",
      "review_jobs",
      "findings",
      "code_chunks",
      "prompt_versions",
      "model_calls",
      "human_decisions",
      "agent_events",
    ]);
  });

  it("detects an applied migration that is no longer on disk", () => {
    expect(
      getMissingAppliedMigrationFilenames(
        ["0001_initial.sql", "0002_foreign_key_indexes.sql"],
        ["0001_initial.sql"],
      ),
    ).toEqual(["0002_foreign_key_indexes.sql"]);
  });

  it("requires an explicit flag and migration filename for checksum repair", () => {
    expect(() => validateMigrationRebaseRequest({}, "0003_review_job_leases.sql")).toThrow(
      "ALLOW_DEV_MIGRATION_REBASE=1",
    );
    expect(() => validateMigrationRebaseRequest({ ALLOW_DEV_MIGRATION_REBASE: "1" }, undefined)).toThrow(
      "migration filename is required",
    );
    expect(
      validateMigrationRebaseRequest(
        { ALLOW_DEV_MIGRATION_REBASE: "1" },
        "0003_review_job_leases.sql",
      ),
    ).toBe("0003_review_job_leases.sql");
  });

  it("does not requeue running jobs in the lease migration", async () => {
    const sql = await readFile(new URL("./migrations/0003_review_job_leases.sql", import.meta.url), "utf8");

    expect(sql).not.toMatch(/update\s+review_jobs/i);
  });
});
