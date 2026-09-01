# Eval commands

The harness lives in `src/pr_reviewer/evals/`. It scores an injected reviewer.
It does not call a model API and it does not write Neon.

## Public dataset

`datasets/public/eval_cases.jsonl` currently has one `dev` case and zero
`holdout` cases. Any command that needs a frozen holdout raises
`BaselineBlocked` and refuses to publish a number.

## Commands

Diff-only baseline, FixtureReviewer, public cases:

```bash
uv run python -c "from pr_reviewer.evals.fixture_reviewer import FixtureReviewer; from pr_reviewer.evals.run_eval import load_public_eval_cases, run_diff_only_baseline; run_diff_only_baseline(load_public_eval_cases(), FixtureReviewer.perfect())"
```

Expected tonight: `BaselineBlocked: holdout is empty; refusing to report a baseline`.

Retrieval comparison:

```bash
uv run python -c "from pr_reviewer.evals.fixture_reviewer import FixtureReviewer; from pr_reviewer.evals.run_eval import load_public_eval_cases, run_retrieval_comparison; run_retrieval_comparison(load_public_eval_cases(), FixtureReviewer.perfect(), FixtureReviewer.perfect())"
```

Specialist comparison:

```bash
uv run python -c "from pr_reviewer.evals.fixture_reviewer import FixtureReviewer; from pr_reviewer.evals.run_eval import load_public_eval_cases, run_specialist_comparison; run_specialist_comparison(load_public_eval_cases(), FixtureReviewer.perfect(), FixtureReviewer.perfect())"
```

Write a machine-readable report from an `EvalRun` you already have (synthetic
or holdout). This writes JSON with the named metric fields on `EvalMetrics`:

```bash
uv run python -c "from pathlib import Path; from pr_reviewer.evals.run_eval import write_eval_report"
```

`write_eval_report(run, path)` writes `run.model_dump_json()`. Read
`precision_per_finding`, `false_findings_per_pr`, `cost_usd`, and the rest
from that file. Do not treat a missing holdout as a passing score.

## Regression gate

`compare_eval_reports(candidate, baseline, thresholds)` blocks on precision,
false findings per PR, high-value recall (`recall_per_finding`), cost, and
latency. Use it on synthetic `EvalRun` objects until a real holdout exists.

## What this file will not do

It will not invent a precision, recall, cost, or latency number. Those come
from a frozen holdout after a human audit, which is not available tonight.
