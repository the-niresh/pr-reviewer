# Eval dataset

Public cases live in `datasets/public/eval_cases.jsonl`. Private FoodSpector cases live in
`datasets/private/`, which is gitignored. Do not commit a private case.

A mined row is a candidate. A commit message is evidence, not ground truth. A holdout case
without a named human auditor is rejected.

The mechanical audit path is `pr-reviewer-holdout` (`evals/holdout_sheet.py`).
`write-sheet` mines commits into `datasets/private/candidate_sheet.jsonl` with
an empty verdict column. `build-holdout` writes `EvalCase` JSONL only from
judged include rows and refuses any blank verdict.

FoodSpector miner run 2026-09-01 (`--max-cases 40`): `candidates=37`
`skipped=3`. No row in that sheet has been labelled. The public file still has
one `dev` case and zero `holdout` cases.

## Precision denominators

`compute_metrics` reports both, as named fields. Do not read one number as the other.

- `precision_per_finding` is true positives over every predicted finding. A
  `needs_human_match` finding counts in this denominator as a miss. The matcher could
  not tell, so the eval does not round that up to a pass.
- `precision_per_case` is clean cases over reviewed cases. A case is clean only when it
  has at least one match, no extra findings, and no `needs_human_match`.

`recall_per_finding` and `recall_per_case` use the same two grains against expected
labels and cases.

`false_findings_per_pr` is unmatched predicted findings over `reviewed_pr_count`. It is
per-PR. That is why precision cannot be a single unnamed number sitting next to it.

## What a divergence means

High per-finding precision and low per-case precision means a few cases produced many
correct findings while other cases were dirty (extras or unresolved matches).

Low per-finding precision and high per-case precision means most cases looked clean at
the case grain, but the cases that missed dumped a lot of unmatched findings.

Treat a divergence as a reason to read the case rows, not as a number to average away.

## needs_human_rate

`needs_human_rate` is the share of cases the matcher could not resolve. It is a
diagnostic, not a second penalty. Precision already treats those findings as misses.
A second gate on the same fact would double-count it.

Read it with precision:

- low precision and a high rate: fix the matcher
- low precision and a low rate: fix the reviewer
