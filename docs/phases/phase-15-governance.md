# Phase 15 - ✅ Governance

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ GOVERNANCE PROOF GATE REPRODUCED 2026-09-01.** Master Tasks 8 through 10, 15,
and 17 are ✅. Master Tasks 20 through 22 are treated as done at HEAD. Product-runtime
Tasks 1, 2, 8, and 9 are ✅. Master Tasks 24 and 26 stay ⬜ and are not this inspectability
gate.

## 1 - ✅ Who approved, and the decision stays

`record_human_feedback` (`notifications/feedback.py:13`) writes actor, action, note,
and hashes. Rows append. A later row does not rewrite prompts
(`tests/test_human_feedback.py`). Dashboard pending approvals and an approval race
live on the loopback API.

## 2 - ✅ Prompt and policy versions cannot be silently rewritten

`PromptRegistry.register` (`prompts/registry.py:27`) raises
`PromptVersionImmutable` on an existing name and version
(`tests/test_prompt_registry.py`). Hosted prompt rows have the same unique
constraint. One dispute does not change prompts, policy, labels, or routing
(`evals/feedback_candidates.py:43`). Repeated evidence plus a human audit can
become an eval candidate. Repeated disputes without audit cannot.

## 3 - ✅ What data remains, and delete is per repository

`uninstall_repository` (`security/retention.py:19`) deletes one repository.
`purge_hosted_repository` (`control_plane/retention.py:8`) scopes every `DELETE`
by `installation_id` and `github_repository_id`. A sibling and the installation
stay (`tests/test_retention.py`). A late sweep raises
`RetentionSweepTimedOut`.

## 4 - ✅ How access is revoked

`revoke_runner` (`control_plane/repository_policy.py:100`) sets `revoked_at`. It
does not delete the row. A revoked runner fails authorization
(`tests/test_control_plane_identity.py`). `revoke_installation` sets
`revoked_at` on the installation (`control_plane/repository_policy.py:36`).
Approval is denied when the signed-in user does not control the installation
(`tests/test_pairing_approval_api.py`).

## 5 - ✅ How to dispute

Dispute is an append-only `FeedbackAction` (`notifications/feedback.py:10`). The
threshold for turning feedback into an eval candidate is in
`consider_feedback`. Confidence is not a posting decision.

## Design gate - ✅

✅ For a posted finding, actor and action are on the local decision row, prompt
versions are immutable, remaining data is repository-scoped, dispute appends, and
access revocation is a timestamp.

## Test gate - ✅ reproduced

The proof gate is: for any posted finding, show who or what approved it, what
evidence and versions were used, what data remains, how to dispute it, and how
access is revoked.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_human_feedback.py tests/test_feedback_candidates.py tests/test_prompt_registry.py tests/test_retention.py tests/test_control_plane_identity.py::test_runner_revocation_is_a_timestamp_not_a_delete tests/test_control_plane_identity.py::test_revoked_runner_fails_authorization tests/test_pairing_approval_api.py::test_approval_denied_when_the_signed_in_user_does_not_control_the_installation
....................                                                     [100%]
20 passed, 1 warning in 1.52s
```

`test_unauthenticated_docs_and_unknown_paths_are_not_ok` is the 06:11 FIX.

⚠️ Task 24 (FoodSpector shadow) and Task 26 (hiring README) are not this gate.
This document invents no eval number.

## Settled - ✅

- ✅ One dispute never rewrites prompts or routing.
- ✅ `HOSTED_EXEMPTIONS` stays empty.

## Open Decisions - ❓

- ❓ None for this inspectability gate. A named autonomy-change record for
  public auto-post remains morning work with Task 24.
