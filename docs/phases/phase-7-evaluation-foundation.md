# Phase 7 - ⚠️ Evaluation Foundation

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ⚠️ HARNESS LANDED, HOLDOUT REPORT BLOCKED 2026-09-01.** Master Tasks 10A, 11,
13, 14, 19, and 20 are treated as done at HEAD. Master Task 9 stays ⚠️ because the public
holdout is empty. Master Tasks 24 and 26 stay ⬜ and are not this harness gate. Task 9
alone must satisfy the proof gate. It does not, because there is no frozen holdout.

## 1 - ✅ Ground truth is typed, not judged by a model

`EvalCase` (`evals/types.py:63`) is frozen with `extra=forbid`. A holdout row without
a named `human_auditor` is rejected (`evals/types.py:75`). Split assignment is time
based, not random (`evals/types.py:112`). Mining emits candidates, not labels
(`tests/test_eval_mining.py`). A commit message is evidence, not ground truth.

## 2 - ✅ Matching is deterministic

`match_findings` (`evals/match_findings.py:49`) matches concern, file, overlapping
lines, and normalised category. No line overlap is not a match. A semantic near
miss needs a human match and is not a pass (`tests/test_eval_matching.py`). There
is no LLM judge on this path.

## 3 - ✅ The harness injects a reviewer and makes no HTTP call

`run_eval` (`evals/run_eval.py:30`) takes a `ReviewerCallable`.
`FixtureReviewer` (`evals/fixture_reviewer.py:27`) is recorded and seeded. The
eval package imports nothing from `models/` (`tests/test_eval_runner.py`). The
dev case can run under the fixture. That is not a holdout report.

## 4 - ⚠️ Frozen holdout is empty

`datasets/public/eval_cases.jsonl` has one row: `public-1`, `split=dev`.
`run_diff_only_baseline` (`evals/run_eval.py:40`) raises `BaselineBlocked`
when holdout is empty (`evals/run_eval.py:47`). `useful_findings_per_dollar`
raises `BaselineBlocked` when `cost_usd <= 0` (`evals/run_eval.py:101`). This
document invents no precision, recall, latency, or cost number.

## Design gate - ✅

✅ The harness can score a fixture reviewer without a model call. Uncertain
matches stay human. An empty holdout refuses a report.

## Test gate - ⚠️ blocked on holdout

The proof gate is: the eval runner produces a versioned report from a frozen
holdout set, driven by a recorded `FixtureReviewer` and making no model call.

Harness tests, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_eval_runner.py tests/test_eval_matching.py tests/test_eval_mining.py tests/test_eval_metrics.py
.......................                                                  [100%]
23 passed, 1 warning in 1.31s
```

Holdout report command, same checkout:

```text
$ uv run python -c "from pr_reviewer.evals.fixture_reviewer import FixtureReviewer; from pr_reviewer.evals.run_eval import load_public_eval_cases, run_diff_only_baseline; cases = load_public_eval_cases(); print([(c.id, c.split) for c in cases]); run_diff_only_baseline(cases, FixtureReviewer.perfect())"
[('public-1', 'dev')]
BaselineBlocked: holdout is empty; refusing to report a baseline
```

`FixtureReviewer` was the reviewer. No model HTTP client ran. No quality number
is reported here because none was produced. `test_unauthenticated_docs_and_unknown_paths_are_not_ok`
is the 06:11 FIX.

⚠️ Task 24 and Task 26 are not this gate.

## Settled - ✅

- ✅ Holdout requires a named human auditor. That rule is in the type.
- ✅ An empty holdout refuses a baseline. It does not synthesise one.
- ✅ `HOSTED_EXEMPTIONS` stays empty.

## Open Decisions - ❓

- ❓ The public dataset is still one `dev` case. The miner at `c35c7d1` can
  produce candidates. A human has to audit them before any holdout row exists.
  Morning job.
