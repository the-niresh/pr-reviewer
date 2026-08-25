import { describe, expect, it } from "vitest";
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
});
