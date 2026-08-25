# Database

Local installs use Docker Postgres with pgvector.

Hosted demo and production use Neon Postgres with pgvector enabled.

We are not using Prisma or Drizzle in v1. Runtime queries use `pg`. Migrations are plain SQL files in `packages/core/src/db/migrations`.

Neon is the hosted default because it is cheap to start, supports Postgres and pgvector, works well with Vercel or a separate worker, and avoids self-hosting database ops during the first release.

Self-hosted Postgres is a later option if traffic, cost, or compliance needs justify owning backups, patching, monitoring, and failover.

## Local setup

Run `docker compose up -d postgres`, then `bun run db:migrate`. The migration command uses `postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer` when `DATABASE_URL` is not set.

Set `DATABASE_URL` to the Neon connection string in hosted environments and include `sslmode=verify-full`. Do not add that value to a committed file or require it for local checks.
