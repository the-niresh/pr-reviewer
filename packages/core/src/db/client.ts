import { Pool } from "pg";

export const localDatabaseUrl =
  "postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer";

export const databaseUrl = process.env.DATABASE_URL ?? localDatabaseUrl;

export const db = new Pool({ connectionString: databaseUrl });
