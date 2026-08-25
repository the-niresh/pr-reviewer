# Database

Local installs use Docker Postgres with pgvector.

Hosted demo and production use Neon Postgres with pgvector enabled.

We are not using Prisma or Drizzle in v1. Runtime queries use `pg`. Migrations are plain SQL files in `packages/core/src/db/migrations`.

Neon is the hosted default because it is cheap to start, supports Postgres and pgvector, works well with Vercel or a separate worker, and avoids self-hosting database ops during the first release.

Self-hosted Postgres is a later option if traffic, cost, or compliance needs justify owning backups, patching, monitoring, and failover.

## Event and cost records

`agent_events` is the append-only audit trail for each review job. Writers only insert rows. The database rejects updates and deletes.

Each model request writes one `model_calls` row and one linked `model_call.recorded` event in the same transaction. The model row stores the provider, model name, prompt version id, token counts, and `cost_usd`. Request metadata is stored in `request_metadata`; `response_metadata.latencyMs` stores request latency in milliseconds.

## Local setup

Run `docker compose up -d postgres`, then `bun run db:migrate`. The migration command uses `postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer` when `DATABASE_URL` is not set.

Set `DATABASE_URL` to the Neon connection string in hosted environments and include `sslmode=verify-full`. Do not add that value to a committed file or require it for local checks.

For a pre-deploy migration rebaseline, run `ALLOW_DEV_MIGRATION_REBASE=1 bun run db:rebase-migration -- <migration-filename>`. This updates only an existing `schema_migrations` checksum and is never part of normal migration execution.
