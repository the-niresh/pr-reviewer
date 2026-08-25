export const schemaTableNames = [
  "github_deliveries",
  "pull_requests",
  "review_jobs",
  "findings",
  "code_chunks",
  "prompt_versions",
  "model_calls",
  "human_decisions",
  "agent_events",
] as const;

export type SchemaTableName = (typeof schemaTableNames)[number];
