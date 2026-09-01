# Failed experiments

Task 26 asks for real reports, including what was tried and discarded. The
history holds nine:

- optimistic precision denominator
- header-only PEM redaction
- direct-import-only boundary check
- mine_eval_candidates stub
- confidence default
- fence breakout in wrap_untrusted
- fail-open dashboard guard
- invented useful_findings_per_dollar
- unknown-age feedback default

Each section names the catching commit and the test that now prevents a
repeat. This file has no quality numbers. A holdout has not been labelled
yet, so no precision, recall, latency, or cost figure belongs here.

`tests/test_failed_experiments.py` fails if any of the nine names or catching
tests disappear from this file.

## 1. Optimistic precision denominator

Tried: count a `needs_human_match` near-miss as a true positive so one
unnamed precision number looked cleaner.

Failed: the matcher had already said it could not tell. Rounding that up
hid misses.

Caught: `99228fa` (`feat: add eval harness with mined candidates and
pessimistic matching`) landed named denominators instead.
`precision_per_finding` keeps near-miss findings in the predicted count and
out of true positives. `precision_per_case` is clean only when the case has
a match, no extras, and no `needs_human_match`.

Tests that now prevent it:

- `tests/test_eval_matching.py::test_semantic_near_miss_needs_human_match_and_is_not_a_pass`
- `tests/test_eval_metrics.py::test_metrics_cover_precision_recall_and_cost`

Also recorded in `docs/EVAL_DATASET.md`.

## 2. Header-only PEM redaction

Tried: redact `-----BEGIN ... PRIVATE KEY-----` and leave the body.

Failed: audit text still held the key material. A truncated paste with no
END line survived a block regex that required END.

Caught: `e88f90f` (`feat: add hosted connector audit log with typed fields
and shape-based redaction`). Typed fields reject a header even without END
(`_PEM_HEADER_RE`). Free-text redaction strips the full BEGIN...END block
(`_PEM_BLOCK_RE`) and drops leftover header-plus-body when END is missing.

Test that now prevents it:

- `tests/test_connector_contracts.py::test_redaction_removes_pem_bodies_not_just_headers`

## 3. Direct-import-only boundary check

Tried: inspect only packages found on disk, and only the first import hop.

Failed: a check that finds nothing on disk passes against nothing. A
forbidden import through a second package also passed.

Caught: `4b6ebad` (`feat: add hosted identity and repository policy control
plane`) added `EXPECTED_EXISTING_PACKAGES` and
`test_guarded_package_inventory_matches_snapshot`. `f117732` (`test: check
package boundaries transitively across the internal import graph`) walks the
AST import graph to a fixed point.

Tests that now prevent it:

- `tests/test_package_boundaries.py::test_guarded_package_inventory_matches_snapshot`
- `tests/test_package_boundaries.py::test_guarded_packages_have_no_transitive_forbidden_reach`

## 4. mine_eval_candidates stub

Tried: treat `git log` subjects as labels, or dump every commit into one
candidate.

Failed: a commit message is a guess. One blob mixed diffs so a later
reviewer could not say which commit produced which finding.

Caught: failing tests in `2f3c85c` (`test: add failing tests for eval
contracts, matching, and metrics`). `99228fa` emitted `EvalCandidate` rows
with no `expected_labels`. `c35c7d1` (`fix: mine one eval candidate per
commit and skip oversized diffs`) emits one candidate per commit.

Tests that now prevent it:

- `tests/test_eval_mining.py::test_mining_emits_candidates_not_labels`
- `tests/test_eval_mining.py::test_commit_message_is_evidence_not_ground_truth`
- `tests/test_eval_mining.py::test_mining_emits_one_candidate_per_commit`

## 5. confidence default

Tried: omit `Finding.confidence` and let a default stand in for high
confidence, or count a graph edge with missing confidence as EXTRACTED.

Failed: routing or sensitivity would treat silence as strong.

Caught: `Finding.confidence` has been required since `1c0628a`
(`refactor: convert backend to python`): `Field(ge=0, le=1)` with no default.
`eb4126c` (`feat: add deterministic finding gate and classified notification
channels`) routes from concern, verification, and `public_safe`, not
confidence. `7367580` (`feat: add repository profile and directed code graph
as context sources`) maps a missing graph-edge confidence to `INFERRED`,
which does not count toward sensitivity. `0869afd` (`feat: add eval
regression gates, feedback candidates, and drift checks`) adds an AST check
that routing source never reads confidence.

Tests that now prevent it:

- `tests/test_eval_regression_gate.py::test_routing_source_does_not_read_confidence`
- `tests/test_notification_policy.py::test_model_cannot_bypass_routing_through_severity_confidence_rationale_or_title`
- `tests/test_code_graph.py::test_missing_confidence_does_not_count_toward_sensitivity`

## 6. Fence breakout in wrap_untrusted

Tried: wrap repository text in BEGIN/END markers without stripping inner
copies of those markers.

Failed: untrusted diff text that contained `UNTRUSTED_END` closed the fence
and whatever followed looked like trusted instructions.

Caught: `ee0a661` (`feat: add trusted instruction sources and untrusted
prompt input boundaries`). `_strip_markers` removes inner BEGIN/END before
wrapping, then asserts exactly one of each.

Test that now prevents it:

- `tests/test_prompt_boundaries.py::test_wrap_untrusted_strips_inner_delimiter_breakout`

## 7. Fail-open dashboard guard

Tried: `path.startswith("/dashboard/")` before checking the session, with
FastAPI default `/docs` and `/openapi.json` left on.

Failed: CLAUDE-IN `2026-09-01T06:11:00+05:30` and `2026-09-01T06:26:00+05:30`.
Unauthenticated loopback GET of `/openapi.json` and `/docs` returned 200.
Any new route outside the prefix inherited no auth.

Caught: `bd8b7dd` (`feat: add versioned installer, setup wizard, and
doctor`) inverted the guard to deny by default and set `docs_url=None`,
`redoc_url=None`, `openapi_url=None`. `e704cd7` is the fail-open version,
not the fix.

Test that now prevents it:

- `tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok`

## 8. Invented useful_findings_per_dollar

Tried: `379b358` (`feat: add specialist reviewers, deterministic merge, and
langgraph adapter`) computed `precision_per_finding * reviewed_pr_count /
cost_usd` and returned `0.0` when cost was missing.

Failed: CLAUDE-IN `2026-09-01T05:39:00+05:30`. The ratio times PR count is
not a finding count. A missing cost looked like a measured zero instead of
"do not report".

Caught: `0869afd` (`feat: add eval regression gates, feedback candidates,
and drift checks`) divides `useful_finding_count` by cost and raises
`BaselineBlocked` when cost is missing.

Tests that now prevent it:

- `tests/test_eval_regression_gate.py::test_useful_findings_per_dollar_is_blocked_without_cost`
- `tests/test_eval_regression_gate.py::test_useful_findings_per_dollar_uses_useful_finding_count`

## 9. Unknown-age feedback default

Tried: `when = event.observed_at or now`, so a missing timestamp counted as
new.

Failed: CLAUDE-IN `2026-09-01T13:58:00+05:30`. Unknown age never decayed.

Caught: `5b1265f` (`fix: decay feedback of unknown age instead of treating
it as new`). A missing `observed_at` is older than `FEEDBACK_MAX_AGE` and is
dropped.

Test that now prevents it:

- `tests/test_feedback_candidates.py::test_missing_observed_at_is_dropped_while_a_fresh_event_is_kept`
