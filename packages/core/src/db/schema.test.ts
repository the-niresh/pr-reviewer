import { describe, expect, it } from "vitest";
import { getMissingAppliedMigrationFilenames } from "./migrate";
import { schemaTableNames } from "./schema";

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
});
