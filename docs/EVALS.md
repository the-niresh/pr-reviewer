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

## Candidate sheet and holdout builder

Mine a repo into an unjudged JSONL sheet. Every row has empty `verdict`,
`human_auditor`, `split`, and `labels`. The writer does not label anything.

```bash
uv run python -m pr_reviewer.evals.holdout_sheet write-sheet \
  --repo /srv/claude/projects/FoodSpector \
  --out datasets/private/candidate_sheet.jsonl \
  --max-cases 40
```

Real run on 2026-09-01 against FoodSpector printed:

`candidates=37 skipped=3 out=datasets/private/candidate_sheet.jsonl`

That sheet is gitignored. A human fills `verdict` (`include` or `exclude`),
and for include rows also `human_auditor`, `split` (`dev` or `holdout`), and
`labels`. Then:

```bash
uv run python -m pr_reviewer.evals.holdout_sheet build-holdout \
  --sheet datasets/private/candidate_sheet.jsonl \
  --out datasets/private/eval_cases.jsonl
```

The builder refuses with exit 2 if any row is still unjudged. It does not
guess a split. No holdout file has been written from the FoodSpector sheet.

## Feedback age cutoff

`consider_feedback` drops `FeedbackEvent` rows whose `observed_at` is older
than 90 days. That is an eval-candidate cutoff. It is not
`claim_recency_weight` in `retrieval/repo_profile.py`, which weights inferred
profile claims. A missing `observed_at` is treated as older than the cutoff
and is excluded. Unknown age counts against the event, not for it.

## What this file will not do

It will not invent a precision, recall, cost, or latency number. Those come
from a frozen holdout after a human audit, which is not available tonight.
