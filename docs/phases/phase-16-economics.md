# Phase 16 - ⚠️ Economics and Cost Control

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ⚠️ BUDGET GATE REPRODUCED, QUALITY-PER-DOLLAR REPORT BLOCKED 2026-09-01.**
Master Tasks 5, 10, 11, 13, 18 through 20, and 22 are treated as done at HEAD.
Master Tasks 24 and 26 stay ⬜ and are not this budget gate. The concurrent
reservation proof is runnable. The eval report that compares useful findings
per dollar across modes is not, because the public holdout is empty.

## 1 - ✅ Unknown models cannot go uncounted

`_PRICE_PER_MILLION` (`models/provider.py:23`) lists `openai/gpt-4o-mini` and
`anthropic/claude-3-5-haiku-latest`. `cost_usd_for` (`models/provider.py:117`)
raises `ModelProviderFailure` when the pair is missing
(`models/provider.py:120`). That is fail closed, not a silent zero.

## 2 - ✅ Token counts and per-call cost are recorded

`test_token_counts_and_cost_are_recorded` asserts input tokens, output tokens,
and `cost_usd` on the adapter response. Ledger fields are a closed set
(`models/provider.py:110`). The API key and the raw request never sit on the
ledger (`tests/test_model_provider.py`). Per-PR cost on the dashboard is
`/dashboard/jobs/{job_id}/costs` (`web/dashboard_api.py:169`). Missing store
totals become zeros that still pass `CostItem` validation. That is a display
fallback, not a measured eval number.

## 3 - ✅ Unset budget denies

`is_configured` (`reliability/budget.py:32`) is false when either cap is
missing or not greater than zero. `require_configured`
(`reliability/budget.py:40`) raises `BudgetDenied("unset")`. Hosted
`reserve_repository_budget` (`control_plane/budget.py:39`) and local
`reserve_job_budget` (`local_store/budget.py:11`) both deny unset. A zero
limit is unset. A null row is unset. Spending freely is not a path.

## 4 - ✅ Concurrent jobs cannot overspend one repository cap

Hosted reservation is one `UPDATE ... WHERE remaining >= this call RETURNING`
(`control_plane/budget.py:58`). It is not select-then-write
(`tests/test_budget.py:187`). `test_two_connections_cannot_exceed_one_repository_budget`
runs two connections against one cap. One succeeds. The other raises
`BudgetDenied("insufficient")`. A held reservation is keyed by `job_id` and
stays until the job is dead, cancelled, or committed
(`reliability/budget.py:5`). Local reservation dies with the process. A
recovered runner starts a new local reservation against the job envelope, not
against the repo cap.

## 5 - ✅ Dashboard and hosted totals exist

Loopback job costs are scoped by runner and repository
(`web/dashboard_api.py:169`). Hosted `/ops/cost` sums `spent_cost_usd`
(`control_plane/ops.py:44`). Neither endpoint invents a quality-per-dollar
figure.

## 6 - ⚠️ Quality-versus-cost report is refused

`useful_findings_per_dollar` (`evals/run_eval.py:101`) divides
`useful_finding_count` (`evals/types.py:102`) by `cost_usd`. When
`cost_usd <= 0` it raises `BaselineBlocked`. The unit test uses a synthetic
run object. That is not a holdout measurement.

`run_diff_only_baseline`, `run_retrieval_comparison`, and
`run_specialist_comparison` each refuse when holdout is empty
(`evals/run_eval.py:47`, `evals/run_eval.py:59`, `evals/run_eval.py:94`).
`datasets/public/eval_cases.jsonl` has one row: `public-1`, `split=dev`.
This document invents no useful-findings-per-dollar number across baseline,
retrieval, verification, or specialist modes.

## Design gate - ⚠️ budget closed, report open

✅ Unset denies. Two connections cannot overspend one repository cap.
Unknown models fail closed. Token counts are recorded.

⚠️ The eval report that compares useful findings per dollar across modes
cannot run until a frozen holdout exists.

## Test gate - ⚠️ partial

The proof gate is: concurrent jobs cannot overspend a repository budget, and
the eval report compares useful findings per dollar across baseline,
retrieval, verification, and specialist modes.

Budget half, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_budget.py tests/test_eval_regression_gate.py::test_useful_findings_per_dollar_is_blocked_without_cost tests/test_eval_regression_gate.py::test_useful_findings_per_dollar_uses_useful_finding_count tests/test_model_provider.py::test_token_counts_and_cost_are_recorded tests/test_dashboard_api.py::test_findings_and_redacted_events_and_costs
................                                                         [100%]
16 passed, 1 warning in 1.40s
```

Quality-per-dollar half, same checkout:

```text
$ uv run python -c "from pr_reviewer.evals.fixture_reviewer import FixtureReviewer; from pr_reviewer.evals.run_eval import load_public_eval_cases, run_diff_only_baseline, run_retrieval_comparison, run_specialist_comparison; cases = load_public_eval_cases(); print([(c.id, c.split) for c in cases]); perfect = FixtureReviewer.perfect(); run_diff_only_baseline(cases, perfect)"
[('public-1', 'dev')]
BaselineBlocked: holdout is empty; refusing to report a baseline
```

The same cases also raised:

```text
BaselineBlocked: holdout is empty; refusing to report a retrieval comparison
BaselineBlocked: holdout is empty; refusing to report a specialist comparison
```

`FixtureReviewer` was the reviewer. No model HTTP client ran. No
quality-per-dollar number is reported here because none was produced.
`test_unauthenticated_docs_and_unknown_paths_are_not_ok` is the 06:11 FIX.

⚠️ Task 24 (FoodSpector shadow) and Task 26 (hiring README) are not this gate.

## Settled - ✅

- ✅ Unset repository budget denies. It does not spend freely.
- ✅ Hosted reservation is one atomic update, not select-then-write.
- ✅ Two connections cannot exceed one repository budget.
- ✅ `useful_findings_per_dollar` refuses a zero cost instead of returning 0.0.
- ✅ An empty holdout refuses a specialist comparison. It does not synthesise one.

## Open Decisions - ❓

- ❓ Who audits the mined FoodSpector candidates into a named-auditor holdout
  so the quality-versus-cost report can run without inventing a number.
