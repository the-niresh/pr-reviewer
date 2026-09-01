# Phase 20 - ⚠️ Continuous Learning

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ⚠️ SYNTHETIC GATES AND FEEDBACK THRESHOLD REPRODUCED, HOLDOUT SHIP
CHECK BLOCKED 2026-09-01.** Master Task 20 is treated as done at HEAD. Master
Task 9 stays ⚠️ because the public holdout is empty. Master Tasks 24 and 26
stay ⬜ and are not this local gate.

## 1 - ✅ One dispute cannot rewrite behavior

`consider_feedback` (`evals/feedback_candidates.py:43`) deletes the prompt,
policy, label, and routing arguments (`evals/feedback_candidates.py:52`) and
always returns empty rewrite tuples (`evals/feedback_candidates.py:72`).
`test_one_dispute_does_not_change_prompts_policy_labels_or_routing`
(`tests/test_feedback_candidates.py:17`) is that rule.

## 2 - ✅ Feedback needs repeats plus a human audit

The default threshold is `min_repeats=3` (`evals/feedback_candidates.py:50`).
A group below that count is skipped. A group with no `human_audited` event is
skipped (`evals/feedback_candidates.py:60`). Repeated disputes without audit
are not candidates (`tests/test_feedback_candidates.py:49`). Repeated evidence
plus audit becomes an eval candidate only
(`tests/test_feedback_candidates.py:71`). It does not edit prompts.

## 3 - ✅ Prompt versions are immutable

`PromptRegistry.register` (`prompts/registry.py:27`) raises
`PromptVersionImmutable` when the name and version already exist
(`prompts/registry.py:30`). A new version is a new key. Version 1 content
stays (`tests/test_prompt_registry.py:16`). Hosted `prompt_versions` has the
same uniqueness (`tests/test_prompt_registry.py:38`).

## 4 - ✅ Synthetic regression and drift gates exist

`compare_eval_reports` (`evals/regression_gate.py:48`) blocks precision, false
findings per PR, high-value recall, cost, and latency against both the
baseline report and `EvalThresholds`. The tests use synthetic `EvalRun`
objects (`tests/test_eval_regression_gate.py:60`).

`detect_drift` (`evals/regression_gate.py:113`) alerts on rejection rate,
dispute rate, no-finding rate, cost, latency, and retrieval misses
(`tests/test_eval_regression_gate.py:143`). Brier score and calibration
buckets are reported (`evals/regression_gate.py:78`). Routing does not read
confidence (`tests/test_eval_regression_gate.py:133`).

`write_eval_report` (`evals/run_eval.py:109`) writes `run.model_dump_json()`.
That is one run dump, not a versioned dataset id.

## 5 - ⚠️ Frozen holdout ship check is refused

The proof gate is: a proposed prompt, model, retrieval, or routing change is
tested against the frozen holdout and recent checked cases, and cannot ship
when precision, noise, safety, or cost gates regress.

`datasets/public/eval_cases.jsonl` has one row: `public-1`, `split=dev`.
`run_diff_only_baseline` (`evals/run_eval.py:40`),
`run_retrieval_comparison` (`evals/run_eval.py:51`), and
`run_specialist_comparison` (`evals/run_eval.py:86`) each raise
`BaselineBlocked` when holdout is empty. A holdout row without
`human_auditor` is rejected (`evals/types.py:75`). This document invents no
precision, noise, safety, or cost number from a live change.

## 6 - ⚠️ Required outputs that are not in this checkout

There is no `decay` symbol in `src/` or `tests/`. Old-feedback decay is not
implemented.

`EvalCase` (`evals/types.py:63`) has no dataset version field. The public
file is one jsonl path, not a versioned dataset.

There is no model-comparison report beyond the holdout refusal above.
Finding-level dashboard approval (`web/dashboard_api.py:226`) is not an
autonomy-change approval that ships a routing or prompt change. Feedback
cannot emit `routing_changes`.

## Design gate - ⚠️ machinery closed, ship check open

✅ One dispute does not rewrite prompts, policy, labels, or routing. Three
repeats plus audit can become an eval candidate. Prompt versions cannot be
overwritten. Synthetic compare and drift gates block named regressions.

⚠️ A proposed change cannot be tested against a frozen holdout tonight. There
is no old-feedback decay and no dataset version id.

## Test gate - ⚠️ partial

Local machinery half, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_eval_regression_gate.py tests/test_feedback_candidates.py tests/test_prompt_registry.py tests/test_eval_runner.py
...........................                                              [100%]
27 passed, 1 warning in 3.23s
```

`test_one_dispute_does_not_change_prompts_policy_labels_or_routing` and
`test_compare_eval_reports_passes_when_candidate_meets_baseline_and_thresholds`
are the local learning-control proof.
`test_unauthenticated_docs_and_unknown_paths_are_not_ok` is the 06:11 FIX.
`test_public_holdout_baseline_is_still_blocked` is the holdout refusal inside
the suite.

Holdout ship-check half, same checkout:

```text
$ uv run python -c "from pr_reviewer.evals.fixture_reviewer import FixtureReviewer; from pr_reviewer.evals.run_eval import load_public_eval_cases, run_diff_only_baseline, run_retrieval_comparison, run_specialist_comparison; cases = load_public_eval_cases(); print([(c.id, c.split) for c in cases]); perfect = FixtureReviewer.perfect();
try:
    run_diff_only_baseline(cases, perfect)
except Exception as e:
    print(type(e).__name__ + ': ' + str(e))
try:
    run_retrieval_comparison(cases, perfect, perfect)
except Exception as e:
    print(type(e).__name__ + ': ' + str(e))
try:
    run_specialist_comparison(cases, perfect, perfect)
except Exception as e:
    print(type(e).__name__ + ': ' + str(e))"
[('public-1', 'dev')]
BaselineBlocked: holdout is empty; refusing to report a baseline
BaselineBlocked: holdout is empty; refusing to report a retrieval comparison
BaselineBlocked: holdout is empty; refusing to report a specialist comparison
```

`FixtureReviewer` was the reviewer. No model HTTP client ran. No holdout
precision, noise, safety, or cost number is reported here because none was
produced.

⚠️ Task 9 stays ⚠️. Task 24 (FoodSpector shadow) and Task 26 (hiring README)
are not this gate.

## Settled - ✅

- ✅ One dispute does not change prompts, policy, labels, or routing.
- ✅ An eval candidate needs repeated evidence and a human audit.
- ✅ An existing prompt name and version cannot be rewritten.
- ✅ Synthetic compare_eval_reports blocks named regressions.
- ✅ An empty holdout refuses baseline, retrieval, and specialist reports.

## Open Decisions - ❓

- ❓ Who audits the mined FoodSpector candidates into a named-auditor holdout
  so a proposed prompt, model, retrieval, or routing change can be scored
  without inventing a number.
- ❓ Whether old-feedback decay is a later task or a morning add after the
  holdout exists.
