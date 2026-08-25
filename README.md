# PR Reviewer

Python backend for an AI PR review agent.

The current backend covers the base system:

- FastAPI GitHub webhook ingress
- HMAC signature checks before processing
- GitHub delivery deduplication
- Plain SQL migrations for Neon or local Postgres
- Durable review jobs with leases and retries
- Append-only agent event log
- Model call cost and latency records
- Typed contracts with Pydantic

## Local setup

```bash
uv sync
docker compose up -d postgres
DATABASE_URL=postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer uv run pr-reviewer-db-migrate
uv run ruff check .
uv run mypy
uv run pytest
```

## Run the API

```bash
uv run pr-reviewer-api
```

The webhook endpoint is:

```text
POST /api/github/webhook
```

## Run the worker

```bash
uv run pr-reviewer-worker
```

The worker currently claims, renews, fails, and completes review jobs. The actual AI review
logic comes next.

## Database

Hosted use is Neon Postgres with pgvector. Runtime DB access uses `psycopg` and plain SQL.
There is no ORM in v1.
