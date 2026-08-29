# Database

Local installs use Docker Postgres with pgvector.

Hosted demo and production use Neon Postgres with pgvector enabled.

We are not using Prisma or Drizzle in v1. Runtime queries use `psycopg`. Migrations are plain SQL files in `src/pr_reviewer/db/migrations`.

Neon is the hosted default because it is cheap to start, supports Postgres and pgvector, works well with Vercel or a separate worker, and avoids self-hosting database ops during the first release.

Self-hosted Postgres is a later option if traffic, cost, or compliance needs justify owning backups, patching, monitoring, and failover.

## Event and cost records

`agent_events` is the append-only audit trail for each review job. Writers only insert rows. The database rejects updates and deletes.

Each model request writes one `model_calls` row and one linked `model_call.recorded` event in the same transaction. The model row stores the provider, model name, prompt version id, token counts, `cost_usd` as `numeric(18, 12)`, and checked `latency_ms` -- aggregates only. Runtime Task 1B dropped `request_metadata` and `response_metadata`: neither ever held anything but a free-form blob, and the hosted plane must never hold a prompt, an output, or a hash of one.

Each event receives a database-generated monotonic `sequence`. Event readers order by that sequence, not by timestamps or UUIDs. `agent_events.payload` is a flat object of scalar values only (identifiers, enums, aggregate numbers); `agent_events_payload_is_flat` rejects a nested object or array at the database layer, and `record_event.serialize_json_object` rejects one before that.

## Local setup

Run `docker compose up -d postgres`, then `uv run pr-reviewer-db-migrate`. The migration command uses `postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer` when `DATABASE_URL` is not set.

Set `DATABASE_URL` to the Neon connection string in hosted environments and include `sslmode=verify-full`. Do not add that value to a committed file or require it for local checks.

The Python runtime keeps strict TLS verification. If a Neon URL has `sslmode=verify-full` and no `sslrootcert`, the config layer adds the `certifi` CA bundle before opening psycopg connections.

For a pre-deploy migration rebaseline, run `ALLOW_DEV_MIGRATION_REBASE=1 uv run pr-reviewer-db-rebase-migration <migration-filename>`. This updates only an existing `schema_migrations` checksum and is never part of normal migration execution.
