# PR Reviewer

Hosted GitHub App control plane plus an installed local runner. The runner
reviews pull requests with a model, verifies allowlisted commands in Docker,
and posts only after a human decision.

This README states what is proved on this checkout. Every claim has a command
you can run. Where a number would need a frozen eval holdout, the gap is
named. Nothing here is a placeholder that looks like a result.

## What is proved

| Claim | Command |
|---|---|
| Backend suite | `flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q` |
| Lint | `uv run ruff check .` |
| Types | `uv run mypy src` |
| Hosted schema cannot hold private review data | `uv run python scripts/generate_data_boundaries_doc.py --check` |
| Empty holdout refuses a baseline | see Eval below |
| Queue claim p99 at 4 workers | `flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run python scripts/queue_benchmark.py` |
| Dashboard screenshots from a live API | `cd apps/web && bunx playwright test tests/dashboard.spec.ts -g "desktop and mobile screenshots"` |

Last recorded backend suite on this branch: 747 passed.

Last recorded queue benchmark, same command as above:

```text
worker_count=4
jobs=40
pending_depth_after_enqueue=40
claimed=40
p99_claim_ms=11.710
```

That is claim latency on local Postgres, not latency per pull request.

## What is not measured

- Precision and recall: not measured. The frozen holdout does not exist yet.
- False findings per PR: not measured. Same holdout gap.
- Cost per PR and useful findings per dollar across modes: not measured.
  `run_diff_only_baseline` raises `BaselineBlocked: holdout is empty; refusing to report a baseline`.
- FoodSpector shadow: not started. Needs a deployed control plane and 14 days
  of real PRs.

```bash
uv run python -c "from pr_reviewer.evals.fixture_reviewer import FixtureReviewer; from pr_reviewer.evals.run_eval import load_public_eval_cases, run_diff_only_baseline; run_diff_only_baseline(load_public_eval_cases(), FixtureReviewer.perfect())"
```

Expected: `BaselineBlocked: holdout is empty; refusing to report a baseline`.

## Why Redis is off

Jobs are Postgres rows claimed with `FOR UPDATE SKIP LOCKED`
(`src/pr_reviewer/jobs/claim_review_job.py`). ADR-002 says add Redis only if
claim p99 goes above 2 seconds. The recorded local run is 11.710 ms. Redis is
not in the stack.

## Why TigerData is off

v1 uses plain Postgres. Global constraint: do not use TigerData, Timescale,
DiskANN, or pgvectorscale in v1.

## Why specialist mode is off

Default policy keeps specialists disabled
(`tests/test_specialists.py::test_specialist_mode_is_disabled_on_the_default_policy`).
LangGraph is off
(`tests/test_langgraph_engine.py`). Enabling either without a holdout
comparison would be an unmeasured experiment. The comparison command raises
`BaselineBlocked` on the public dataset.

## Data retention

- Uninstall of the local runner preserves reviews and volumes by default.
  Deleting data requires `--confirm-delete`
  (`tests/test_runner_uninstall.py`).
- Uninstall of one hosted repository leaves the sibling and the installation
  (`tests/test_retention.py::test_uninstall_one_repository_leaves_sibling_and_installation_intact`).
- Hosted columns that could hold source or findings are rejected by
  `assert_no_private_columns`. See `docs/DATA_BOUNDARIES.md`.

## Rollback

`reviewer update` hashes the artifact before replace and keeps a `.prior`
copy (`tests/test_runner_update.py::test_update_keeps_the_prior_version_for_rollback`).
A failed replace writes the prior bytes back.

## Local setup

```bash
uv sync
docker compose up -d postgres
DATABASE_URL=postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer uv run pr-reviewer-db-migrate
uv run ruff check .
uv run mypy src
flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q
```

Hosted API (loopback, for operator work):

```bash
uv run pr-reviewer-api
```

Webhook path: `POST /api/github/webhook`. HMAC is checked before JSON parse
(`tests/test_webhook.py`).

Worker:

```bash
uv run pr-reviewer-worker
```

Installer and doctor: `docs/INSTALL.md`. Architecture: `docs/ARCHITECTURE.md`.
Security: `docs/SECURITY.md`. Demo: `docs/DEMO.md`. Eval commands: `docs/EVALS.md`.

## Known limits

- No public hostname yet. `reviewer.niresh.tech` is not live.
- Dashboard is loopback only. Docs, Redoc, and OpenAPI are off.
- Full mode needs Docker. Analysis-only never claims executable verification.
- One active runner per repository in v1.
- Public auto-post stays off until measured release gates pass.

## License

Private. Not a public package.
